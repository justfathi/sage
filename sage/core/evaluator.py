"""Output evaluation -- real performance signal for the Gardener.

The old heuristic scored agents by word count, which saturated to 1.0 with a
capable model (everything writes long), leaving the Gardener nothing to judge.
Instead we ask the reasoning layer to rate each artifact against the agent's
own success criteria. That score is what the Gardener prunes/retrains on.
"""

from __future__ import annotations

from typing import Dict

from ..providers.base import Provider
from .models import Agent


EVAL_SYSTEM = (
    "You are a strict quality evaluator inside SAGE. Score an agent's artifact "
    "against its stated success criteria. Be discerning: reserve high scores "
    "for genuinely complete, on-target work. Return only JSON."
)


def evaluate(provider: Provider, agent: Agent, goal: str, output: str,
             is_retry: bool = False) -> Dict:
    """Return {score: 0..1, completeness, reason} for one agent's artifact."""
    retry_note = (
        "\nThis is a revised attempt after critique; judge it on its own merits."
        if is_retry else ""
    )
    task = (
        "Evaluate this artifact. Score 0.0-1.0 on how well it meets the "
        "success criteria for the role, in service of the goal."
        f"{retry_note}\n\n"
        f"role: {agent.spec.role}\n"
        f"purpose: {agent.spec.purpose}\n"
        f"success_criteria: {agent.spec.success_criteria}\n"
        f"goal: {goal}\n\n"
        f"ARTIFACT:\n{output[:4000]}\n\n"
        'Return JSON: {"score": <float 0-1>, "reason": "<one line>"}'
    )
    try:
        result = provider.reason_json(task, system=EVAL_SYSTEM, max_tokens=300)
        if isinstance(result, list):  # tolerate a model that wraps in a list
            result = result[0] if result else {}
        score = float(result.get("score", 0.5))
        reason = str(result.get("reason", ""))
    except Exception:
        score, reason = 0.5, "evaluation unavailable"
    score = max(0.0, min(1.0, score))
    return {"score": round(score, 3), "reason": reason}
