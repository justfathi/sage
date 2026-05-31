"""Smoke tests for the SAGE thin loop, using the offline mock provider."""

from __future__ import annotations

import os
import tempfile

from sage.core.engine import SageEngine
from sage.core.memory import KnowledgeBase
from sage.providers import get_provider
from sage.providers.base import extract_json
from sage.providers.mock import MockProvider


def _engine():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    return SageEngine(provider=MockProvider(), db_path=tmp.name), tmp.name


def test_extract_json_handles_fences():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('noise [1,2,3] tail') == [1, 2, 3]


def test_knowledge_base_ingest_and_search():
    kb = KnowledgeBase()
    n = kb.ingest_text("doc", "The quoting workflow applies fuel surcharges.\n\nInvoices post to SAP.")
    assert n >= 1
    hits = kb.search("surcharge fuel")
    assert hits and "surcharge" in hits[0].text.lower()


def test_software_goal_matches_bmad_and_designs_team():
    engine, _ = _engine()
    engine.kb.ingest_text("tender", "Rebuild our API and app. Backend and frontend software.")
    result = engine.run("Rebuild the orders platform API")
    assert result.methodology == "BMAD"
    assert len(result.agents) >= 3
    roles = {a.role for a in result.agents}
    assert "Builder" in roles
    engine.close()


def test_non_software_goal_designs_from_scratch():
    engine, _ = _engine()
    engine.kb.ingest_text("brief", "Plan a company offsite and improve team morale.")
    result = engine.run("Plan the annual offsite")
    assert result.methodology is None
    assert len(result.agents) >= 1
    engine.close()


def test_activity_log_is_resumable():
    engine, db = _engine()
    engine.kb.ingest_text("x", "build an api")
    result = engine.run("build an api")
    events = engine.log.events(result.instance_id)
    assert events, "expected events to be logged"
    assert any(e.checkpoint for e in events), "expected at least one checkpoint"
    cp = engine.log.last_checkpoint(result.instance_id)
    assert cp is not None
    engine.close()


def test_provider_autoselect_offline_is_mock(monkeypatch=None):
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ["SAGE_PROVIDER"] = "mock"
    assert get_provider().name == "mock"


def test_reconstruct_state_from_log_alone():
    """Prove run state is recoverable from the persisted log alone."""
    from sage.core.events import ActivityLog
    from sage.core.resume import reconstruct

    engine, db = _engine()
    engine.kb.ingest_text("tender", "Rebuild our API and app software platform.")
    result = engine.run("Rebuild the orders platform API")
    iid = result.instance_id
    engine.close()

    # Fresh log handle: state comes purely from persisted events.
    state = reconstruct(ActivityLog(db_path=db), iid)
    assert state.goal == "Rebuild the orders platform API"
    assert state.methodology == "BMAD"
    assert state.complete is True
    assert state.phase == "learned"
    assert "Builder" in state.roster


def test_gate_rejection_halts_before_spawn():
    """A configured gate with a rejecting approver stops the run cleanly."""
    engine, _ = _engine()
    engine.kb.ingest_text("tender", "Rebuild our API and app software platform.")
    engine.control.gates.add("before_spawn")
    engine.control.approver = lambda name, detail: False  # human says no
    result = engine.run("Rebuild the orders platform API")
    assert result.agents == []
    actions = [e.action for e in engine.log.events(result.instance_id)]
    assert "halted" in actions
    assert "spawned" not in actions
    engine.close()


def test_gate_approval_allows_spawn():
    engine, _ = _engine()
    engine.kb.ingest_text("tender", "Rebuild our API and app software platform.")
    engine.control.gates.add("before_spawn")
    engine.control.approver = lambda name, detail: True
    result = engine.run("Rebuild the orders platform API")
    assert len(result.agents) >= 3
    engine.close()


def test_gardener_emits_lifecycle_and_marks_qa():
    """The Gardener must actually run, emit lifecycle events, and act on QA."""
    from sage.core.models import AgentStatus

    engine, _ = _engine()
    engine.kb.ingest_text("tender", "Rebuild our API and app software platform.")
    result = engine.run("Rebuild the orders platform API")

    actions = [e.action for e in engine.log.events(result.instance_id)]
    assert "lifecycle" in actions, "Gardener produced no lifecycle events"

    # QA scores in the retrain band, so the Gardener flags it AND the retrain
    # pass runs (a "retrained" event is emitted). With a critique-guided retry
    # it recovers to alive -- that recovery is the lifecycle working end to end.
    assert "retrained" in actions, "retrain pass did not run"
    qa = next((a for a in result.agents if a.role == "QA"), None)
    assert qa is not None
    assert qa.status in (AgentStatus.ALIVE, AgentStatus.RETRAINING)
    engine.close()


