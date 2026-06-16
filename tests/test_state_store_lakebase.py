"""Tests for the LakebaseStateStore class (no live DB required).

These tests verify the class structure, SQL statement generation, and
factory function routing without connecting to a real Postgres instance.
"""
from __future__ import annotations
import json
import unittest.mock as mock
from pathlib import Path


# -- LakebaseStateStore importable -------------------------------------------

def test_lakebase_store_class_importable():
    from src.state_store import LakebaseStateStore
    assert LakebaseStateStore is not None


def test_get_state_store_importable():
    from src.state_store import get_state_store
    assert callable(get_state_store)


def test_state_store_importable():
    from src.state_store import StateStore
    assert StateStore is not None


# -- Factory routing ----------------------------------------------------------

def test_get_state_store_returns_sqlite_by_default(monkeypatch):
    monkeypatch.setenv("STATE_STORE_MODE", "sqlite")
    import importlib
    import src.config as cfg
    importlib.reload(cfg)
    import src.state_store as ss
    importlib.reload(ss)
    from src.state_store import StateStore, get_state_store
    result = get_state_store()
    assert isinstance(result, StateStore)


def test_get_state_store_returns_lakebase_when_mode_set(monkeypatch):
    monkeypatch.setenv("STATE_STORE_MODE", "lakebase")
    import importlib
    import src.config as cfg
    importlib.reload(cfg)
    import src.state_store as ss
    importlib.reload(ss)

    dummy_conn = mock.MagicMock()
    dummy_conn.__enter__ = mock.MagicMock(return_value=dummy_conn)
    dummy_conn.__exit__ = mock.MagicMock(return_value=False)

    with mock.patch("psycopg.connect", return_value=dummy_conn):
        from src.state_store import LakebaseStateStore, get_state_store
        store = get_state_store()
        assert isinstance(store, LakebaseStateStore)


# -- Schema SQL sanity --------------------------------------------------------

def test_pg_schema_stmts_creates_schema():
    from src.state_store import _PG_SCHEMA_STMTS
    first = _PG_SCHEMA_STMTS[0]
    assert "CREATE SCHEMA" in first.upper()
    assert "trustroute_ai_state" in first


def test_pg_schema_stmts_has_three_tables():
    from src.state_store import _PG_SCHEMA_STMTS
    table_stmts = [s for s in _PG_SCHEMA_STMTS if "CREATE TABLE" in s.upper()]
    assert len(table_stmts) == 3


def test_pg_schema_stmts_sessions_table():
    from src.state_store import _PG_SCHEMA_STMTS
    sessions_stmt = next(s for s in _PG_SCHEMA_STMTS if "sessions" in s)
    assert "trustroute_ai_state.sessions" in sessions_stmt
    assert "id" in sessions_stmt
    assert "created_at" in sessions_stmt
    assert "plan_text" in sessions_stmt
    assert "lineage_json" in sessions_stmt


def test_pg_schema_stmts_feedback_table():
    from src.state_store import _PG_SCHEMA_STMTS
    fb_stmt = next(s for s in _PG_SCHEMA_STMTS if "feedback" in s)
    assert "trustroute_ai_state.feedback" in fb_stmt
    assert "rating" in fb_stmt


def test_pg_schema_stmts_shortlists_table():
    from src.state_store import _PG_SCHEMA_STMTS
    sl_stmt = next(s for s in _PG_SCHEMA_STMTS if "facility_shortlists" in s)
    assert "trustroute_ai_state.facility_shortlists" in sl_stmt
    assert "facility_name" in sl_stmt


# -- LakebaseStateStore mock-connect round-trip ------------------------------

def _make_mock_conn():
    conn = mock.MagicMock()
    conn.__enter__ = mock.MagicMock(return_value=conn)
    conn.__exit__ = mock.MagicMock(return_value=False)
    return conn


