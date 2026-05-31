"""Offline, deterministic mock provider.

Lets the entire SAGE loop run end-to-end with no API key and no network.
It inspects the task to decide what kind of structured answer to return,
so the demo produces believable specs, outputs, and lifecycle decisions.

This is a stand-in for reasoning -- not real intelligence. Set
ANTHROPIC_API_KEY to swap in real Claude with zero code changes.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional

from .base import Provider


def _keywords(text: str, n: int = 6) -> List[str]:
    stop = {
        "the", "a", "an", "to", "of", "and", "for", "with", "our", "we",
        "want", "need", "this", "that", "their", "them", "from", "into",
        "build", "new", "all", "have", "has", "are", "is", "be", "on", "in",
    }
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    seen, out = set(), []
    for w in words:
        if w in stop or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= n:
            break
    return out


class MockProvider(Provider):
    name = "mock"

    def reason(
        self,
        task: str,
        context: str = "",
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        t = task.lower()

        # Route on the INSTRUCTION (which always opens the task), most specific
        # first, so words that merely appear inside an embedded payload (a
        # role's purpose, an artifact, a roster) never cause a misroute.
        if t.startswith("perform your role") or t.startswith("re-do your work"):
            return self._agent_work(task, context)
        if t.startswith("evaluate this artifact"):
            return self._evaluate(task, context)
        if "match the goal to one methodology" in t:
            return self._match_methodology(task, context)
        if t.startswith("design the team of agents"):
            return self._design_team(task, context)
        if "decide each agent" in t or "agent's fate" in t or t.startswith("evaluate the roster"):
            return self._gardener(task, context)
        if "extract insights" in t:
            return self._insights(task, context)
        return "Acknowledged."

    # -- intent handlers -------------------------------------------------

    def _match_methodology(self, task: str, context: str) -> str:
        # Inspect the GOAL + company context only -- never the catalog text in
        # the prompt (which names software methodologies and would falsely match).
        m = re.search(r"goal:\s*(.+)", task, re.IGNORECASE)
        goal = (m.group(1) if m else "").lower()
        blob = (goal + " " + context).lower()
        software = any(
            k in blob for k in
            ("api", "app", "software", "code", "backend", "frontend", "tender", "platform")
        )
        if not software:
            return json.dumps({"methodology": None})
        # MetaGPT fits a short greenfield brief ("from scratch", a one-liner);
        # BMAD fits a documented rebuild/migration with rich context.
        greenfield = any(
            k in blob for k in ("from scratch", "greenfield", "prototype", "mvp", "brief")
        )
        chosen = "MetaGPT" if (greenfield and len(context) < 400) else "BMAD"
        return json.dumps({"methodology": chosen})

    def _design_team(self, task: str, context: str) -> str:
        blob = (task + " " + context).lower()
        kws = _keywords(task + " " + context)
        focus = ", ".join(kws[:3]) or "the goal"

        if "metagpt" in blob:
            # MetaGPT's lean simulated-software-company crew.
            specs = [
                {"role": "PM", "purpose": f"turn the brief into a PRD for {focus}",
                 "tools": ["read_kb", "write_doc"], "success_criteria": "PRD written",
                 "methodology": "MetaGPT"},
                {"role": "Architect", "purpose": "design the system from the PRD",
                 "tools": ["read_kb", "write_doc"], "success_criteria": "design drafted",
                 "methodology": "MetaGPT"},
                {"role": "Engineer", "purpose": "implement the design",
                 "tools": ["write_file", "run_tests"], "success_criteria": "feature works",
                 "methodology": "MetaGPT"},
                {"role": "QA", "purpose": "test the implementation",
                 "tools": ["run_tests"], "success_criteria": "no critical defects",
                 "methodology": "MetaGPT"},
            ]
        elif "bmad" in blob or any(
            k in blob for k in ("api", "app", "software", "code", "tender")
        ):
            specs = [
                {"role": "Analyst", "purpose": f"extract requirements for {focus}",
                 "tools": ["read_kb"], "success_criteria": "requirements captured",
                 "methodology": "BMAD"},
                {"role": "Architect", "purpose": "design the system & API shape",
                 "tools": ["read_kb", "write_doc"], "success_criteria": "architecture drafted",
                 "methodology": "BMAD"},
                {"role": "Builder", "purpose": "implement against the spec",
                 "tools": ["write_file", "run_tests"], "success_criteria": "passes spec suite",
                 "methodology": "BMAD"},
                {"role": "QA", "purpose": "validate behaviour & edge cases",
                 "tools": ["run_tests"], "success_criteria": "no critical defects",
                 "methodology": "BMAD"},
                {"role": "ContextKeeper", "purpose": "maintain shared knowledge across agents",
                 "tools": ["read_kb", "write_kb"], "success_criteria": "no knowledge gaps",
                 "methodology": None},
            ]
        else:
            specs = [
                {"role": "Analyst", "purpose": f"break down {focus}",
                 "tools": ["read_kb"], "success_criteria": "decomposed into tasks",
                 "methodology": None},
                {"role": "Executor", "purpose": f"carry out the work on {focus}",
                 "tools": ["read_kb", "write_doc"], "success_criteria": "tasks completed",
                 "methodology": None},
                {"role": "Reviewer", "purpose": "check quality of the output",
                 "tools": ["read_kb"], "success_criteria": "meets the bar",
                 "methodology": None},
            ]
        return json.dumps(specs, indent=2)

    def _agent_work(self, task: str, context: str) -> str:
        role = "agent"
        m = re.search(r"role:\s*([A-Za-z]+)", task)
        if m:
            role = m.group(1)
        kws = _keywords(context or task)
        topic = ", ".join(kws[:3]) or "the goal"
        return (
            f"[{role}] completed its pass on {topic}. "
            f"Produced a concrete artifact and flagged 1 open dependency."
        )

    def _evaluate(self, task: str, context: str) -> str:
        # Deterministic but varied per role, so the Gardener gets real signal
        # offline: weaker-sounding roles score lower and trip retrain/prune.
        m = re.search(r"role:\s*([A-Za-z][\w /&()-]*)", task)
        role = (m.group(1).strip() if m else "agent").lower()
        if any(k in role for k in ("qa", "reviewer", "validator")):
            score = 0.55      # mid -> retrain band
        elif "context" in role or "idler" in role:
            score = 0.4       # low -> prune band
        else:
            score = 0.8       # solid -> keep
        # A critique-guided retry improves: reward the second attempt so
        # "retrain" can actually recover an agent.
        if "revised attempt" in task.lower():
            score = min(1.0, score + 0.25)
        return json.dumps({"score": score, "reason": f"{role} artifact assessed"})

    def _gardener(self, task: str, context: str) -> str:
        # The roster is passed in the task as a JSON list of
        # {"role", "score", "notes", "outputs"} objects. Decide by performance
        # rather than a hardcoded rule -- judgment, not a fixed threshold.
        blob = task + " " + context
        try:
            roster = json.loads(re.search(r"\[.*\]", blob, re.DOTALL).group(0))
        except Exception:
            roster = []

        decisions = []
        for entry in roster:
            if not isinstance(entry, dict) or "role" not in entry:
                continue
            role = entry["role"]
            score = float(entry.get("score", 0.5) or 0.0)
            produced = int(entry.get("outputs", 0) or 0)
            if produced == 0 or score < 0.45:
                verdict, why = "prune", f"{role} produced too little (score {score:.2f})"
            elif score < 0.62:
                verdict, why = "retrain", f"{role} underperforming (score {score:.2f})"
            else:
                verdict, why = "keep", f"{role} performing well (score {score:.2f})"
            decisions.append({"role": role, "verdict": verdict, "reason": why})

        if not decisions:
            # Fall back to scanning bare role names if no structured roster.
            for role in re.findall(r'"role":\s*"([^"]+)"', blob):
                decisions.append({"role": role, "verdict": "keep",
                                  "reason": "no performance data"})
        if not decisions:
            decisions = [{"role": "unknown", "verdict": "keep", "reason": "no data"}]
        return json.dumps(decisions, indent=2)

    def _insights(self, task: str, context: str) -> str:
        kws = _keywords(context or task)
        return json.dumps(
            {
                "insights": [
                    f"Recurring theme: {kws[0] if kws else 'scope'} needs tighter definition.",
                    "A bridging role would reduce hand-off friction.",
                ],
                "suggested_roles": ["BridgeAgent"],
            },
            indent=2,
        )
