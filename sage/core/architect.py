"""The Architect -- SAGE Core's team-design step.

Reads the knowledge base and a goal, optionally steered by a matched
methodology from the playbook, and emits a list of AgentSpecs: the roles
SAGE will spawn. Designs lean, single-purpose agents and is free to invent
new role archetypes the situation demands.
"""

from __future__ import annotations

from typing import List, Optional

from ..providers.base import Provider
from .memory import KnowledgeBase
from .models import AgentSpec
from .playbook import Methodology


SYSTEM = (
    "You are the Architect inside SAGE. Given a goal and company context, "
    "design the smallest team of single-purpose agents that can achieve it. "
    "Invent new roles where the situation demands. Return only JSON."
)


def design_team(
    provider: Provider,
    goal: str,
    kb: KnowledgeBase,
    methodology: Optional[Methodology] = None,
    discovered_roles: Optional[List[str]] = None,
    avoid_roles: Optional[List[str]] = None,
) -> List[AgentSpec]:
    context = kb.context_for(goal, k=6)
    steer = ""
    if methodology:
        steer = (
            f"\nUse the {methodology.name} methodology as a starting crew "
            f"({methodology.crew_hint}), then add any roles it lacks."
        )
    if discovered_roles:
        steer += (
            "\nPrior cycles discovered these roles were missing; include them: "
            + ", ".join(discovered_roles)
        )
    if avoid_roles:
        steer += (
            "\nThe Gardener pruned these roles as ineffective; do NOT include "
            "them: " + ", ".join(avoid_roles)
        )

    task = (
        "Design the team of agents (roles) needed to achieve this goal."
        f"{steer}\n\nGoal: {goal}\n\n"
        "Return a JSON array; each item: "
        '{"role", "purpose", "tools": [..], "success_criteria", '
        '"methodology": <name|null>}.'
    )

    try:
        raw = provider.reason_json(task, context=context, system=SYSTEM, max_tokens=2048)
    except Exception:
        raw = []

    if isinstance(raw, dict):
        raw = raw.get("roles") or raw.get("agents") or raw.get("team") or []

    specs: List[AgentSpec] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("role"):
            continue
        specs.append(
            AgentSpec(
                role=str(item["role"]),
                purpose=str(item.get("purpose", "")),
                context_refs=list(item.get("context_refs", [])),
                tools=list(item.get("tools", [])),
                success_criteria=str(item.get("success_criteria", "")),
                methodology=item.get("methodology") or (methodology.name if methodology else None),
            )
        )

    # Safety net: never return an empty team.
    if not specs:
        specs = [
            AgentSpec(role="Analyst", purpose=f"break down: {goal}",
                      tools=["read_kb"], success_criteria="goal decomposed"),
            AgentSpec(role="Executor", purpose=f"carry out: {goal}",
                      tools=["read_kb", "write_doc"], success_criteria="work completed"),
        ]

    # Grow any discovered roles the model didn't already include. This is the
    # learning loop closing: a role suggested in a prior cycle becomes a real
    # new branch on the tree.
    if discovered_roles:
        present = {s.role.lower() for s in specs}
        for role in discovered_roles:
            if role.lower() not in present:
                specs.append(
                    AgentSpec(
                        role=role,
                        purpose=f"fill the gap SAGE discovered: {role}",
                        tools=["read_kb"],
                        success_criteria="closes the identified gap",
                        methodology=None,
                    )
                )
                present.add(role.lower())

    # Enforce the Gardener's prune decisions: drop any role it killed, so the
    # loop actually shapes future teams instead of re-growing dead weight.
    if avoid_roles:
        avoid = {r.lower() for r in avoid_roles}
        specs = [s for s in specs if s.role.lower() not in avoid]
        if not specs:  # never hand back an empty team
            specs = [AgentSpec(role="Analyst", purpose=f"break down: {goal}",
                               tools=["read_kb"], success_criteria="goal decomposed")]
    return specs
