import json
import sqlite3
from pathlib import Path
from typing import Any

from storage.interfaces import EventStore, LearningStore, WrongCaseStore


class SQLiteStore(EventStore, WrongCaseStore, LearningStore):
    """Local SQLite storage for events, decisions, failures and learning data."""

    SCHEMA_VERSION = 1
    WRONG_STATUSES = {"new", "investigating", "replayed", "resolved"}

    def __init__(self, db_path: str | Path = "data/lp_rebalancer.db"):
        self.db_path = str(db_path)

        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    decision TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS wrong (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS to_learn (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT NOT NULL DEFAULT 'candidate',
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_events_type
                    ON events(event_type);

                CREATE INDEX IF NOT EXISTS idx_wrong_status
                    ON wrong(status);

                CREATE INDEX IF NOT EXISTS idx_learning_status
                    ON to_learn(status);
            """)

            db.execute(
                "INSERT OR IGNORE INTO schema_version(version) VALUES (?)",
                (self.SCHEMA_VERSION,),
            )

    @staticmethod
    def _json(payload: dict[str, Any]) -> str:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )

    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        if not event_type.strip():
            raise ValueError("event_type must not be empty")

        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO events(event_type, payload_json) VALUES (?, ?)",
                (event_type, self._json(payload)),
            )
            return int(cursor.lastrowid)

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")

        with self._connect() as db:
            rows = db.execute(
                """SELECT id, event_type, payload_json, created_at
                   FROM events ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def record_decision(
        self,
        decision: str,
        payload: dict[str, Any],
    ) -> int:
        if not decision.strip():
            raise ValueError("decision must not be empty")

        serialized = self._json(payload)

        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO decisions(decision, payload_json) VALUES (?, ?)",
                (decision, serialized),
            )
            decision_id = int(cursor.lastrowid)

            db.execute(
                "INSERT INTO events(event_type, payload_json) VALUES (?, ?)",
                (
                    "decision",
                    self._json({
                        "decision_id": decision_id,
                        "decision": decision,
                        "payload": payload,
                    }),
                ),
            )

            return decision_id

    def list_decisions(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent decisions, newest first."""
        if limit < 1:
            raise ValueError("limit must be positive")

        with self._connect() as db:
            rows = db.execute(
                """SELECT id, decision, payload_json, created_at
                   FROM decisions ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "decision": row["decision"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def record_wrong(
        self,
        category: str,
        payload: dict[str, Any],
    ) -> int:
        if not category.strip():
            raise ValueError("category must not be empty")

        serialized = self._json(payload)

        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO wrong(category, payload_json) VALUES (?, ?)",
                (category, serialized),
            )
            wrong_id = int(cursor.lastrowid)

            db.execute(
                "INSERT INTO events(event_type, payload_json) VALUES (?, ?)",
                (
                    "wrong",
                    self._json({
                        "wrong_id": wrong_id,
                        "category": category,
                        "payload": payload,
                    }),
                ),
            )

            return wrong_id

    def update_wrong_status(self, case_id: int, status: str) -> None:
        if status not in self.WRONG_STATUSES:
            raise ValueError(f"Invalid wrong-case status: {status}")

        with self._connect() as db:
            cursor = db.execute(
                """UPDATE wrong
                   SET status = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (status, case_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Wrong case not found: {case_id}")

    def add_candidate(self, payload: dict[str, Any]) -> int:
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO to_learn(payload_json) VALUES (?)",
                (self._json(payload),),
            )
            return int(cursor.lastrowid)

    def close(self) -> None:
        """Connections are short-lived; nothing persistent needs closing."""
        return None
