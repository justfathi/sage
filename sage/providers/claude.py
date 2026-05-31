"""Claude reasoning provider (Anthropic SDK).

Used automatically when ANTHROPIC_API_KEY is set. Prompt caching is applied
to the system prompt so repeated calls in a run stay cheap.
"""

from __future__ import annotations

import os
from typing import Optional

from .base import Provider

# Default to the latest capable Claude model; override with SAGE_MODEL.
DEFAULT_MODEL = "claude-opus-4-8"


class ClaudeProvider(Provider):
    name = "claude"

    def __init__(self, model: Optional[str] = None):
        import anthropic  # imported lazily so the mock path needs no SDK

        self.model = model or os.environ.get("SAGE_MODEL", DEFAULT_MODEL)
        self.client = anthropic.Anthropic()

    def reason(
        self,
        task: str,
        context: str = "",
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        system = system or (
            "You are a precise reasoning engine inside SAGE, a system that "
            "designs and grows teams of AI agents from a company's context. "
            "Answer exactly what is asked. When asked for JSON, return only JSON."
        )
        user = task if not context else f"{task}\n\n--- CONTEXT ---\n{context}"

        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
