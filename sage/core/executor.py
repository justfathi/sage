"""Spawn & execute -- turn specs into working agents and run them.

Each agent run is just a scoped reasoning call: load its context, ask the
model to perform its role, capture the output. Nothing exotic.
"""

from __future__ import annotations

from typing import List, Optional

from ..providers.base import Provider
from . import evaluator as evaluator_mod
from .models import Agent, AgentSpec, AgentStatus
from .memory import KnowledgeBase


def spawn(spec: AgentSpec) -> Agent:
    return Agent(spec=spec)


AGENT_SYSTEM = (
    "You are a single-purpose agent inside SAGE. Stay strictly within your "
    "role. Produce one concrete artifact and note any open dependency."
)


def run_agent(provider: Provider, agent: Agent, goal: str, kb: KnowledgeBase,
              peer_context: str = "") -> str:
    query = f"{agent.spec.role} {agent.spec.purpose} {goal}"
    context = kb.context_for(query, k=4)
    if peer_context:
        # Hand off prior agents' artifacts so work builds on work.
        context = f"{context}\n\n--- UPSTREAM AGENT OUTPUTS ---\n{peer_context}"
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


def run_team(provider: Provider, agents: List[Agent], goal: str, kb: KnowledgeBase,
             handoff: bool = True):
    """Yield (agent, output) as each agent completes -- a step boundary.

    When `handoff` is on, each agent sees a short digest of the artifacts
    produced by the agents before it, so work composes instead of every agent
    starting cold from the goal.
    """
    done: List[str] = []
    for agent in agents:
        if agent.status != AgentStatus.ALIVE:
            continue
        peer = "\n\n".join(done[-3:]) if (handoff and done) else ""
        output = run_agent(provider, agent, goal, kb, peer_context=peer)
        # Keep a trimmed handoff note so context stays bounded.
        done.append(f"[{agent.spec.role}] {output[:600]}")
        yield agent, output
