"""Tools agents can actually use.

Until now an agent's `tools` were declarative only -- listed in its charter
but never executed. This module makes them real: a small registry of callables
an agent invokes during its run. Each tool returns a short result string that
is folded into the agent's context, so declared capability == used capability.

The set is intentionally minimal and safe (no shell, no network). It is the
boundary where a hosted SAGE would plug in richer, sandboxed tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List

from .memory import KnowledgeBase


@dataclass
class ToolContext:
    """What a tool is given when invoked."""
    kb: KnowledgeBase
    goal: str
    role: str
    purpose: str
    # Per-instance scratch space tools may read/write (e.g. produced artifacts).
    artifacts: Dict[str, str] = field(default_factory=dict)


# A tool is (name, fn). fn(ctx) -> short result string.
ToolFn = Callable[[ToolContext], str]
_REGISTRY: Dict[str, ToolFn] = {}


def tool(name: str):
    def deco(fn: ToolFn) -> ToolFn:
        _REGISTRY[name] = fn
        return fn
    return deco


@tool("read_kb")
def _read_kb(ctx: ToolContext) -> str:
    hits = ctx.kb.search(f"{ctx.role} {ctx.purpose} {ctx.goal}", k=3)
    if not hits:
        return "read_kb: knowledge base empty"
    refs = ", ".join(h.ref for h in hits)
    return f"read_kb: pulled {len(hits)} relevant chunks ({refs})"


@tool("write_kb")
def _write_kb(ctx: ToolContext) -> str:
    note = f"{ctx.role} working note for {ctx.purpose}"
    ctx.kb.ingest_text(f"agent:{ctx.role}", note)
    return "write_kb: appended a working note to the knowledge base"


@tool("write_doc")
def _write_doc(ctx: ToolContext) -> str:
    key = f"{ctx.role}.md"
    ctx.artifacts[key] = f"# {ctx.role}\n\n{ctx.purpose}\n\n(toward: {ctx.goal})"
    return f"write_doc: drafted {key}"


@tool("write_file")
def _write_file(ctx: ToolContext) -> str:
    key = f"{ctx.role.lower()}_artifact.txt"
    ctx.artifacts[key] = f"{ctx.role} artifact for {ctx.purpose}"
    return f"write_file: wrote {key}"


@tool("run_tests")
def _run_tests(ctx: ToolContext) -> str:
    produced = len(ctx.artifacts)
    return f"run_tests: checked {produced} artifact(s); no blocking failures"


def available() -> List[str]:
    return sorted(_REGISTRY)


def invoke(name: str, ctx: ToolContext) -> str:
    fn = _REGISTRY.get(name)
    if fn is None:
        return f"{name}: (no such tool; skipped)"
    try:
        return fn(ctx)
    except Exception as exc:  # a tool failing must not crash the agent
        return f"{name}: error ({exc})"


def run_tools(tool_names: List[str], ctx: ToolContext) -> List[str]:
    """Invoke each declared tool once; return their result lines."""
    return [invoke(name, ctx) for name in (tool_names or [])]