def test_pause_barrier_invokes_on_pause_hook():
    """When paused, the checkpoint barrier calls the injected on_pause hook."""
    engine, _ = _engine()
    engine.kb.ingest_text("x", "build an api")
    calls = []
    engine.control.on_pause = lambda iid: calls.append(iid)
    engine.control.pause()
    result = engine.run("build an api")
    assert calls, "on_pause should fire at step boundaries while paused"
    assert all(c == result.instance_id for c in calls)
    engine.close()


def test_multi_cycle_grows_knowledge_base():
    """Core thesis: each cycle feeds learnings back, so the KB grows."""
    engine, _ = _engine()
    engine.kb.ingest_text("tender", "Rebuild our API and app software platform.")
    before = len(engine.kb.chunks)
    results = engine.run_cycles("Rebuild the orders platform API", cycles=3)
    after = len(engine.kb.chunks)
    assert len(results) == 3
    assert after > before, "learnings should have been fed back into the KB"
    # All three cycles share the one sealed instance.
    assert len({r.instance_id for r in results}) == 1
    engine.close()


def test_discovered_role_grows_in_next_cycle():
    """A role suggested in cycle 1 must be grown as a real agent in cycle 2."""
    engine, _ = _engine()
    engine.kb.ingest_text("tender", "Rebuild our API and app software platform.")
    results = engine.run_cycles("Rebuild the orders platform API", cycles=2)

    # The mock learn step suggests "BridgeAgent"; it should be remembered...
    assert "BridgeAgent" in engine.discovered_roles
    # ...and actually spawned in the second cycle.
    cycle2_roles = {a.role for a in results[1].agents}
    assert "BridgeAgent" in cycle2_roles
    # And a 'grew_role' event should record the tree growing a new branch.
    actions = [e.action for e in engine.log.events(results[1].instance_id)]
    assert "grew_role" in actions
    engine.close()


def test_activity_log_is_thread_safe():
    """The web server runs the engine off-thread; the log must survive that."""
    import threading

    engine, _ = _engine()
    engine.kb.ingest_text("tender", "Rebuild our API and app software platform.")
    err = {}

    def worker():
        try:
            engine.run("Rebuild the orders platform API")
        except Exception as exc:  # the old cross-thread sqlite bug landed here
            err["e"] = repr(exc)

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=10)
    assert not err, f"engine raised on worker thread: {err.get('e')}"
    # And the main thread can still read the log the worker wrote.
    events = engine.log.events(engine.instance_id)
    assert any(e.action == "learned" for e in events)
    engine.close()


def test_metagpt_selected_for_greenfield_brief():
    """A short greenfield software brief should pull MetaGPT, not BMAD."""
    engine, _ = _engine()
    # Short context (< 400 chars) + greenfield cue.
    engine.kb.ingest_text("brief", "Build an MVP app from scratch. A prototype API.")
    result = engine.run("Build an MVP app from scratch")
    assert result.methodology == "MetaGPT"
    roles = {a.role for a in result.agents}
    assert "Engineer" in roles  # MetaGPT crew, not BMAD's "Builder"
    engine.close()


def test_gardener_prunes_zero_output_agent():
    """An agent that produced nothing should be pruned, not kept."""
    from sage.core.models import Agent, AgentSpec, AgentStatus
    from sage.core import gardener
    from sage.providers.mock import MockProvider

    good = Agent(spec=AgentSpec(role="Builder", purpose="x"))
    good.score = 0.9
    good.outputs = ["did the thing"]
    dud = Agent(spec=AgentSpec(role="Idler", purpose="y"))
    dud.score = 0.1
    dud.outputs = []  # produced nothing

    decisions = gardener.review(MockProvider(), [good, dud])
    by_role = {d["role"]: d["verdict"] for d in decisions}
    assert by_role["Builder"] == "keep"
    assert by_role["Idler"] == "prune"
    assert dud.status == AgentStatus.DEAD
    assert good.status == AgentStatus.ALIVE


def test_vector_search_ranks_by_relevance():
    """TF-IDF cosine should rank the on-topic chunk above an unrelated one."""
    kb = KnowledgeBase()
    kb.ingest_text("a", "The surcharge engine applies fuel and remote-area fees.")
    kb.ingest_text("b", "Employees may book annual leave through the HR portal.")
    hits = kb.search("how are fuel surcharges calculated")
    assert hits, "expected at least one hit"
    assert "surcharge" in hits[0].text.lower()