def test_lakebase_save_session_uses_parameterised_query():
    dummy_conn = _make_mock_conn()
    with mock.patch("psycopg.connect", return_value=dummy_conn):
        from src.state_store import LakebaseStateStore
        store = LakebaseStateStore()
        sid = store.save_session(
            raw_text="test text",
            profile={"age": 25},
            plan_text="Plan A",
            plan_method="claude",
        )
        assert sid
        calls = [str(c) for c in dummy_conn.execute.call_args_list]
        assert any("INSERT INTO trustroute_ai_state.sessions" in c for c in calls)


def test_lakebase_save_feedback_uses_parameterised_query():
    dummy_conn = _make_mock_conn()
    with mock.patch("psycopg.connect", return_value=dummy_conn):
        from src.state_store import LakebaseStateStore
        store = LakebaseStateStore()
        fid = store.save_feedback(session_id="s1", rating="Helpful")
        assert fid
        calls = [str(c) for c in dummy_conn.execute.call_args_list]
        assert any("INSERT INTO trustroute_ai_state.feedback" in c for c in calls)


def test_lakebase_get_recent_sessions_queries_correct_table():
    dummy_conn = _make_mock_conn()
    cur = mock.MagicMock()
    cur.description = [("id",), ("created_at",)]
    cur.fetchall.return_value = []
    dummy_conn.execute.return_value = cur
    with mock.patch("psycopg.connect", return_value=dummy_conn):
        from src.state_store import LakebaseStateStore
        store = LakebaseStateStore()
        rows = store.get_recent_sessions(5)
        assert isinstance(rows, list)
        calls = [str(c) for c in dummy_conn.execute.call_args_list]
        assert any("trustroute_ai_state.sessions" in c for c in calls)


def test_lakebase_get_recent_feedback_queries_correct_table():
    dummy_conn = _make_mock_conn()
    cur = mock.MagicMock()
    cur.description = [("id",), ("rating",)]
    cur.fetchall.return_value = []
    dummy_conn.execute.return_value = cur
    with mock.patch("psycopg.connect", return_value=dummy_conn):
        from src.state_store import LakebaseStateStore
        store = LakebaseStateStore()
        rows = store.get_recent_feedback(5)
        assert isinstance(rows, list)
        calls = [str(c) for c in dummy_conn.execute.call_args_list]
        assert any("trustroute_ai_state.feedback" in c for c in calls)


# -- app.yaml existence and content ------------------------------------------

def test_app_yaml_exists():
    assert Path("app.yaml").exists(), "app.yaml not found"


def test_app_yaml_has_streamlit_command():
    content = Path("app.yaml").read_text(encoding="utf-8")
    assert "streamlit" in content
    assert "app.py" in content


def test_app_yaml_has_lakebase_state_mode():
    content = Path("app.yaml").read_text(encoding="utf-8")
    assert "STATE_STORE_MODE" in content
    assert "lakebase" in content


def test_app_yaml_has_anthropic_key_ref():
    content = Path("app.yaml").read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY" in content
    assert "anthropic-api-key" in content


def test_app_yaml_has_pguser_ref():
    content = Path("app.yaml").read_text(encoding="utf-8")
    assert "PGUSER" in content
    assert "lakebase-user" in content


def test_app_yaml_has_pgpassword_ref():
    content = Path("app.yaml").read_text(encoding="utf-8")
    assert "PGPASSWORD" in content
    assert "lakebase-password" in content


def test_app_yaml_has_warehouse_config():
    content = Path("app.yaml").read_text(encoding="utf-8")
    assert "DATABRICKS_HTTP_PATH" in content
    assert "81c2d8e2b863208b" in content


def test_app_yaml_no_hardcoded_secrets():
    content = Path("app.yaml").read_text(encoding="utf-8")
    assert "sk-ant-" not in content
    assert "dapi" not in content
    assert "placeholder" not in content


# -- get_state_store imported in app.py ---------------------------------------

def test_app_imports_get_state_store():
    src = Path("app.py").read_text(encoding="utf-8")
    assert "get_state_store" in src


def test_app_uses_get_state_store_not_raw_statestore():
    src = Path("app.py").read_text(encoding="utf-8")
    assert "store = get_state_store()" in src
