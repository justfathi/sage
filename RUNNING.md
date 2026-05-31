# Running SAGE (MVP)

This MVP runs **offline with zero dependencies** using a deterministic mock
reasoning provider, and switches to **real Claude** automatically when an API
key is present — with no code changes (that's the model-agnostic boundary at
work).

## Quick start (offline, no key needed)

```bash
python3 -m sage.cli run \
  --docs demo/sample_company \
  --goal "Rebuild our Orders Platform with a modern API"
```

You'll see the live activity feed — ingest -> methodology match -> architect ->
spawn -> agent work -> Gardener lifecycle -> learn — each line one event in the
append-only log. A `*` marks a checkpoint (a safe resume point).

## Launch the live God-View dashboard

```bash
python3 -m sage.cli serve \
  --docs demo/sample_company \
  --goal "Rebuild our Orders Platform with a modern API" \
  --cycles 3
```

Then open <http://127.0.0.1:8765> in a browser. You'll watch agents spawn and
orbit the SAGE core, the roster fill in, the event feed stream live, and — by
cycle 2 — a newly discovered role (BridgeAgent) **grow as a new branch** with a
"+ New role" badge. The **Pause** button is a real client of the control plane:
it hits `/pause` on the server, which blocks the engine at the next step
boundary (exactly the architecture's channel-agnostic design).

The dashboard is driven entirely by real activity-log events over SSE — no
fake animation. Stop the server with Ctrl-C.

## Run multiple learning cycles

```bash
python3 -m sage.cli run --docs demo/sample_company \
  --goal "Rebuild our Orders Platform" --cycles 3
```

Each cycle feeds its learnings back into the knowledge base, so later cycles
reason over a richer context. This is the core thesis in motion: one sealed
instance getting sharper over time.

## Use real Claude

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m sage.cli run --docs demo/sample_company --goal "Rebuild our API"
```

SAGE auto-selects Claude when the key is set. Force a provider with
`--provider mock` or `--provider claude`, or `SAGE_PROVIDER=...`.
Pick a model with `SAGE_MODEL=claude-opus-4-8` (default).

## Replay a past run

Every run prints its `instance` id. Replay its full event log:

```bash
python3 -m sage.cli log --instance <instance-id>
```

## Resume an instance (it remembers what it learned)

```bash
python3 -m sage.cli run --goal "Rebuild our Orders Platform" --instance <instance-id>
```

A fresh process rehydrates the instance's discovered roles and fed-back
learnings from the activity log, then keeps going. The log is the source of
truth, so SAGE does not forget on restart — one sealed instance keeps getting
smarter across sessions.

## Reconstruct state from the log alone

```bash
python3 -m sage.cli status --instance <instance-id>
```

This rebuilds the goal, methodology, roster, phase reached, and last
checkpoint **purely from the activity log** — proving the log is the source of
truth for state, exactly what a resume would read.

## Run the tests

```bash
python3 -m pytest tests/ -q
```

## Install as a package (optional)

```bash
pip install -e .            # core, offline
pip install -e ".[claude]"  # add the Anthropic SDK for real Claude
# then:
sage run --docs demo/sample_company --goal "Rebuild our API"
```

## What's in the box (MVP)

| Layer | Module | Status |
|-------|--------|--------|
| Model-agnostic boundary | `sage/providers/` | mock + Claude |
| Ingestion | `sage/core/memory.py` | text/markdown -> chunked KB |
| Architect | `sage/core/architect.py` | goal -> agent specs |
| Playbook | `sage/core/playbook.py` | BMAD / MetaGPT matching |
| Spawn & execute | `sage/core/executor.py` | run scoped agents |
| Gardener | `sage/core/gardener.py` | keep / retrain / prune |
| Learn | `sage/core/engine.py` | insights -> back into KB |
| Activity log | `sage/core/events.py` | SQLite, event-sourced |
| Human control plane | `sage/core/control.py` | pause + gates |
| State reconstruction | `sage/core/resume.py` | rebuild state from log |
| Thin loop | `sage/core/engine.py` | ties it together |
| God-View dashboard | `sage/web/` | live SSE UI + pause control |

## Known MVP simplifications

- Retrieval is keyword-overlap, not a real vector DB (interface is ready for one).
- Agents "work" via a single reasoning call; no real tools are executed yet.
- Resume reconstructs state from the log but re-runs from the goal; full
  mid-run re-entry is a next step.
