"""SAGE God-View web server -- stdlib only, zero dependencies.

Runs a real SAGE engine in a background thread and streams its activity-log
events to the browser over Server-Sent Events (SSE). The dashboard is a pure
CLIENT of the control plane: the Pause/Resume buttons hit /pause and /resume,
exactly the channel-agnostic design the architecture prescribes.

    python -m sage.cli serve --docs demo/sample_company --goal "..."
"""

from __future__ import annotations

import json
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from ..core.engine import SageEngine
from ..providers import get_provider


class _Hub:
    """Fan-out of engine events to any number of SSE subscribers."""

    def __init__(self) -> None:
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self._history: list[dict] = []

    def publish(self, event: dict) -> None:
        with self._lock:
            self._history.append(event)
            for q in list(self._subs):
                q.put(event)

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            for past in self._history:
                q.put(past)
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)


class SageRunner:
    """Drives a SAGE engine on a worker thread, feeding events to the hub."""

    def __init__(self, docs: Optional[str], goal: str, cycles: int,
                 provider_name: Optional[str], db_path: str) -> None:
        self.hub = _Hub()
        self.goal = goal
        self.cycles = cycles
        self.docs = docs
        self._ingested = False
        self._resume = threading.Event()
        self._resume.set()

        provider = get_provider(provider_name)
        self.engine = SageEngine(provider=provider, db_path=db_path,
                                 on_event=self._on_event)
        # Wire the control plane: pausing blocks the loop at step boundaries.
        self.engine.control.on_pause = lambda iid: self._resume.wait()
        self.provider_name = provider.name
        self._thread: Optional[threading.Thread] = None

    # -- control plane clients --------------------------------------------

    def pause(self) -> None:
        self._resume.clear()
        self.engine.control.pause()
        self.hub.publish({"actor": "human", "action": "paused",
                          "summary": "Run paused by operator",
                          "checkpoint": False, "ts": time.time()})

    def resume(self) -> None:
        self.engine.control.resume()
        self._resume.set()
        self.hub.publish({"actor": "human", "action": "resumed",
                          "summary": "Run resumed by operator",
                          "checkpoint": False, "ts": time.time()})

    # -- engine glue ------------------------------------------------------

    def _on_event(self, event) -> None:
        d = event.to_dict()
        d["ts"] = time.time()
        self.hub.publish(d)

    def _run(self) -> None:
        try:
            if self.docs and not self._ingested:
                self.engine.ingest(self.docs)
                self._ingested = True
            self.engine.run_cycles(self.goal, cycles=self.cycles)
            self.hub.publish({"actor": "SAGE-Core", "action": "finished",
                              "summary": "All cycles complete",
                              "checkpoint": True, "ts": time.time()})
        except Exception as exc:  # surface failures to the dashboard
            self.hub.publish({"actor": "SAGE-Core", "action": "error",
                              "summary": f"Run error: {exc}",
                              "checkpoint": False, "ts": time.time()})

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def ingest_text(self, source: str, text: str) -> dict:
        """Feed a document into the instance from the UI (paste or upload)."""
        if self.is_running():
            return {"ok": False, "error": "cannot ingest while a run is in progress"}
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty document"}
        source = (source or "pasted").strip() or "pasted"
        n = self.engine.kb.ingest_text(source, text)
        # Persist it the same way engine.ingest does, so it survives restart.
        self.engine._emit("SAGE-Core", "ingested_doc",
                          f"Ingested {source} ({n} chunks)",
                          payload={"source": source, "text": text, "chunks": n},
                          checkpoint=True)
        self._ingested = True
        return {"ok": True, "source": source, "chunks": n,
                "kb": self.engine.kb.summary()}

    def submit_goal(self, goal: str, cycles: Optional[int] = None) -> dict:
        """Start a new run from the UI. Reuses the same sealed instance so the
        engine keeps everything it has already learned -- a new goal on the
        same company, not a new company."""
        if self.is_running():
            return {"ok": False, "error": "a run is already in progress"}
        goal = (goal or "").strip()
        if not goal:
            return {"ok": False, "error": "goal is empty"}
        self.goal = goal
        if cycles:
            self.cycles = max(1, int(cycles))
        self._resume.set()
        self.engine.control.resume()
        self.start()
        return {"ok": True, "goal": self.goal, "cycles": self.cycles}


def _make_handler(runner: SageRunner, html: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def _send(self, code, body, ctype="text/plain"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path == "/pause":
                runner.pause(); self._send(200, "paused")
            elif self.path == "/resume":
                runner.resume(); self._send(200, "resumed")
            elif self.path == "/run":
                body = self._json_body()
                result = runner.submit_goal(body.get("goal", ""), body.get("cycles"))
                self._send(200 if result.get("ok") else 409,
                           json.dumps(result), "application/json")
            elif self.path == "/ingest":
                body = self._json_body()
                result = runner.ingest_text(body.get("source", ""), body.get("text", ""))
                self._send(200 if result.get("ok") else 409,
                           json.dumps(result), "application/json")
            else:
                self._send(404, "not found")

        def _json_body(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                return json.loads(raw or b"{}")
            except Exception:
                return {}

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, html, "text/html; charset=utf-8")
            elif self.path == "/meta":
                self._send(200, json.dumps({
                    "goal": runner.goal, "cycles": runner.cycles,
                    "provider": runner.provider_name,
                    "instance": runner.engine.instance_id,
                    "running": runner.is_running(),
                }), "application/json")
            elif self.path == "/events":
                self._stream_events()
            elif self.path == "/timeline":
                # Full ordered history from the durable log -- the replay spine.
                events = [e.to_dict() for e in
                          runner.engine.log.events(runner.engine.instance_id)]
                self._send(200, json.dumps(events), "application/json")
            else:
                self._send(404, "not found")

        def _stream_events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q = runner.hub.subscribe()
            try:
                while True:
                    try:
                        event = q.get(timeout=15)
                        payload = json.dumps(event)
                        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")  # heartbeat
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                runner.hub.unsubscribe(q)

    return Handler


def serve(docs: Optional[str], goal: str, cycles: int = 1,
          provider_name: Optional[str] = None, db_path: str = "sage_state.db",
          host: str = "127.0.0.1", port: int = 8765) -> None:
    html = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")
    runner = SageRunner(docs, goal, cycles, provider_name, db_path)
    server = ThreadingHTTPServer((host, port), _make_handler(runner, html))
    url = f"http://{host}:{port}"
    print(f"SAGE God-View live at {url}  (provider: {runner.provider_name})")
    print("Open it in a browser. Ctrl-C to stop.")
    # Give the browser a beat to connect before the run floods events.
    threading.Timer(1.2, runner.start).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping...")
        server.shutdown()
        runner.engine.close()
