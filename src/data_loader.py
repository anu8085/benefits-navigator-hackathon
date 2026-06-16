from __future__ import annotations
import json
from decimal import Decimal
from functools import lru_cache
from typing import Any

from .config import (
    DATA_MODE,
    DATABRICKS_HTTP_PATH,
    DATABRICKS_SERVER_HOSTNAME,
    DATABRICKS_TOKEN,
    SAMPLE_DATA_DIR,
    UC_CATALOG,
    UC_SCHEMA,
)

# Maps district_norm values (pincode_district_lookup) → NFHS district_name values (normalised)
_DISTRICT_ALIAS: dict[str, str] = {
    "BENGALURU URBAN": "BANGALORE",
    "BENGALURU RURAL": "BANGALORE RURAL",
    "MYSURU": "MYSORE",
    "KALABURAGI": "GULBARGA",
    "VIJAYAPURA": "BIJAPUR",
    "BELAGAVI": "BELGAUM",
    "BALLARI": "BELLARY",
    "SHIVAMOGGA": "SHIMOGA",
    "TUMAKURU": "TUMKUR",
    "DAVANAGERE": "DAVANGERE",
    "CHIKKAMAGALURU": "CHIKMAGALUR",
    "RAMANAGARA": "RAMANAGARAM",
}

# Ordered candidate NFHS district_name values to try for each district_norm.
# First match within the correct state wins; the district_norm itself is the final fallback.
_NFHS_ALIAS_CANDIDATES: dict[str, list[str]] = {
    "BENGALURU URBAN": ["BANGALORE", "BENGALURU URBAN", "BENGALURU", "BANGALORE URBAN"],
    "BENGALURU RURAL": ["BANGALORE RURAL", "BENGALURU RURAL"],
    "MYSURU": ["MYSORE", "MYSURU"],
    "KALABURAGI": ["GULBARGA", "KALABURAGI"],
    "VIJAYAPURA": ["BIJAPUR", "VIJAYAPURA"],
    "BELAGAVI": ["BELGAUM", "BELAGAVI"],
    "BALLARI": ["BELLARY", "BALLARI"],
    "SHIVAMOGGA": ["SHIMOGA", "SHIVAMOGGA"],
    "TUMAKURU": ["TUMKUR", "TUMAKURU"],
    "DAVANAGERE": ["DAVANGERE", "DAVANAGERE"],
    "CHIKKAMAGALURU": ["CHIKMAGALUR", "CHIKKAMAGALURU"],
    "RAMANAGARA": ["RAMANAGARAM", "RAMANAGARA"],
}

_UC_TABLES: set[str] = {
    "facilities",
    "india_post_pincode_directory",
    "pincode_district_lookup",
    "nfhs_5_district_health_indicators",
    "support_pathways",
}

_LOAD_CACHE: dict[str, list[dict]] = {}
_TABLE_STATUS: dict[str, dict] = {}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _qualified_table(name: str) -> str:
    return f"`{UC_CATALOG}`.`{UC_SCHEMA}`.`{name}`"


def _uc_config_error() -> str | None:
    missing = [
        key for key, value in [
            ("DATABRICKS_SERVER_HOSTNAME", DATABRICKS_SERVER_HOSTNAME),
            ("DATABRICKS_HTTP_PATH", DATABRICKS_HTTP_PATH),
            ("DATABRICKS_TOKEN", DATABRICKS_TOKEN),
        ] if not value
    ]
    if missing:
        return "Missing Databricks env vars: " + ", ".join(missing)
    return None


def _redact_http_path(path: str) -> str:
    if not path:
        return ""
    if len(path) <= 18:
        return path[:4] + "..."
    return f"{path[:12]}...{path[-6:]}"


@lru_cache(maxsize=1)
def _uc_connection():
    config_error = _uc_config_error()
    if config_error:
        raise RuntimeError(config_error)
    from databricks import sql

    return sql.connect(
        server_hostname=DATABRICKS_SERVER_HOSTNAME,
        http_path=DATABRICKS_HTTP_PATH,
        access_token=DATABRICKS_TOKEN,
    )


