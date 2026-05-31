"""The Gardener -- agent lifecycle as a dedicated, SAGE-native role.

It prunes dead/underperforming agents, flags ones to retrain, and surfaces
gaps for the Architect to grow new branches. "Underperforming" is a
judgment, not a fixed threshold: a reasoning call decides, in context.

MVP scope: mark agents dead / alive / retraining. It gets better later by
observing the outcomes of its own past decisions.
"""

from __future__ import annotations

import json
from typing import Dict, List

from ..providers.base import Provider
from .models import Agent, AgentStatus


SYSTEM = (
    "You are the Gardener inside SAGE. Decide each agent's fate from its "
    "performance: keep, retrain, or prune. Use judgement, not fixed rules."
)


def review(provider: Provider, agents: List[Agent]) -> List[Dict]:
    roster = [
        {"role": a.role, "score": a.score, "notes": a.notes,
         "outputs": len(a.outputs)}
        for a in agents
    ]
    task = (
        "Evaluate the roster and decide each agent's fate. For each, return "
        '{"role", "verdict": "keep"|"retrain"|"prune", "reason"}.\n\n'
        f"Roster:\n{json.dumps(roster, indent=2)}"
    )
    try:
        decisions = provider.reason_json(task, system=SYSTEM, max_tokens=1024)
        if not isinstance(decisions, list):
            decisions = decisions.get("decisions", [])
    except Exception:
        decisions = [{"role": a.role, "verdict": "keep", "reason": "default"} for a in agents]

    by_role = {a.role.lower(): a for a in agents}
    applied: List[Dict] = []
    for d in decisions:
        agent = by_role.get(str(d.get("role", "")).lower())
        if not agent:
            continue
        verdict = d.get("verdict", "keep")
        if verdict == "prune":
            agent.status = AgentStatus.DEAD
        elif verdict == "retrain":
            agent.status = AgentStatus.RETRAINING
        agent.notes = d.get("reason", "")
        applied.append({"role": agent.role, "verdict": verdict,
                        "reason": agent.notes, "status": agent.status.value})
    return applied
