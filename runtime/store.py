from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AgentState


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteRunStore:
    """Checkpoint store and append-only audit log for one runtime."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                state_version INTEGER NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(run_id, seq),
                FOREIGN KEY(run_id) REFERENCES runs(run_id)
            );
            CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, seq);
            """
        )
        self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def save_checkpoint(self, state: AgentState, *, event_type: str, payload: dict[str, Any] | None = None) -> None:
        with self._lock:
            state.updated_at = utc_now()
            encoded = state.model_dump_json()
            with self._connection:
                existing = self._connection.execute(
                    "SELECT state_version FROM runs WHERE run_id = ?", (state.run_id,)
                ).fetchone()
                previous_version = existing["state_version"] if existing else -1
                if existing and state.state_version <= previous_version:
                    raise ValueError(
                        f"stale checkpoint for {state.run_id}: {state.state_version} <= {previous_version}"
                    )
                self._connection.execute(
                    """INSERT INTO runs(run_id,state_version,stage,status,state_json,updated_at)
                       VALUES(?,?,?,?,?,?)
                       ON CONFLICT(run_id) DO UPDATE SET state_version=excluded.state_version,
                       stage=excluded.stage,status=excluded.status,state_json=excluded.state_json,
                       updated_at=excluded.updated_at""",
                    (state.run_id, state.state_version, state.stage, state.status, encoded, state.updated_at),
                )
                seq_row = self._connection.execute(
                    "SELECT COALESCE(MAX(seq), -1) + 1 AS next_seq FROM events WHERE run_id = ?",
                    (state.run_id,),
                ).fetchone()
                event_payload = payload or {"stage": state.stage, "status": state.status}
                self._connection.execute(
                    "INSERT INTO events(run_id,seq,event_type,created_at,payload_json) VALUES(?,?,?,?,?)",
                    (state.run_id, seq_row["next_seq"], event_type, utc_now(), json.dumps(event_payload, ensure_ascii=False)),
                )

    def load(self, run_id: str) -> AgentState | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT state_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            return AgentState.model_validate_json(row["state_json"]) if row else None

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT seq,event_type,created_at,payload_json FROM events WHERE run_id = ? ORDER BY seq",
                (run_id,),
            ).fetchall()
            return [
                {"seq": row["seq"], "event_type": row["event_type"], "created_at": row["created_at"], "payload": json.loads(row["payload_json"])}
                for row in rows
            ]

    def raw_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            return dict(row) if row else None