def _load_json(name: str) -> list[dict]:
    path = SAMPLE_DATA_DIR / f"{name}.json"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_uc_table(name: str) -> list[dict]:
    with _uc_connection().cursor() as cursor:
        cursor.execute(f"SELECT * FROM {_qualified_table(name)}")
        columns = [desc[0] for desc in cursor.description]
        return [
            {col: _json_safe(value) for col, value in zip(columns, row)}
            for row in cursor.fetchall()
        ]


def _norm(s: Any) -> str:
    return str(s or "").upper().strip()


def _safe_float(v: Any) -> float | None:
    try:
        if str(v).strip() in ("", "NA", "na", "None", "null"):
            return None
        return float(v)
    except (ValueError, TypeError):
        return None


def _load(name: str) -> list[dict]:
    if name in _LOAD_CACHE:
        return _LOAD_CACHE[name]

    if DATA_MODE == "uc" and name in _UC_TABLES:
        try:
            rows = _load_uc_table(name)
            _TABLE_STATUS[name] = {
                "source": "uc",
                "row_count": len(rows),
                "fallback_reason": None,
            }
            _LOAD_CACHE[name] = rows
            return rows
        except Exception as exc:
            rows = _load_json(name)
            _TABLE_STATUS[name] = {
                "source": "json_fallback",
                "row_count": len(rows),
                "fallback_reason": f"Unity Catalog load failed: {type(exc).__name__}",
            }
            _LOAD_CACHE[name] = rows
            return rows

    rows = _load_json(name)
    _TABLE_STATUS[name] = {
        "source": "json",
        "row_count": len(rows),
        "fallback_reason": None,
    }
    _LOAD_CACHE[name] = rows
    return rows


def get_data_source_status() -> dict:
    fallback_reasons = [
        s.get("fallback_reason")
        for s in _TABLE_STATUS.values()
        if s.get("fallback_reason")
    ]
    expected_statuses = {
        name: _TABLE_STATUS.get(name, {})
        for name in sorted(_UC_TABLES)
    }
    if DATA_MODE == "uc" and fallback_reasons:
        active_source = "json_fallback"
    elif DATA_MODE == "uc" and any(s.get("source") == "uc" for s in expected_statuses.values()):
        active_source = "uc"
    else:
        active_source = "json"
    return {
        "configured_mode": DATA_MODE,
        "active_source": active_source,
        "catalog": UC_CATALOG,
        "schema": UC_SCHEMA,
        "server_hostname": DATABRICKS_SERVER_HOSTNAME,
        "http_path_redacted": _redact_http_path(DATABRICKS_HTTP_PATH),
        "tables": dict(_TABLE_STATUS),
        "fallback_reason": fallback_reasons[0] if fallback_reasons else None,
    }


def load_pathways() -> list[dict]:
    return _load("support_pathways")


def load_scenarios() -> list[dict]:
    return _load("sample_scenarios")


def get_district_for_pincode(pincode: str) -> dict | None:
    """Return {district_norm, state_norm, lat, lon} for pincode, or None."""
    pincode = str(pincode).strip()

    for row in _load("pincode_district_lookup"):
        if str(row.get("pincode", "")).strip() == pincode:
            return {
                "district_norm": _norm(row.get("district_norm")),
                "state_norm": _norm(row.get("state_norm")),
                "lat": _safe_float(row.get("sample_latitude")),
                "lon": _safe_float(row.get("sample_longitude")),
            }

    # Fallback: india_post directory (less precise district names)
    for row in _load("india_post_pincode_directory"):
        if str(row.get("pincode", "")).strip() == pincode:
            return {
                "district_norm": _norm(row.get("district")),
                "state_norm": _norm(row.get("statename")),
                "lat": _safe_float(row.get("latitude")),
                "lon": _safe_float(row.get("longitude")),
            }

    return None


def _nfhs_alias_candidates(district_norm: str) -> list[str]:
    """Ordered alias candidates to try against NFHS district_name within the correct state."""
    specific = _NFHS_ALIAS_CANDIDATES.get(district_norm)
    if specific:
        return specific
    simple = _DISTRICT_ALIAS.get(district_norm)
    if simple and simple != district_norm:
        return [simple, district_norm]
    return [district_norm]


