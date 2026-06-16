from __future__ import annotations
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from .config import SQLITE_PATH, STATE_STORE_MODE

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    raw_text      TEXT,
    profile_json  TEXT,
    plan_text     TEXT,
    plan_method   TEXT,
    district_norm TEXT,
    state_norm    TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id            TEXT PRIMARY KEY,
    session_id    TEXT,
    created_at    TEXT NOT NULL,
    rating        TEXT NOT NULL,
    comment       TEXT
);

CREATE TABLE IF NOT EXISTS facility_shortlists (
    id            TEXT PRIMARY KEY,
    session_id    TEXT,
    created_at    TEXT NOT NULL,
    facility_name TEXT NOT NULL,
    facility_data TEXT,
    user_note     TEXT
);
"""


class StateStore:
    def __init__(self, path: Path = SQLITE_PATH):
        self._path = str(path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN lineage_json TEXT")
            except Exception:
                pass  # column already exists

    def save_session(
        self,
        raw_text: str,
        profile: dict,
        plan_text: str,
        plan_method: str,
        district_norm: str = "",
        state_norm: str = "",
        lineage: dict | None = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions "
                "(id, created_at, raw_text, profile_json, plan_text, plan_method, "
                "district_norm, state_norm, lineage_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    now,
                    raw_text,
                    json.dumps(profile, default=str),
                    plan_text,
                    plan_method,
                    district_norm,
                    state_norm,
                    json.dumps(lineage, default=str) if lineage else None,
                ),
            )
        return session_id

    def get_recent_sessions(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_feedback(
        self,
        session_id: str | None,
        rating: str,
        comment: str = "",
    ) -> str:
        feedback_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO feedback (id, session_id, created_at, rating, comment) "
                "VALUES (?, ?, ?, ?, ?)",
                (feedback_id, session_id, now, rating, comment),
            )
        return feedback_id

    def save_shortlist_item(
        self,
        session_id: str | None,
        facility_name: str,
        facility_data: dict | None = None,
        user_note: str = "",
    ) -> str:
        item_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO facility_shortlists "
                "(id, session_id, created_at, facility_name, facility_data, user_note) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    item_id,
                    session_id,
                    now,
                    facility_name,
                    json.dumps(facility_data, default=str) if facility_data else None,
                    user_note,
                ),
            )
        return item_id

    def get_shortlist(self, session_id: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM facility_shortlists WHERE session_id = ? ORDER BY created_at DESC",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM facility_shortlists ORDER BY created_at DESC LIMIT 20"
                ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_feedback(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM feedback ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


_PG_SCHEMA_STMTS = [
    "CREATE SCHEMA IF NOT EXISTS trustroute_ai_state",
    """CREATE TABLE IF NOT EXISTS trustroute_ai_state.sessions (
        id            TEXT PRIMARY KEY,
        created_at    TEXT NOT NULL,
        raw_text      TEXT,
        profile_json  TEXT,
        plan_text     TEXT,
        plan_method   TEXT,
        district_norm TEXT,
        state_norm    TEXT,
        lineage_json  TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS trustroute_ai_state.feedback (
        id            TEXT PRIMARY KEY,
        session_id    TEXT,
        created_at    TEXT NOT NULL,
        rating        TEXT NOT NULL,
        comment       TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS trustroute_ai_state.facility_shortlists (
        id            TEXT PRIMARY KEY,
        session_id    TEXT,
        created_at    TEXT NOT NULL,
        facility_name TEXT NOT NULL,
        facility_data TEXT,
        user_note     TEXT
    )""",
]


def _pg_rows_to_dicts(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _pg_row_to_dict(cur) -> dict | None:
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


class LakebaseStateStore:
    """Postgres/Lakebase state store using psycopg v3.

    Reads connection details from standard PG* environment variables
    (PGHOST, PGDATABASE, PGPORT, PGSSLMODE) injected by the Databricks App
    platform when the lakebase-state resource is attached, plus PGUSER and
    PGPASSWORD from the lakebase-user / lakebase-password secrets.
    """

    def __init__(self) -> None:
        self._init_schema()

    def _connect(self):
        import psycopg
        return psycopg.connect()

    def _init_schema(self) -> None:
        import psycopg
        with psycopg.connect() as conn:
            for stmt in _PG_SCHEMA_STMTS:
                conn.execute(stmt)

    def save_session(
        self,
        raw_text: str,
        profile: dict,
        plan_text: str,
        plan_method: str,
        district_norm: str = "",
        state_norm: str = "",
        lineage: dict | None = None,
    ) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO trustroute_ai_state.sessions "
                "(id, created_at, raw_text, profile_json, plan_text, plan_method, "
                "district_norm, state_norm, lineage_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    session_id,
                    now,
                    raw_text,
                    json.dumps(profile, default=str),
                    plan_text,
                    plan_method,
                    district_norm,
                    state_norm,
                    json.dumps(lineage, default=str) if lineage else None,
                ),
            )
        return session_id

    def get_recent_sessions(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM trustroute_ai_state.sessions "
                "ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            return _pg_rows_to_dicts(cur)

    def get_session(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM trustroute_ai_state.sessions WHERE id = %s",
                (session_id,),
            )
            return _pg_row_to_dict(cur)

    def save_feedback(
        self,
        session_id: str | None,
        rating: str,
        comment: str = "",
    ) -> str:
        feedback_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO trustroute_ai_state.feedback "
                "(id, session_id, created_at, rating, comment) "
                "VALUES (%s, %s, %s, %s, %s)",
                (feedback_id, session_id, now, rating, comment),
            )
        return feedback_id

    def save_shortlist_item(
        self,
        session_id: str | None,
        facility_name: str,
        facility_data: dict | None = None,
        user_note: str = "",
    ) -> str:
        item_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO trustroute_ai_state.facility_shortlists "
                "(id, session_id, created_at, facility_name, facility_data, user_note) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    item_id,
                    session_id,
                    now,
                    facility_name,
                    json.dumps(facility_data, default=str) if facility_data else None,
                    user_note,
                ),
            )
        return item_id

    def get_shortlist(self, session_id: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if session_id:
                cur = conn.execute(
                    "SELECT * FROM trustroute_ai_state.facility_shortlists "
                    "WHERE session_id = %s ORDER BY created_at DESC",
                    (session_id,),
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM trustroute_ai_state.facility_shortlists "
                    "ORDER BY created_at DESC LIMIT 20"
                )
            return _pg_rows_to_dicts(cur)

    def get_recent_feedback(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM trustroute_ai_state.feedback "
                "ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            return _pg_rows_to_dicts(cur)


def get_state_store() -> StateStore | LakebaseStateStore:
    """Return the appropriate state store based on STATE_STORE_MODE env var."""
    if STATE_STORE_MODE == "lakebase":
        return LakebaseStateStore()
    return StateStore()
