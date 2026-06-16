"""Smoke test: verify Lakebase connection, schema creation, and basic round-trip.

Run this after setting the real lakebase-user / lakebase-password secrets and
redeploying the app, or locally with PG* env vars pointing at the endpoint:

  PGHOST=<host> PGDATABASE=databricks_postgres PGPORT=5432 PGSSLMODE=require \
  PGUSER=<role> PGPASSWORD=<password> python scripts/smoke_test_lakebase.py
"""
from __future__ import annotations
import os
import sys

REQUIRED_PG_VARS = ["PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD"]


def check_env() -> bool:
    missing = [v for v in REQUIRED_PG_VARS if not os.environ.get(v)]
    if missing:
        print(f"SKIP: missing env vars: {', '.join(missing)}")
        return False
    return True


def run_smoke() -> None:
    import psycopg

    print(f"Connecting to {os.environ.get('PGHOST')} / {os.environ.get('PGDATABASE')} ...")
    with psycopg.connect() as conn:
        row = conn.execute("SELECT current_database(), current_user").fetchone()
        print(f"  database={row[0]}  user={row[1]}")

    print("Creating schema trustroute_ai_state ...")
    with psycopg.connect() as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS trustroute_ai_state")

    print("Creating tables ...")
    with psycopg.connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS trustroute_ai_state.sessions (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                raw_text TEXT, profile_json TEXT, plan_text TEXT,
                plan_method TEXT, district_norm TEXT, state_norm TEXT,
                lineage_json TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS trustroute_ai_state.feedback (
                id TEXT PRIMARY KEY, session_id TEXT,
                created_at TEXT NOT NULL, rating TEXT NOT NULL, comment TEXT
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS trustroute_ai_state.facility_shortlists (
                id TEXT PRIMARY KEY, session_id TEXT,
                created_at TEXT NOT NULL, facility_name TEXT NOT NULL,
                facility_data TEXT, user_note TEXT
            )"""
        )

    print("Testing state store round-trip ...")
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

    from src.state_store import LakebaseStateStore
    lb = LakebaseStateStore()

    session_id = lb.save_session(
        raw_text="Smoke test family description",
        profile={"test": True},
        plan_text="Smoke test plan",
        plan_method="smoke_test",
        district_norm="test_district",
        state_norm="test_state",
    )
    print(f"  saved session: {session_id}")

    sessions = lb.get_recent_sessions(1)
    assert sessions and sessions[0]["id"] == session_id, "get_recent_sessions mismatch"

    feedback_id = lb.save_feedback(session_id=session_id, rating="Helpful", comment="smoke test")
    print(f"  saved feedback: {feedback_id}")

    recent_feedback = lb.get_recent_feedback(1)
    assert recent_feedback and recent_feedback[0]["id"] == feedback_id, "get_recent_feedback mismatch"

    shortlist_id = lb.save_shortlist_item(
        session_id=session_id,
        facility_name="Smoke Test Clinic",
        facility_data={"address": "1 Test Road"},
    )
    print(f"  saved shortlist item: {shortlist_id}")

    items = lb.get_shortlist(session_id)
    assert items and items[0]["id"] == shortlist_id, "get_shortlist mismatch"

    print("All checks passed.")


if __name__ == "__main__":
    if not check_env():
        sys.exit(0)
    try:
        run_smoke()
    except Exception as exc:
        print(f"FAIL: {exc}")
        sys.exit(1)
