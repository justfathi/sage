"""Spawn & execute -- turn specs into working agents and run them.

Each agent run is just a scoped reasoning call: load its context, ask the
model to perform its role, capture the output. Nothing exotic.
"""

from __future__ import annotations

from typing import List, Optional

from ..providers.base import Provider
from . import evaluator as evaluator_mod
from . import tools as tools_mod
from .models import Agent, AgentSpec, AgentStatus
from .memory import KnowledgeBase


def spawn(spec: AgentSpec) -> Agent:
    return Agent(spec=spec)


AGENT_SYSTEM = (
    "You are a single-purpose agent inside SAGE. Stay strictly within your "
    "role. Produce one concrete artifact and note any open dependency."
)


def run_agent(provider: Provider, agent: Agent, goal: str, kb: KnowledgeBase,
              peer_context: str = "", artifacts: Optional[dict] = None) -> str:
    query = f"{agent.spec.role} {agent.spec.purpose} {goal}"
    context = kb.context_for(query, k=4)
    if peer_context:
        # Hand off prior agents' artifacts so work builds on work.
        context = f"{context}\n\n--- UPSTREAM AGENT OUTPUTS ---\n{peer_context}"

    # Actually invoke the agent's declared tools -- declared capability becomes
    # used capability. Their results are folded into the reasoning context.
    tctx = tools_mod.ToolContext(kb=kb, goal=goal, role=agent.spec.role,
                                 purpose=agent.spec.purpose,
                                 artifacts=artifacts if artifacts is not None else {})
    tool_results = tools_mod.run_tools(agent.spec.tools, tctx)
    agent.tools_used = list(agent.spec.tools or [])
    if tool_results:
        context = f"{context}\n\n--- TOOL RESULTS ---\n" + "\n".join(tool_results)

    task = (
        f"Perform your role.\nrole: {agent.spec.role}\n"
        f"purpose: {agent.spec.purpose}\n"
        f"success_criteria: {agent.spec.success_criteria}\n"
        f"overall goal: {goal}\n\nDo your work and report the result."
    )
    output = provider.reason(task, context=context, system=AGENT_SYSTEM, max_tokens=1024)
    agent.outputs.append(output)
    # Real performance signal: the model rates the artifact against the
    # agent's success criteria, instead of counting words.
    verdict = evaluator_mod.evaluate(provider, agent, goal, output)
    agent.score = verdict["score"]
    agent.notes = verdict["reason"]
    return output


def retrain_agent(provider: Provider, agent: Agent, goal: str,
                  kb: KnowledgeBase) -> str:
    """Give a flagged agent a second attempt, steered by its own critique.

    This is what makes "retrain" mean something: the agent re-does its work
    with the evaluator's feedback in hand, and is re-scored. If it improves,
    it comes back to life; if not, it stays flagged for the Gardener.
    """
    query = f"{agent.spec.role} {agent.spec.purpose} {goal}"
    context = kb.context_for(query, k=4)
    prior = agent.outputs[-1] if agent.outputs else ""
    task = (
        f"Re-do your work. Your previous attempt underperformed.\n"
        f"role: {agent.spec.role}\n"
        f"purpose: {agent.spec.purpose}\n"
        f"success_criteria: {agent.spec.success_criteria}\n"
        f"overall goal: {goal}\n"
        f"evaluator critique: {agent.notes}\n\n"
        f"PREVIOUS ATTEMPT:\n{prior[:1500]}\n\n"
        f"Produce a stronger artifact that directly addresses the critique."
    )
    output = provider.reason(task, context=context, system=AGENT_SYSTEM, max_tokens=1024)
    agent.outputs.append(output)
    verdict = evaluator_mod.evaluate(provider, agent, goal, output, is_retry=True)
    agent.score = verdict["score"]
    agent.notes = verdict["reason"]
    # If the retry clears the bar, the agent recovers.
    if agent.score >= 0.62:
        agent.status = AgentStatus.ALIVE
    return output


def order_by_dependencies(agents: List[Agent]) -> List[Agent]:
    """Topologically sort agents so each runs after roles it depends on.

    Falls back to the architect's original order for any agent whose deps are
    unknown or cyclic -- ordering is a helpful hint, never a hard failure.
    """
    by_role = {a.role: a for a in agents}
    ordered: List[Agent] = []
    placed = set()

    def place(agent, trail):
        if agent.role in placed or agent.role in trail:
            return
        trail = trail | {agent.role}
        for dep in agent.spec.depends_on:
            dep_agent = by_role.get(dep)
            if dep_agent is not None:
                place(dep_agent, trail)
        if agent.role not in placed:
            ordered.append(agent)
            placed.add(agent.role)

    for a in agents:
        place(a, set())
    return ordered


def run_team(provider: Provider, agents: List[Agent], goal: str, kb: KnowledgeBase,
             handoff: bool = True):
    """Yield (agent, output) as each agent completes -- a step boundary.

    Agents run in dependency order. Each agent receives the artifacts of the
    roles it depends on (or, absent declared deps, a digest of recent work),
    so work composes instead of every agent starting cold from the goal.
    """
    artifacts: dict = {}            # shared tool workspace for the whole team
    outputs_by_role: dict = {}      # role -> its output, for dependency handoff
    recent: List[str] = []
    for agent in order_by_dependencies(agents):
        if agent.status != AgentStatus.ALIVE:
            continue
        if not handoff:
            peer = ""
        elif agent.spec.depends_on:
            # Hand off exactly the artifacts this agent declared it needs.
            peer = "\n\n".join(
                f"[{dep}] {outputs_by_role[dep][:600]}"
                for dep in agent.spec.depends_on if dep in outputs_by_role
            )
        else:
            peer = "\n\n".join(recent[-3:])
        output = run_agent(provider, agent, goal, kb, peer_context=peer,
                           artifacts=artifacts)
        outputs_by_role[agent.role] = output
        recent.append(f"[{agent.spec.role}] {output[:600]}")
        yield agent, output
