"""The activity log -- SAGE's event-sourced spine.

One append-only log that serves two uses at once:
  1. the human status feed (via `summary`)
  2. recovery / resume (via `payload` + `status` + `checkpoint`)

Backed by SQLite so it is durable and queryable with zero external
services. The log IS the source of truth for run state.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Callable, List, Optional

from .models import Event, EventStatus


class ActivityLog:
    def __init__(self, db_path: str = "sage_state.db",
                 on_append: Optional[Callable[[Event], None]] = None):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # The engine runs on a worker thread while the web server reads the
        # log on request threads, so the connection is shared across threads.
        # That is safe here because every access goes through `self._lock`.
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()
        # Optional live hook -- e.g. print to a status feed as events land.
        self.on_append = on_append

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id   TEXT PRIMARY KEY,
                instance_id TEXT NOT NULL,
                timestamp  TEXT NOT NULL,
                actor      TEXT NOT NULL,
                action     TEXT NOT NULL,
                summary    TEXT NOT NULL,
                status     TEXT NOT NULL,
                parent_id  TEXT,
                payload    TEXT NOT NULL,
                checkpoint INTEGER NOT NULL,
                seq        INTEGER
            )
            """
        )
        self.conn.commit()

    def append(self, event: Event) -> Event:
        with self._lock:
            cur = self.conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 AS next FROM events WHERE instance_id = ?",
                (event.instance_id,),
            )
            seq = cur.fetchone()["next"]
            self.conn.execute(
                """
                INSERT INTO events (event_id, instance_id, timestamp, actor, action,
                                    summary, status, parent_id, payload, checkpoint, seq)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id, event.instance_id, event.timestamp, event.actor,
                    event.action, event.summary, event.status.value, event.parent_id,
                    json.dumps(event.payload), int(event.checkpoint), seq,
                ),
            )
            self.conn.commit()
        # Fire the live hook outside the lock so subscribers can't deadlock us.
        if self.on_append:
            self.on_append(event)
        return event

    def events(self, instance_id: str) -> List[Event]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE instance_id = ? ORDER BY seq", (instance_id,)
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def last_checkpoint(self, instance_id: str) -> Optional[Event]:
        with self._lock:
            row = self.conn.execute(
                """
                SELECT * FROM events WHERE instance_id = ? AND checkpoint = 1
                ORDER BY seq DESC LIMIT 1
                """,
                (instance_id,),
            ).fetchone()
        return self._row_to_event(row) if row else None

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
        return Event(
            event_id=row["event_id"],
            instance_id=row["instance_id"],
            timestamp=row["timestamp"],
            actor=row["actor"],
            action=row["action"],
            summary=row["summary"],
            status=EventStatus(row["status"]),
            parent_id=row["parent_id"],
            payload=json.loads(row["payload"]),
            checkpoint=bool(row["checkpoint"]),
        )

    def close(self) -> None:
        self.conn.close()
