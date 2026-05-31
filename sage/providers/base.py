"""The model-agnostic boundary.

Every reasoning call in SAGE goes through this interface. The orchestrator,
the architect, the agents, and the Gardener never know which model is
underneath -- that is the whole point.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Provider(ABC):
    """A reasoning backend. Implementations wrap a concrete model."""

    name: str = "base"

    @abstractmethod
    def reason(
        self,
        task: str,
        context: str = "",
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        """Return the model's text response for a task given some context."""
        raise NotImplementedError

    def reason_json(
        self,
        task: str,
        context: str = "",
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> Any:
        """Reason and parse a JSON object/array out of the response.

        Tolerant of models that wrap JSON in prose or code fences.
        """
        raw = self.reason(task, context=context, system=system, max_tokens=max_tokens)
        return extract_json(raw)


def extract_json(text: str) -> Any:
    """Best-effort extraction of the first JSON value in a string."""
    text = text.strip()
    # Strip code fences if present.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced { } or [ ] span.
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"No JSON found in model response:\n{text[:500]}")
