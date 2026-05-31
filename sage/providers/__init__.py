"""Model-agnostic reasoning providers.

Everything in SAGE reasons through `Provider.reason(...)` and never names
a model directly. Swap the provider, keep the system.

`get_provider()` auto-selects: real Claude when ANTHROPIC_API_KEY is set,
otherwise the offline deterministic mock so the whole loop runs with no
external dependencies.
"""

from __future__ import annotations

import os
from typing import Optional

from ..core.env import load_dotenv
from .base import Provider
from .mock import MockProvider


def get_provider(name: Optional[str] = None) -> Provider:
    # Pick up a local .env (e.g. ANTHROPIC_API_KEY) without overriding any
    # variable already exported in the environment.
    load_dotenv()
    name = name or os.environ.get("SAGE_PROVIDER")
    if name == "mock":
        return MockProvider()
    if name == "claude" or (name is None and os.environ.get("ANTHROPIC_API_KEY")):
        try:
            from .claude import ClaudeProvider

            return ClaudeProvider()
        except Exception as exc:  # pragma: no cover - fall back gracefully
            print(f"[sage] Claude provider unavailable ({exc}); using mock.")
            return MockProvider()
    return MockProvider()


__all__ = ["Provider", "MockProvider", "get_provider"]
