"""State reconstruction from the activity log.

The architecture's signature claim: the log is not just for humans to watch,
it *is* the source of truth for state. This module proves it -- given only an
instance's event stream, it reconstructs what happened: the goal, the matched
methodology, the roster and each agent's fate, the last safe checkpoint, and
which phase a run reached.

This is what a resume would read to "look back at what we were doing and
continue from there."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .events import ActivityLog
from .models import Event


# Ordered phases of a run, inferred from event actions.
PHASE_ORDER = [
    "cycle_started", "goal_received", "methodology_matched", "architected",
    "grew_role", "spawned", "worked", "lifecycle", "learned",
]


@dataclass
class ReconstructedState:
    instance_id: str
    goal: Optional[str] = None
    methodology: Optional[str] = None
    roster: Dict[str, str] = field(default_factory=dict)  # role -> status
    phase: Optional[str] = None
    last_checkpoint_summary: Optional[str] = None
    event_count: int = 0
    complete: bool = False

    def describe(self) -> str:
        lines = [
            f"instance: {self.instance_id}",
            f"goal: {self.goal}",
            f"methodology: {self.methodology or 'none (from scratch)'}",
            f"phase reached: {self.phase}",
            f"complete: {self.complete}",
            f"events: {self.event_count}",
            f"last checkpoint: {self.last_checkpoint_summary}",
            "roster:",
        ]
        for role, status in self.roster.items():
            lines.append(f"  {role:<14} {status}")
        return "\n".join(lines)


def reconstruct(log: ActivityLog, instance_id: str) -> ReconstructedState:
    events: List[Event] = log.events(instance_id)
    state = ReconstructedState(instance_id=instance_id, event_count=len(events))

    seen_phases = set()
    for e in events:
        if e.action == "goal_received":
            state.goal = e.payload.get("goal")
        elif e.action == "methodology_matched":
            state.methodology = e.payload.get("methodology")
        elif e.action == "spawned":
            role = e.payload.get("role")
            if role:
                state.roster.setdefault(role, "alive")
        elif e.action == "lifecycle":
            role = e.payload.get("role")
            if role:
                state.roster[role] = e.payload.get("status", "alive")
        if e.action in PHASE_ORDER:
            seen_phases.add(e.action)
        if e.checkpoint:
            state.last_checkpoint_summary = e.summary

    # Phase reached = furthest phase in canonical order that we saw.
    for phase in PHASE_ORDER:
        if phase in seen_phases:
            state.phase = phase
    state.complete = "learned" in seen_phases
    return state
