# SAGE — High-Level Implementation

> How we *build* SAGE. This is the companion to [ARCHITECTURE.md](./ARCHITECTURE.md): the architecture says **what** the system is; this says **how** we construct it, at a high level, without locking in premature detail.

## The core decision: build the thin layer, don't depend on a framework

SAGE is **built directly on the model API plus a thin orchestration loop we own** — *not* on CrewAI, LangGraph, AutoGen, or similar.

Why:

- An **agent** is just one LLM call with a role, context, and a few tools.
- **Orchestration** is just a loop deciding which calls to make next.
- Frameworks are convenience wrappers around that loop — they add lock-in, heavy abstractions, and each wraps the model *their own way*, which fights our **model-agnostic** principle.
- The thin loop is a few hundred lines, not a mountain. Owning it keeps SAGE simple and lets it ride model improvements for free.

> A framework like CrewAI may be used to *prototype* quickly on day one, but it never becomes the foundation.

**Don't confuse the two layers:**

- **What we build SAGE *with*** → the thin loop + Claude API (this document).
- **What SAGE *deploys* for the customer** → the playbook (BMAD, MetaGPT, etc. — see ARCHITECTURE.md → *Methodologies & substrates*).

## What an "agent" actually is

A scoped, persistent record — not a magic object:

```json
{
  "agent_id": "uuid",
  "role": "Builder",
  "purpose": "scaffold and implement the API",
  "context_refs": ["doc:123", "kb:auth-flow"],   // what knowledge to load
  "tools": ["write_file", "run_tests"],
  "success_criteria": "endpoints pass the spec suite",
  "status": "alive | dead | retraining"
}
```

Running an agent = load its context → make an LLM call with its role + tools → capture the result → log it. Nothing more exotic.

## The building blocks

| Block | Role | Starting bet |
|-------|------|--------------|
| **Reasoning** | the brain — planning, decomposition, decisions | Claude API (behind the model-agnostic boundary) |
| **The thin loop** | reads context → designs roles → spawns scoped calls → logs | our own code |
| **Tool-calling** | how agents act on the world | the model's *native* tool use — no framework |
| **Semantic store** | knowledge retrievable by meaning | Vector DB (Pinecone / Weaviate) |
| **Structured store** | specs, metrics, org chart, relationships | PostgreSQL |
| **Blob store** | uploaded files, raw outputs (source of truth) | S3 |
| **Working memory / queue** | scratchpad, async jobs | Redis |
| **Activity log** | event-sourced spine: status + recovery | append-only (Postgres table or log store) |

These mirror the stores in ARCHITECTURE.md → *Agent memory*. The abstraction boundaries matter more than the specific products.

## The thin loop (pseudocode)

This is the heart of SAGE — the loop that turns a goal into a working, self-correcting team.

```python
def run(instance, goal):
    kb = ingest(instance.documents)            # ① layer

    while not goal.satisfied():
        if paused(instance):                   # human-in-the-loop control plane
            wait_for_resume(instance)

        # ② ARCHITECT — design or adjust the team
        methodology = playbook.match(goal, kb) # BMAD? MetaGPT? or none → from scratch
        specs = architect(goal, kb, methodology)
        log(instance, "architected", specs, checkpoint=True)

        gate_check(instance, "before_spawn")   # configurable gate

        # ③ SPAWN & EXECUTE
        for spec in specs:
            agent = spawn(spec, kb)
            for action in agent.work():
                result = execute(action)
                log(instance, action, result, checkpoint=action.done)

        # ④ LEARN
        insights = collect_outcomes(agents)
        kb.update(insights)
        gardener.review(agents)                # mark dead / retrain / flag gaps
        log(instance, "learned", insights, checkpoint=True)
```

Every `log(...)` writes one event in the schema from ARCHITECTURE.md. The loop checks `paused()` and writes checkpoints **at the same step boundaries** — pause, status, and resume all converge there.

## The model-agnostic boundary in practice

Every reasoning call goes through one interface, never a named model:

```python
def reason(task, context):
    return provider.complete(task, context)    # provider = Claude today, swappable
```

The thin loop, the architect, the agents, the Gardener — none of them know which model is underneath. Swap the provider, keep the system.

## What we build vs. borrow

| Build ourselves | Borrow / plug in |
|-----------------|------------------|
| The thin orchestration loop | The LLM (Claude API) |
| The architect logic (goal → specs) | Native tool-calling |
| The activity-log spine | Storage engines (Postgres, vector DB, S3, Redis) |
| The Gardener | Methodologies in the playbook (BMAD, MetaGPT) |
| The human control plane (pause/gates) | — |
| The playbook registry | — |

The pattern, restated: **own the architect's chair, rent the engine room.**

## Build order (mirrors the roadmap)

1. **Ingestion** — documents → knowledge base.
2. **Architect** — knowledge → agent specs (with playbook matching).
3. **Spawn & execute** — specs → running agents on real tasks.
4. **Learn** — feedback loop + minimal Gardener (mark dead/alive).

The activity log and model-agnostic boundary are laid down in step 1 and used by every step after.

---

_See [ARCHITECTURE.md](./ARCHITECTURE.md) for the system design and [README.md](./README.md) for product framing._
