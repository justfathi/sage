"""The playbook -- SAGE's registry of known methodologies.

Methodologies are opinionated crews + workflows, tagged by goal type. SAGE
matches a goal to one (e.g. BMAD for software delivery) instead of always
designing from scratch. The registry is pluggable: BMAD proves the slot
works, it is not the engine.

Note the layering: these are what SAGE *deploys for the customer's work*,
not the tools we build SAGE itself out of.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..providers.base import Provider


@dataclass
class Methodology:
    name: str
    fits: str          # human description of when it applies
    crew_hint: str     # roles it brings, to steer the architect


REGISTRY: List[Methodology] = [
    Methodology(
        name="BMAD",
        fits="software delivery: building or rebuilding an app/API/system",
        crew_hint="Analyst -> PM -> Architect -> Scrum Master -> Dev -> QA",
    ),
    Methodology(
        name="MetaGPT",
        fits="software delivery from a short brief via simulated software company",
        crew_hint="PM -> Architect -> Engineer -> QA",
    ),
]


def match(provider: Provider, goal: str, kb_context: str = "") -> Optional[Methodology]:
    """Ask the reasoning layer whether a known methodology fits the goal."""
    names = ", ".join(m.name for m in REGISTRY)
    catalog = "\n".join(f"- {m.name}: {m.fits}" for m in REGISTRY)
    task = (
        "Match the goal to one methodology from the playbook, or null if none "
        f"fit. Available: {names}.\n\nCatalog:\n{catalog}\n\nGoal: {goal}\n\n"
        'Return JSON: {"methodology": "<name>" | null}'
    )
    try:
        result = provider.reason_json(task, context=kb_context, max_tokens=200)
        chosen = (result or {}).get("methodology")
    except Exception:
        chosen = None
    if not chosen:
        return None
    for m in REGISTRY:
        if m.name.lower() == str(chosen).lower():
            return m
    return None