def get_nfhs_for_district(district_norm: str, state_norm: str) -> list[dict]:
    """Return NFHS rows, state-first filtered, then alias-priority matched."""
    rows = _load("nfhs_5_district_health_indicators")
    # Step 1: restrict to the correct state so we never cross-match another state
    state_rows = [r for r in rows if _norm(r.get("state_ut")) == state_norm]

    # Step 2: exact district match within state
    exact = [r for r in state_rows if _norm(r.get("district_name")) == district_norm]
    if exact:
        return exact

    # Step 3: alias candidates in priority order, within state
    for candidate in _nfhs_alias_candidates(district_norm):
        alias_matches = [r for r in state_rows if _norm(r.get("district_name")) == candidate]
        if alias_matches:
            return alias_matches

    # Step 4: state-level fallback (capped)
    return state_rows[:5]


def get_nfhs_lookup_trace(district_norm: str, state_norm: str) -> dict:
    """Describe how NFHS rows were resolved; useful for the debug tab."""
    rows = _load("nfhs_5_district_health_indicators")
    state_rows = [r for r in rows if _norm(r.get("state_ut")) == state_norm]
    candidates = _nfhs_alias_candidates(district_norm)

    exact = [r for r in state_rows if _norm(r.get("district_name")) == district_norm]
    if exact:
        return {
            "requested_district": district_norm,
            "requested_state": state_norm,
            "normalized_district": district_norm,
            "normalized_state": state_norm,
            "alias_candidates_tried": candidates,
            "state_row_count": len(state_rows),
            "match_type": "exact",
            "matched_district": _norm(exact[0].get("district_name")),
            "matched_state": _norm(exact[0].get("state_ut")),
            "candidate_row_count": len(exact),
        }

    for candidate in candidates:
        alias_matches = [r for r in state_rows if _norm(r.get("district_name")) == candidate]
        if alias_matches:
            return {
                "requested_district": district_norm,
                "requested_state": state_norm,
                "normalized_district": district_norm,
                "normalized_state": state_norm,
                "alias_candidates_tried": candidates,
                "state_row_count": len(state_rows),
                "match_type": "alias",
                "matched_district": _norm(alias_matches[0].get("district_name")),
                "matched_state": _norm(alias_matches[0].get("state_ut")),
                "candidate_row_count": len(alias_matches),
            }

    if state_rows:
        return {
            "requested_district": district_norm,
            "requested_state": state_norm,
            "normalized_district": district_norm,
            "normalized_state": state_norm,
            "alias_candidates_tried": candidates,
            "state_row_count": len(state_rows),
            "match_type": "state_fallback",
            "matched_district": None,
            "matched_state": state_norm,
            "candidate_row_count": min(len(state_rows), 5),
        }

    return {
        "requested_district": district_norm,
        "requested_state": state_norm,
        "normalized_district": district_norm,
        "normalized_state": state_norm,
        "alias_candidates_tried": candidates,
        "state_row_count": 0,
        "match_type": "missing",
        "matched_district": None,
        "matched_state": None,
        "candidate_row_count": 0,
    }


def get_facilities(pincode: str, district_norm: str, state_norm: str) -> list[dict]:
    """Return facilities sorted: exact pincode first, then same state, then rest."""
    rows = _load("facilities")

    def _sort_key(r: dict) -> int:
        z = _norm(r.get("address_zipOrPostcode"))
        s = _norm(r.get("address_stateOrRegion"))
        if z == _norm(pincode):
            return 0
        if s == state_norm:
            return 1
        return 2

    return sorted(rows, key=_sort_key)


def get_district_alias(district_norm: str) -> str:
    return _DISTRICT_ALIAS.get(district_norm, district_norm)


def list_nfhs_districts() -> list[str]:
    rows = _load("nfhs_5_district_health_indicators")
    return sorted({r.get("district_name", "").strip() for r in rows if r.get("district_name", "").strip()})