def test_vector_search_empty_kb_is_safe():
    kb = KnowledgeBase()
    assert kb.search("anything") == []


def test_evaluator_gives_differentiated_scores():
    """Real evaluation should spread scores, not saturate at 1.0."""
    engine, _ = _engine()
    engine.kb.ingest_text("tender", "Rebuild our API and app software platform.")
    result = engine.run("Rebuild the orders platform API")
    scores = {a.role: a.score for a in result.agents}
    # Not everything is 1.0 (the old word-count bug); there is real spread.
    assert len(set(scores.values())) > 1, f"scores did not differentiate: {scores}"
    assert all(0.0 <= s <= 1.0 for s in scores.values())
    # ContextKeeper is scored low by the mock evaluator -> Gardener should act.
    from sage.core.models import AgentStatus
    ck = next((a for a in result.agents if a.role == "ContextKeeper"), None)
    if ck:
        assert ck.status in (AgentStatus.DEAD, AgentStatus.RETRAINING)
    engine.close()


def test_handoff_passes_upstream_outputs():
    """With handoff on, a later agent's context includes an earlier artifact."""
    from sage.core import executor
    from sage.core.models import Agent, AgentSpec
    from sage.core.memory import KnowledgeBase
    from sage.providers.mock import MockProvider

    captured = {}

    class SpyProvider(MockProvider):
        def reason(self, task, context="", system=None, max_tokens=2048):
            if "perform your role" in task.lower():
                captured.setdefault("contexts", []).append(context)
            return super().reason(task, context=context, system=system, max_tokens=max_tokens)

    kb = KnowledgeBase(); kb.ingest_text("x", "build an api platform")
    agents = [Agent(spec=AgentSpec(role="First", purpose="a")),
              Agent(spec=AgentSpec(role="Second", purpose="b"))]
    list(executor.run_team(SpyProvider(), agents, "build an api", kb, handoff=True))
    # The second agent's context should mention the first agent's handoff note.
    assert any("[First]" in c for c in captured["contexts"][1:]), captured["contexts"]


def test_engine_rehydrates_learning_across_restart():
    """A fresh engine on the same instance_id recovers discovered roles + KB."""
    import tempfile
    from sage.core.events import ActivityLog

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
    e1 = SageEngine(provider=MockProvider(), db_path=tmp.name)
    e1.kb.ingest_text("tender", "Rebuild our API and app software platform.")
    e1.run("Rebuild the orders platform API")
    iid = e1.instance_id
    assert "BridgeAgent" in e1.discovered_roles
    e1.close()

    # Simulate a process restart: brand-new engine, same instance id.
    e2 = SageEngine(provider=MockProvider(), db_path=tmp.name, instance_id=iid)
    assert "BridgeAgent" in e2.discovered_roles, "did not rehydrate from log"
    assert any(c.source == "learnings" for c in e2.kb.chunks), "KB learnings lost"
    e2.close()


def test_pruned_role_not_regrown_next_cycle():
    """The Gardener's prune must shape the next cycle: dead roles stay gone."""
    engine, _ = _engine()
    engine.kb.ingest_text("tender", "Rebuild our API and app software platform.")
    results = engine.run_cycles("Rebuild the orders platform API", cycles=2)

    # The mock evaluator scores ContextKeeper low -> pruned in cycle 1.
    assert "ContextKeeper" in engine.pruned_roles
    c1 = {a.role for a in results[0].agents}
    c2 = {a.role for a in results[1].agents}
    assert "ContextKeeper" in c1
    assert "ContextKeeper" not in c2, "pruned role was wrongly re-grown"
    # The discovered role still grows -- prune and grow coexist.
    assert "BridgeAgent" in c2
    engine.close()


def test_resumed_instance_restores_documents():
    """A resumed instance must rebuild its KB docs from the log, not forget them."""
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
    e1 = SageEngine(provider=MockProvider(), db_path=tmp.name)
    n = e1.ingest("demo/sample_company")
    iid = e1.instance_id
    assert n > 0
    e1.close()

    # Resume WITHOUT re-passing --docs; KB should rebuild from the log.
    e2 = SageEngine(provider=MockProvider(), db_path=tmp.name, instance_id=iid)
    assert len(e2.kb.chunks) == n, "documents were not restored on resume"
    assert any("tender" in c.source for c in e2.kb.chunks)
    e2.close()


