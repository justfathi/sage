# SAGE — Architecture

> Self-Architecting Genesis Engine. This document describes the system design at a level meant to guide implementation without locking in premature detail.

## Design principles

1. **Context-first.** The system's power comes from ingesting how a company *actually* works, not from clever prompting.
2. **Model-agnostic.** Every call to an LLM goes through an abstraction layer. Swapping Claude for another model is a config change, never a rewrite. As models improve, SAGE improves for free.
3. **Agent creation is a phase, not a prerequisite.** SAGE's first job on any goal is to design the team.
4. **Closed feedback loop from day one.** Agents don't just execute — they report learnings that re-shape the knowledge base and future agents.
5. **Persistence over ephemerality.** Agents are entities with memory, specs, and performance history — not throwaway prompt calls.

## The four layers

```
┌─────────────────────────────────────────────────────────┐
│  ① INGESTION          PDFs · docs · workflows · chats     │
│     └─ parse → chunk → embed → store                      │
├─────────────────────────────────────────────────────────┤
│  ② ARCHITECT (Orchestrator / "SAGE Core")                 │
│     └─ read knowledge → decompose goal → design specs     │
├─────────────────────────────────────────────────────────┤
│  ③ SPAWN & EXECUTE                                        │
│     └─ instantiate agents with context → run tasks        │
├─────────────────────────────────────────────────────────┤
│  ④ LEARN                                                  │
│     └─ collect outcomes → update knowledge → re-architect │
└─────────────────────────────────────────────────────────┘
              ▲                                    │
              └──────────── feedback ──────────────┘
```

### ① Ingestion layer

Turns a company's raw material into structured, queryable knowledge.

- **Input:** PDFs, text docs, SOPs, tender documents, design specs, conversation history
- **Process:** parse → clean → chunk → embed
- **Output:** a semantic knowledge base, plus extracted explicit workflows and (eventually) implicit patterns and bottlenecks
- **Re-ingestion is first-class:** dropping in new files updates the base and triggers re-evaluation downstream

### ② Architect layer (the Orchestrator)

The brain. One primary orchestrator agent — "SAGE Core."

- Reads the knowledge base
- Decomposes a goal into the **roles** required
- Emits **agent specs**: role, purpose, context to load, tools, success criteria
- Designs lean, narrowly-scoped agents (one job each) rather than monoliths
- Discovers **new role archetypes** the situation demands — including non-human-shaped ones
- (Stretch) simulates agent interaction, predicts failure points, pre-emptively designs bridging agents

### ③ Spawn & execution layer

Turns specs into working agents.

- Instantiates each agent with its scoped context
- Assigns tasks, runs them (async)
- Manages agent lifecycle and state
- Agents can reference the knowledge base throughout their life, not just at creation

### ④ Learning layer

Closes the loop.

- Agents emit outcomes, insights, flagged inefficiencies, suggested new roles
- The knowledge base is updated
- The orchestrator re-architects: refine, retire, or spawn agents
- Over time SAGE builds an evolving org chart and a library of discovered archetypes

## Agent memory

Memory is layered, not a single store. Each layer answers a different question.

| Layer | Store | Holds |
|-------|-------|-------|
| Working / short-term | Redis | per-task scratchpad, ephemeral |
| Semantic ("what it learned") | Vector DB | insights, retrievable by meaning |
| Structured facts | PostgreSQL | agent specs, metrics, relationships, org chart |
| Raw artifacts | S3 (blob) | uploaded files, agent outputs — source of truth |

Rule of thumb: **S3 holds the files, the DBs hold the understanding.** DynamoDB is an option only if we later want serverless + massive scale; for one-instance-per-company, Postgres + vector DB + S3 is the conventional and correct baseline.

## The Gardener (agent lifecycle)

Retiring vs. retraining an agent is itself a **dedicated role** — the **Gardener**. It's a SAGE-native position with no human equivalent.

- **Prunes** dead or underperforming agents
- **Retrains** agents that are close but drifting
- **Flags gaps** back to the Architect to grow new branches

This keeps the tree healthy without human bookkeeping, and fits the core metaphor.

**"Underperforming" is a judgment, not a fixed threshold.** We deliberately do *not* hardcode metrics for prune-vs-retrain. That decision is **fluid** — handled by a custom SAGE agent that evaluates each case in context, the same way SAGE designs everything else. Static thresholds would calcify; an agent can reason about *why* something is failing and choose accordingly.

**Minimum viable Gardener (v1):** just **mark agents dead/alive**. That's enough to prove the role exists and earns its place in the tree. No sophisticated scoring required to start.

**How the Gardener gets better (later):** it rides the same feedback loop as everything else — it logs each prune/retrain decision, later observes the outcome (did killing that agent actually help?), and refines its judgment from its own track record. Not needed for v1; the marking comes first.

## Instance isolation (and why)

Each SAGE instance stays **fully separate** — one company's digital DNA, no shared state, no cross-instance archetype sharing. **For now.**

This isn't only a privacy stance, it's an **experiment**: if a single isolated instance's agents demonstrably get smarter, more refined, and more effective over time, that *proves* the learning loop works (or disproves it). We want that signal clean.

> **Cross-instance archetype sharing is off the table — not "later," but not considered at all for now.** Instances stay sealed. The only sharing model we'd ever entertain (the *blueprint travels, the data never does* pattern) is explicitly out of scope and not part of the design. Revisit only if a real, proven need emerges far down the line.

