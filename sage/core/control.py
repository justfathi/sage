"""The human-in-the-loop control plane.

Pause logic does NOT live in the UI. It lives here, in the orchestration
layer. UI / Slack / API are all just clients that flip the same flags.
SAGE checks one place -- "am I paused?" -- at every step boundary, which is
the same moment it writes a checkpoint.

Gates are pre-set policy (e.g. "always stop before spawning") so SAGE is
not blocked on every routine cycle; the interrupt handles exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Set


@dataclass
class ControlPlane:
    instance_id: str
    _paused: bool = False
    # Gate names that should halt for approval, e.g. {"before_spawn"}.
    gates: Set[str] = field(default_factory=set)
    # Injected approval hook; returns True to proceed. Defaults to auto-approve.
    approver: Optional[Callable[[str, dict], bool]] = None
    # Injected pause-wait hook (e.g. block until a UI resume). Defaults to no-op.
    on_pause: Optional[Callable[[str], None]] = None

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused

    def checkpoint_barrier(self) -> None:
        """Called at each step boundary. Blocks while paused."""
        if self._paused and self.on_pause:
            self.on_pause(self.instance_id)

    def gate(self, name: str, detail: Optional[Dict] = None) -> bool:
        """Return True to proceed past a named gate."""
        if name not in self.gates:
            return True
        if self.approver:
            return self.approver(name, detail or {})
        return True  # auto-approve when no approver is wired