def test_retrain_pass_recovers_an_agent():
    """A retrain-band agent gets a critique-guided retry and can recover."""
    from sage.core.models import AgentStatus

    engine, _ = _engine()
    engine.kb.ingest_text("tender", "Rebuild our API and app software platform.")
    result = engine.run("Rebuild the orders platform API")

    events = engine.log.events(result.instance_id)
    retrained = [e for e in events if e.action == "retrained"]
    assert retrained, "expected at least one retrained event"
    # At least one retrain should report a score improvement.
    improved = [e for e in retrained
                if e.payload.get("after", 0) > e.payload.get("before", 1)]
    assert improved, f"no retrain improved a score: {[e.payload for e in retrained]}"
    # QA specifically should have recovered to alive.
    qa = next((a for a in result.agents if a.role == "QA"), None)
    assert qa and qa.status == AgentStatus.ALIVE
    engine.close()


def test_all_internal_prompts_route_in_mock():
    """Guard against prompt/router drift: every internal call must hit a real
    mock handler, never the 'Acknowledged.' fallback. If a prompt's opening
    text changes without updating the router, this fails loudly."""
    from sage.providers.mock import MockProvider
    p = MockProvider()

    # Mirror the opening text of each internal prompt the engine issues.
    prompts = {
        "match": "Match the goal to one methodology from the playbook, or null...",
        "design": "Design the team of agents (roles) needed to achieve this goal.",
        "work": "Perform your role.\nrole: Builder\npurpose: x",
        "retrain": "Re-do your work. Your previous attempt underperformed.\nrole: QA",
        "evaluate": "Evaluate this artifact. Score 0.0-1.0 on how well it meets...",
        "gardener": 'Evaluate the roster and decide each agent\'s fate. [{"role":"QA"}]',
        "insights": "Extract insights and suggested new roles from this cycle...",
    }
    for name, text in prompts.items():
        out = p.reason(text)
        assert out != "Acknowledged.", f"prompt '{name}' fell through the router"


def test_runner_submit_goal_reuses_instance():
    """The web runner can start a new goal on the same sealed instance."""
    import tempfile
    from sage.web.server import SageRunner

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
    runner = SageRunner(docs=None, goal="first goal about an api platform",
                        cycles=1, provider_name="mock", db_path=tmp.name)
    iid = runner.engine.instance_id

    r1 = runner.submit_goal("Rebuild the orders platform API")
    assert r1["ok"] is True
    runner._thread.join(timeout=10)

    # A second goal reuses the SAME instance (keeps what it learned).
    r2 = runner.submit_goal("Now migrate the data warehouse")
    assert r2["ok"] is True
    runner._thread.join(timeout=10)

    assert runner.engine.instance_id == iid
    goals = [e.payload.get("goal") for e in runner.engine.log.events(iid)
             if e.action == "goal_received"]
    assert "Rebuild the orders platform API" in goals
    assert "Now migrate the data warehouse" in goals
    runner.engine.close()


def test_runner_rejects_empty_goal():
    from sage.web.server import SageRunner
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False); tmp.close()
    runner = SageRunner(None, "seed goal", 1, "mock", tmp.name)
    assert runner.submit_goal("   ")["ok"] is False
    runner.engine.close()


def test_tools_actually_execute():
    """An agent's declared tools must really run and record what was used."""
    from sage.core import tools
    from sage.core.memory import KnowledgeBase

    kb = KnowledgeBase(); kb.ingest_text("doc", "build an api platform with auth")
    ctx = tools.ToolContext(kb=kb, goal="build an api", role="Builder",
                            purpose="implement the api")
    results = tools.run_tools(["read_kb", "write_doc", "run_tests"], ctx)
    assert len(results) == 3
    assert any("read_kb:" in r for r in results)
    assert "Builder.md" in ctx.artifacts          # write_doc produced an artifact
    # unknown tools are skipped gracefully, never crash
    assert "nope: (no such tool" in tools.invoke("nope", ctx)


def test_agent_records_tools_used():
    """run_agent should populate agent.tools_used from its spec."""
    from sage.core import executor
    from sage.core.models import Agent, AgentSpec
    from sage.core.memory import KnowledgeBase
    from sage.providers.mock import MockProvider

    kb = KnowledgeBase(); kb.ingest_text("x", "build an api platform")
    agent = Agent(spec=AgentSpec(role="Builder", purpose="implement",
                                 tools=["read_kb", "write_file"]))
    executor.run_agent(MockProvider(), agent, "build an api", kb, artifacts={})
    assert agent.tools_used == ["read_kb", "write_file"]