## Human-in-the-loop

A human can always shape the flow — two mechanisms working together:

1. **Always-available interrupt.** An ambient prompt the human can use at any moment — mid-architecting, mid-spawn — e.g. *"pause, let me approve these roles before you assign them."* SAGE yields.
2. **Configurable gates.** Pre-set policy so SAGE isn't blocked on every routine cycle — e.g. *"always stop before spawning"* vs. *"auto-run, just notify me."*

Together you get the live override **and** a default policy. The interrupt handles the exception; the gate handles the norm.

**Surface: UI first.** The cleanest channel is a persistent, **non-blocking** pause affordance always visible in the UI — the human never has to hunt for it. Build it UI-first, but keep the underlying signal **channel-agnostic** so a future Slack message or API call can hit the same pause endpoint.

## State, status & resuming — one activity log

SAGE maintains a single **append-only activity log** (the event-sourcing / "durable execution" pattern). Its key property: **the log is not just for humans to watch — it *is* the source of truth for state.**

- Every meaningful step is written as an event: `designing roles`, `spawned Builder`, `Builder completed task X`, `Gardener marked Analyst dead`
- That same stream powers **two things at once**:
  1. the **human status view** (a live column/feed showing what SAGE and each agent are doing)
  2. **recovery** after an interrupt or crash
- **Resume = read the last committed event, reconstruct context, continue from there** — literally "look back at what we were doing and pick up."
- **Checkpoint at step boundaries, never mid-step**, so we never resume into a half-finished action.

The elegance: the status bar and the resume mechanism are the *same artifact*. One log, two uses.

### Event schema

Every event shares one flat shape:

```json
{
  "event_id": "uuid",
  "instance_id": "uuid",
  "timestamp": "ISO-8601",
  "actor": "SAGE-Core | Gardener | agent:builder-7",
  "action": "spawned_agent",
  "summary": "Spawned Builder to scaffold the API",   // human-readable, one line
  "status": "started | completed | failed | paused",
  "parent_id": "event_id of the step this belongs to", // threads the tree of work
  "payload": { },                                       // machine state: specs, inputs, outputs, refs
  "checkpoint": true                                    // is this a safe resume point?
}
```

- `summary` → human-readable status feed
- `payload` + `status` + `checkpoint` → machine-resumable
- `parent_id` → reconstructs the full tree of work

One schema serves both the human view and recovery.

### Checkpoint granularity — per agent action

Checkpoint **per agent action**, not per task or per cycle.

- A *task* is too coarse — a long task would lose work on interrupt.
- A *cycle* is far too coarse.
- An **action** = one atomic unit an agent completes (a tool call, a decision, an output).

Mark `checkpoint: true` when an action **fully completes**. Resume picks up at the last completed action. Fine granularity is cheap (cost isn't a constraint) and preserves the most work.

### The pause control plane

Pause logic does **not** live in the UI. It lives in a dedicated control endpoint in the orchestration layer:

```
POST /instance/{id}/pause     POST /instance/{id}/resume
```

- The UI is just *a client* of this endpoint. So is a future Slack action or API caller.
- SAGE checks one place — *"am I paused?"* — at every step boundary.
- This is what makes the interrupt channel-agnostic for free.

**The loops align:** SAGE checks the pause flag **at each step boundary** — which is exactly where it **writes a checkpoint event**. Same moment, same loop. Pause, status, and resume all converge on the step boundary.

## Component stack (high-level, indicative)

| Concern | Candidate |
|---------|-----------|
| Semantic knowledge store | Vector DB — Pinecone or Weaviate |
| Orchestration / agent logic | Python (LangChain or similar) |
| Persistence (specs, metrics, relationships) | PostgreSQL |
| Async agent jobs | Redis / Celery |
| LLM access | **Model-agnostic abstraction** (Claude first) |
| Prompt management | Versioned, model-portable prompt store |

> These are starting bets, not commitments. The abstraction boundaries matter more than the specific tools.

## On cost

**Cost is not a design constraint.** SAGE's alternative is spinning up a human team — and that cost vastly outweighs the compute. We optimize for capability and correctness, not for shaving tokens. Learning cycles run as richly as they need to. If cost ever becomes a real ceiling, it's a tuning problem for later, never a reason to cripple the loop now.

## The model-agnostic boundary

All reasoning goes through a single generic interface:

```
reason(task, context) ─▶ [ LLM abstraction ] ─▶ provider (Claude | … )
```

Orchestrator logic never names a model. Swap the backend, keep the system. When the underlying model gets smarter at reasoning, decomposition, and planning, SAGE inherits that — no architectural change.

## One instance = one company

Each SAGE instance is a single organization's **digital DNA**: its documents, workflows, conversation history, agent roster, and performance data. Instances don't share state.

## Settled stances

These are decided, not open:

- **Gardener uses judgment, not fixed thresholds** — a custom agent decides prune vs. retrain, fluidly.
- **Cost is not a constraint** — capability wins; the human-team alternative dwarfs compute cost.
- **No cross-instance sharing** — instances stay sealed; not considered at all for now.

## Open questions / frontier

_Resolved for now — revisit when implementation surfaces new ones._

---

_See [README.md](./README.md) for the product framing and roadmap._
