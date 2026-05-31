"""Core data shapes for SAGE.

These mirror the structures described in ARCHITECTURE.md and
IMPLEMENTATION.md. An "agent" is a scoped, persistent record -- not a
magic object. An event is one flat shape that serves both the human
status feed and machine recovery.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentStatus(str, Enum):
    ALIVE = "alive"
    DEAD = "dead"
    RETRAINING = "retraining"


class EventStatus(str, Enum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class AgentSpec:
    """The Architect's design for one agent: a role and how to fill it."""

    role: str
    purpose: str
    context_refs: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    success_criteria: str = ""
    # Set when this role came from a playbook methodology (e.g. "BMAD").
    methodology: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Agent:
    """A spawned, persistent agent instance."""

    spec: AgentSpec
    agent_id: str = field(default_factory=_uuid)
    status: AgentStatus = AgentStatus.ALIVE
    outputs: List[str] = field(default_factory=list)
    # Lightweight performance signal the Gardener reasons over.
    score: float = 0.0
    notes: str = ""
    # Tools the agent actually invoked during its run.
    tools_used: List[str] = field(default_factory=list)

    @property
    def role(self) -> str:
        return self.spec.role

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "score": self.score,
            "notes": self.notes,
            "outputs": self.outputs,
            "tools_used": self.tools_used,
        }
        d.update(self.spec.to_dict())
        return d


@dataclass
class Event:
    """One entry in the append-only activity log.

    `summary` powers the human status feed; `payload` + `status` +
    `checkpoint` make it machine-resumable; `parent_id` threads the
    tree of work.
    """

    actor: str
    action: str
    summary: str
    instance_id: str
    event_id: str = field(default_factory=_uuid)
    timestamp: str = field(default_factory=_now)
    status: EventStatus = EventStatus.COMPLETED
    parent_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    checkpoint: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d
