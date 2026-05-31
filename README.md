<div align="center">

# 🌳 SAGE

### Self-Architecting Genesis Engine

**Feed it your company. It grows its own team.**

[![CI](https://github.com/justfathi/sage/actions/workflows/ci.yml/badge.svg)](https://github.com/justfathi/sage/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
![Status: Concept](https://img.shields.io/badge/status-early%20concept-orange)
![Model-agnostic](https://img.shields.io/badge/models-agnostic-7c3aed)

### ▶ [Watch the live demo](https://justfathi.github.io/sage/)

*A real SAGE run, replayed in your browser — agents spawning, a discovered role growing, the Gardener pruning. No install.*

</div>

---

## What is SAGE?

SAGE is an open-source engine that **designs and grows its own workforce of AI agents** from your company's context — no code required.

You don't tell SAGE which agents to build. You give it your world — documents, workflows, conversations, a tender, a goal — and SAGE figures out what roles are needed, spawns specialized agents to fill them, watches how they perform, and grows new agents to close the gaps it discovers.

> Think of it less like automation software and more like **onboarding a team that already understands how you work.**

## The tree metaphor

SAGE behaves like a living tree:

| Part | What it is |
|------|-----------|
| 🟤 **The soil** | Your company — the ask, the goal, the tender, everything you know |
| 🟣 **The roots** | SAGE reaching deep into your context, absorbing how you actually operate |
| 🟪 **The trunk** | The engine itself — reasoning, decomposing, deciding |
| 🌿 **The branches** | Specialized agents, each grown for a purpose |
| ✨ **A forming branch** | A *new role* SAGE discovered that you didn't know you needed |

Energy flows **both ways**: SAGE grows agents outward, and agents feed their learnings back inward — so the tree gets stronger every cycle.

## Why it's different

Most agent frameworks make you assemble the team by hand. SAGE flips it:

- **Context-first, not prompt-first** — you upload your real documentation, not a clever prompt
- **It designs the workforce** — agent creation is the *first* phase of any job, not your homework
- **It discovers new roles** — not just digital versions of human jobs, but positions the agentic world creates (knowledge keepers, bridge agents, decision validators)
- **It learns** — a feedback loop runs from day one; every agent's experience sharpens the next generation
- **It's model-agnostic** — Claude today, whatever's best tomorrow, with zero rewrites

## How it works

```
  Your docs ─▶ ① INGEST ─▶ ② ARCHITECT ─▶ ③ SPAWN ─▶ ④ LEARN ─┐
                                                               │
                  ▲                                            │
                  └──────────── feedback loop ─────────────────┘
```

1. **Ingest** — PDFs, docs, workflows, and conversations become a structured, searchable knowledge base
2. **Architect** — the orchestrator reads that knowledge and designs the agent roles the goal demands
3. **Spawn** — agents are instantiated with the right context and put to work
4. **Learn** — agents report what worked, what didn't, and what gaps remain; SAGE updates and re-architects

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full system design.

## A concrete example

A company puts out a tender to rebuild their app and API. They have requirements, specs, design prototypes, timelines.

They start a new SAGE instance and upload all of it. SAGE:

- Ingests the tender and extracts functional + non-functional requirements
- Identifies the roles needed: requirements breakdown, dependency mapping, effort estimation, architecture, QA
- Spawns lean, focused agents for each
- Returns a structured plan — *"here are the agents for this project, here's what they'll do, here's the order"*

When the founder remembers a missing spec, they drop it in. SAGE re-ingests, re-evaluates, and adjusts the team on the fly.

## Roadmap

| Phase | Focus |
|-------|-------|
| **Week 1** | Document ingestion pipeline → knowledge base |
| **Week 2** | Orchestrator agent → reads knowledge, outputs agent specs |
| **Week 3** | Agent spawning + execution on real tasks |
| **Week 4** | Feedback loops + continuous learning |

## Project philosophy

- **Open core, hosted edge.** The engine is open source (AGPL). A managed SAGE will offer hosting, integrations, and enterprise support.
- **Eat our own dog food.** SAGE helps build SAGE from day one.
- **Build first, polish later.** A working prototype beats a perfect spec.

## License

[AGPL-3.0](./LICENSE) — use it freely, but improvements stay open.

---

<div align="center">
<sub>SAGE · Self-Architecting Genesis Engine · grow your team, don't build it</sub>
</div>
