#!/usr/bin/env python3
"""Regenerate the static GitHub Pages demo (docs/index.html).

The demo is the live dashboard (sage/web/dashboard.html) with its server
calls swapped for a player that replays a real, captured SAGE run. This
script captures that run in-process (no server needed), trims heavy fields,
embeds it, and writes docs/index.html -- so the demo never drifts from the
real dashboard.

    python scripts/build_demo.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "sage" / "web" / "dashboard.html"
OUT = ROOT / "docs" / "index.html"
DEMO_GOAL = "Rebuild our Orders Platform with a modern API"
DEMO_CYCLES = 3


def capture_timeline() -> list:
    """Run a real mock-provider SAGE instance and collect its event stream."""
    import sys
    sys.path.insert(0, str(ROOT))
    from sage.core.engine import SageEngine
    from sage.providers.mock import MockProvider

    import tempfile
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()

    events: list = []
    engine = SageEngine(provider=MockProvider(), db_path=db.name,
                        on_event=lambda e: events.append(e.to_dict()))
    engine.ingest(str(ROOT / "demo" / "sample_company"))
    engine.run_cycles(DEMO_GOAL, cycles=DEMO_CYCLES)
    events.append({"actor": "SAGE-Core", "action": "finished",
                   "summary": "All cycles complete", "checkpoint": True})
    engine.close()
    Path(db.name).unlink(missing_ok=True)
    return events


def trim(events: list) -> list:
    """Drop heavy fields the visual replay does not need."""
    for e in events:
        p = e.get("payload", {}) or {}
        p.pop("text", None)                       # raw doc text
        if "output" in p:
            p["output"] = str(p["output"])[:200]
        if "specs" in p:
            keep = ("role", "purpose", "tools", "success_criteria", "methodology")
            p["specs"] = [{k: s.get(k) for k in keep} for s in p["specs"]]
    return events


def build(timeline: list) -> str:
    html = DASHBOARD.read_text(encoding="utf-8")
    tjson = json.dumps(timeline)

    # 1) swap the server-driven boot for a self-contained player
    boot_start = html.index("  // -------- boot --------")
    boot_end = html.index("})();", boot_start)
    new_boot = (
        "  // -------- static demo player (GitHub Pages, no server) --------\n"
        "  const DEMO_TIMELINE = " + tjson + ";\n"
        "  let demoGoal = " + json.dumps(DEMO_GOAL) + ";\n"
        "  const gr = DEMO_TIMELINE.find(e => e.action === 'goal_received');\n"
        "  if (gr && gr.payload && gr.payload.goal) demoGoal = gr.payload.goal;\n"
        "  el('goalText').textContent = demoGoal;\n"
        "  let demoIdx = 0, demoTimer = null;\n"
        "  function demoStep(){\n"
        "    if (paused) return;\n"
        "    if (demoIdx >= DEMO_TIMELINE.length){\n"
        "      el('liveDot').textContent = 'Complete'; setRunUI(false);\n"
        "      clearInterval(demoTimer); demoTimer = null; return;\n"
        "    }\n"
        "    if (!replay) handle(DEMO_TIMELINE[demoIdx]);\n"
        "    else { EVENTS.push(DEMO_TIMELINE[demoIdx]); refreshScrub(); }\n"
        "    demoIdx++;\n"
        "  }\n"
        "  function startDemo(){ setRunUI(true); demoTimer = setInterval(demoStep, 280); }\n"
        "  setRoster();\n"
        "  startDemo();\n"
    )
    html = html[:boot_start] + new_boot + html[boot_end:]

    # 2) neutralize the three server fetches
    html = re.sub(
        r"    try\{\n      const r = await fetch\('/run'.*?\}catch\(_\)\{ setRunUI\(false\); \}",
        ("    el('goalInput').value=''; el('goalText').textContent = goal;\n"
         "    demoIdx = 0; if(demoTimer) clearInterval(demoTimer); startDemo();"),
        html, flags=re.DOTALL)
    html = html.replace("    await fetch(paused?'/pause':'/resume',{method:'POST'});\n", "")
    html = re.sub(
        r"    el\('docMsg'\)\.textContent='ingesting\.\.\.';\n    try\{.*?\}catch\(_\)\{ el\('docMsg'\)\.textContent='request failed'; \}",
        ("    el('docMsg').textContent='Document ingest runs in the live (self-hosted) version.';\n"
         "    setTimeout(closeDocs, 1400);"),
        html, flags=re.DOTALL)

    # 3) demo banner
    html = html.replace("<div class=\"brand-sub\">Orchestration Engine</div>",
                        "<div class=\"brand-sub\">Orchestration Engine &middot; Live Demo</div>")
    return html


def main() -> None:
    timeline = trim(capture_timeline())
    html = build(timeline)
    assert "fetch('/" not in html, "server fetch left in demo"
    assert "EventSource" not in html, "EventSource left in demo"
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    (OUT.parent / ".nojekyll").touch()
    print(f"wrote {OUT} ({len(html)} bytes, {len(timeline)} events)")


if __name__ == "__main__":
    main()
