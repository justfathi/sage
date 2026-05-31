"""Tests for the web layer (SSE dashboard server), offline mock provider.

These cover the HTTP endpoints and the SageRunner control logic that the
dashboard depends on -- previously only checked by throwaway scripts, now
guarded by CI.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import urllib.request
import urllib.error

from http.server import ThreadingHTTPServer

from sage.web.server import SageRunner, _make_handler


def _serve():
    """Spin up a real server on an ephemeral port; return (base_url, srv, runner)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    runner = SageRunner(docs="demo/sample_company",
                        goal="Rebuild our Orders Platform with a modern API",
                        cycles=1, provider_name="mock", db_path=tmp.name)
    # minimal HTML stand-in so we don't depend on the real file here
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(runner, "<html>demo</html>"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    return f"http://127.0.0.1:{port}", srv, runner


def _get(url):
    return urllib.request.urlopen(url, timeout=10).read().decode()


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        return urllib.request.urlopen(req, timeout=10).read().decode()
    except urllib.error.HTTPError as e:
        return f"HTTP{e.code}:" + e.read().decode()


def test_meta_and_index_served():
    base, srv, runner = _serve()
    try:
        assert "demo" in _get(base + "/")
        meta = json.loads(_get(base + "/meta"))
        assert meta["provider"] == "mock"
        assert meta["goal"].startswith("Rebuild")
        assert "instance" in meta
    finally:
        srv.shutdown(); runner.engine.close()


def test_run_then_timeline_records_events():
    base, srv, runner = _serve()
    try:
        res = json.loads(_post(base + "/run", {"goal": "Rebuild the orders platform API"}))
        assert res["ok"] is True
        runner._thread.join(timeout=10)
        tl = json.loads(_get(base + "/timeline"))
        actions = {e["action"] for e in tl}
        assert "architected" in actions and "learned" in actions
    finally:
        srv.shutdown(); runner.engine.close()


def test_run_rejects_empty_goal():
    base, srv, runner = _serve()
    try:
        # empty / whitespace goal -> 409 with ok:false
        resp = _post(base + "/run", {"goal": "   "})
        assert resp.startswith("HTTP409")
        assert '"ok": false' in resp
    finally:
        srv.shutdown(); runner.engine.close()


def test_ingest_endpoint_adds_to_kb():
    base, srv, runner = _serve()
    try:
        res = json.loads(_post(base + "/ingest",
                               {"source": "notes.md", "text": "Refunds over $500 need approval."}))
        assert res["ok"] is True and res["chunks"] >= 1
        # empty doc rejected
        assert "HTTP409" in _post(base + "/ingest", {"source": "x", "text": "  "})
    finally:
        srv.shutdown(); runner.engine.close()


def test_pause_resume_endpoints():
    base, srv, runner = _serve()
    try:
        assert _post(base + "/pause", {}) == "paused"
        assert runner.engine.control.paused is True
        assert _post(base + "/resume", {}) == "resumed"
        assert runner.engine.control.paused is False
    finally:
        srv.shutdown(); runner.engine.close()


def test_unknown_route_404():
    base, srv, runner = _serve()
    try:
        try:
            _get(base + "/nope")
            assert False, "expected 404"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        srv.shutdown(); runner.engine.close()
