"""Minimal .env loader -- stdlib only, zero dependencies.

Loads KEY=VALUE lines from a .env file into os.environ if not already set.
Existing environment variables always win, so an explicit `export` overrides
the file. Quotes are stripped; blank lines and `#` comments are ignored.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def load_dotenv(path: Optional[str] = None) -> int:
    """Load a .env file. Returns the number of vars set. Never overrides
    a variable already present in the environment."""
    p = Path(path) if path else _find_dotenv()
    if not p or not p.is_file():
        return 0
    loaded = 0
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val
            loaded += 1
    return loaded


def _find_dotenv() -> Optional[Path]:
    """Walk up from the current directory looking for a .env file."""
    here = Path.cwd()
    for d in [here, *here.parents]:
        candidate = d / ".env"
        if candidate.is_file():
            return candidate
    return None
