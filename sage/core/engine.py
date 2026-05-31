"""The thin loop -- the heart of SAGE.

Turns a goal + a company's documents into a working, self-correcting team:
ingest -> architect -> spawn -> execute -> learn. Every meaningful step
writes one event to the activity log; pause checks and checkpoints land at
the same step boundaries.

This is the ~"few hundred lines, not a mountain" layer we own instead of
depending on a framework.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from ..providers import get_provider
from ..providers.base import Provider
from . import architect as architect_mod
from . import executor as executor_mod
from . import gardener as gardener_mod
from . import playbook as playbook_mod
from .control import ControlPlane
from .events import ActivityLog
from .memory import KnowledgeBase
from .models import Agent, Event, EventStatus


@dataclass
class RunResult:
    instance_id: str
    goal: str
    methodology: Optional[str]
    agents: List[Agent] = field(default_factory=list)
    insights: dict = field(default_factory=dict)


class SageEngine:
    """One engine drives one instance (= one company's digital DNA)."""

    def __init__(
        self,
        provider: Optional[Provider] = None,
        db_path: str = "sage_state.db",
        instance_id: Optional[str] = None,
        on_event=None,
    ):
        self.instance_id = instance_id or str(uuid.uuid4())
        self.provider = provider or get_provider()
        self.kb = KnowledgeBase()
        self.log = ActivityLog(db_path=db_path, on_append=on_event)
        self.control = ControlPlane(instance_id=self.instance_id)
        # Roles SAGE discovered it was missing, carried across cycles.
        self.discovered_roles: List[str] = []
        # Roles the Gardener pruned -- don't keep re-growing dead weight.
        self.pruned_roles: List[str] = []
        # If resuming a known instance, rehydrate what it already learned from
        # the activity log -- the log is the source of truth, so a restart does
        # not forget. This is what lets one sealed instance keep getting
        # smarter across process restarts.
        if instance_id:
            self._rehydrate()

    def _rehydrate(self) -> None:
        """Rebuild in-memory learning state from the persisted log."""
        learned_learnings: List[str] = []
        for ev in self.log.events(self.instance_id):
            if ev.action == "ingested_doc":
                p = ev.payload or {}
                if p.get("text") and p.get("source"):
                    self.kb.ingest_text(p["source"], p["text"])
            elif ev.action == "learned":
                for role in (ev.payload or {}).get("suggested_roles", []):
                    if role and role not in self.discovered_roles:
                        self.discovered_roles.append(role)
                for ins in (ev.payload or {}).get("insights", []):
                    learned_learnings.append(ins)
            elif ev.action == "lifecycle":
                p = ev.payload or {}
                if p.get("verdict") == "prune" and p.get("role"):
                    if p["role"] not in self.pruned_roles:
                        self.pruned_roles.append(p["role"])
        if learned_learnings:
            # Restore the fed-back learnings into the knowledge base too.
            self.kb.ingest_text("learnings", "\n".join(learned_learnings))

    # -- logging helper --------------------------------------------------

    def _emit(self, actor, action, summary, payload=None, checkpoint=False,
              status=EventStatus.COMPLETED, parent_id=None) -> Event:
        return self.log.append(
            Event(
                actor=actor, action=action, summary=summary,
                instance_id=self.instance_id, payload=payload or {},
                checkpoint=checkpoint, status=status, parent_id=parent_id,
            )
        )

    # -- the four layers -------------------------------------------------

    def ingest(self, path: str) -> int:
        from pathlib import Path

        p = Path(path)
        files = [p] if p.is_file() else sorted(
            f for f in p.rglob("*") if f.suffix.lower() in {".md", ".txt"}
        )
        added = 0
        for f in files:
            text = f.read_text(encoding="utf-8")
            # Persist the raw source so a resumed instance can rebuild its KB
            # from the log alone -- the log is the durable store of record.
            n = self.kb.ingest_text(f.name, text)
            added += n
            self._emit("SAGE-Core", "ingested_doc",
                       f"Ingested {f.name} ({n} chunks)",
                       payload={"source": f.name, "text": text, "chunks": n},
                       checkpoint=True)
        self._emit("SAGE-Core", "ingested",
                   f"Ingested {added} chunks ({self.kb.summary()})",
                   payload={"path": path, "chunks": added}, checkpoint=True)
        return added

    def run(self, goal: str) -> RunResult:
        self._emit("SAGE-Core", "goal_received", f"Goal: {goal}",
                   payload={"goal": goal}, checkpoint=True)

        # (1) match a methodology from the playbook
        self.control.checkpoint_barrier()
        method = playbook_mod.match(self.provider, goal, self.kb.context_for(goal))
        self._emit(
            "SAGE-Core", "methodology_matched",
            f"Methodology: {method.name}" if method else "No methodology fit -> design from scratch",
            payload={"methodology": method.name if method else None}, checkpoint=True,
        )

        # (2) architect the team -- carrying forward any roles SAGE has
        # discovered it was missing in prior cycles.
        self.control.checkpoint_barrier()
        carried = list(self.discovered_roles)
        # Pruned roles stay pruned unless they were since re-discovered as a gap.
        avoid = [r for r in self.pruned_roles if r not in carried]
        specs = architect_mod.design_team(
            self.provider, goal, self.kb, method,
            discovered_roles=carried, avoid_roles=avoid,
        )
        arch_event = self._emit(
            "SAGE-Core", "architected",
            f"Designed {len(specs)} roles: " + ", ".join(s.role for s in specs),
            payload={"specs": [s.to_dict() for s in specs],
                     "grown_from_discovery": carried}, checkpoint=True,
        )
        for role in carried:
            if any(s.role == role for s in specs):
                self._emit("SAGE-Core", "grew_role",
                           f"Grew discovered role: {role}",
                           payload={"role": role}, checkpoint=True)

        # (3) gate, then spawn & execute
        if not self.control.gate("before_spawn", {"roles": [s.role for s in specs]}):
            self._emit("SAGE-Core", "halted", "Human declined the proposed team",
                       status=EventStatus.PAUSED, checkpoint=True)
            return RunResult(self.instance_id, goal,
                             method.name if method else None, [], {})

        agents = [executor_mod.spawn(s) for s in specs]
        for a in agents:
            self._emit("SAGE-Core", "spawned", f"Spawned {a.role}",
                       payload={"agent_id": a.agent_id, "role": a.role},
                       parent_id=arch_event.event_id, checkpoint=True)

        for agent, output in executor_mod.run_team(self.provider, agents, goal, self.kb):
            self.control.checkpoint_barrier()  # step boundary
            self._emit(f"agent:{agent.role}", "worked",
                       f"{agent.role}: {output[:90]}",
                       payload={"agent_id": agent.agent_id, "score": agent.score,
                                "output": output},
                       parent_id=arch_event.event_id, checkpoint=True)

        # (4) learn + gardener
        self.control.checkpoint_barrier()
        decisions = gardener_mod.review(self.provider, agents)
        for d in decisions:
            self._emit("Gardener", "lifecycle",
                       f"{d['role']}: {d['verdict']} ({d['status']})",
                       payload=d, checkpoint=True)
            # Remember pruned roles so future cycles don't re-grow dead weight.
            if d.get("verdict") == "prune" and d["role"] not in self.pruned_roles:
                self.pruned_roles.append(d["role"])

        # Act on "retrain": give each flagged agent a second, critique-guided
        # attempt. This is the lifecycle decision finally taking effect, not
        # just being logged.
        by_role = {a.role: a for a in agents}
        for d in decisions:
            if d.get("verdict") != "retrain":
                continue
            agent = by_role.get(d["role"])
            if not agent:
                continue
            self.control.checkpoint_barrier()
            before = agent.score
            executor_mod.retrain_agent(self.provider, agent, goal, self.kb)
            recovered = agent.status.value == "alive"
            self._emit(
                "Gardener", "retrained",
                f"{agent.role}: {before:.2f} -> {agent.score:.2f} "
                f"({'recovered' if recovered else 'still weak'})",
                payload={"role": agent.role, "before": before,
                         "after": agent.score, "recovered": recovered},
                checkpoint=True,
            )

        insights = self._learn(goal, agents)
        self._emit("SAGE-Core", "learned",
                   "Updated knowledge from this cycle",
                   payload=insights, checkpoint=True)

        return RunResult(self.instance_id, goal,
                         method.name if method else None, agents, insights)

    def run_cycles(self, goal: str, cycles: int = 1) -> List[RunResult]:
        """Run the loop repeatedly on the same goal.

        This is the core thesis in motion: because each cycle feeds its
        learnings back into the knowledge base (see `_learn`), later cycles
        reason over a richer context. One sealed instance should get sharper
        over time -- the experiment instance isolation is meant to prove.
        """
        results: List[RunResult] = []
        for n in range(1, cycles + 1):
            self._emit("SAGE-Core", "cycle_started",
                       f"Cycle {n}/{cycles}",
                       payload={"cycle": n, "kb": self.kb.summary()}, checkpoint=True)
            results.append(self.run(goal))
        return results

    def _learn(self, goal: str, agents: List[Agent]) -> dict:
        digest = "\n".join(f"{a.role}: {a.outputs[-1] if a.outputs else ''}" for a in agents)
        try:
            insights = self.provider.reason_json(
                f"Extract insights and suggested new roles from this cycle "
                f"for goal '{goal}'. Return JSON with 'insights' and "
                f"'suggested_roles'.",
                context=digest, max_tokens=512,
            )
        except Exception:
            insights = {"insights": [], "suggested_roles": []}
        # Feed learnings back into the knowledge base (closing the loop).
        if isinstance(insights, dict) and insights.get("insights"):
            self.kb.ingest_text("learnings", "\n".join(insights["insights"]))
        # Remember any newly suggested roles so the next cycle can grow them.
        if isinstance(insights, dict):
            for role in insights.get("suggested_roles", []):
                if role and role not in self.discovered_roles:
                    self.discovered_roles.append(role)
        return insights if isinstance(insights, dict) else {}

    def close(self) -> None:
        self.log.close()
