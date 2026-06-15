"""Export small local sample JSON files from the trusted Unity Catalog tables.

Read-only. Used for local-first (Gate A) development so the Streamlit app can run
against realistic data without a live Databricks connection.

Source of truth:  `benefits_navigator`.`trusted`
Outputs (into sample_data/):
    facilities.json
    india_post_pincode_directory.json
    pincode_district_lookup.json
    nfhs_5_district_health_indicators.json
    support_pathways.json

Two connection transports (auto-selected):
  1. databricks-sql-connector  -- uses .env: DATABRICKS_SERVER_HOSTNAME,
     DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN  (the path judges/you use).
  2. Databricks CLI Statement Execution  -- uses an authenticated CLI profile
     (--profile / DATABRICKS_CONFIG_PROFILE) and a warehouse id; no PAT needed
     in the environment. Handy for agent/CI runs.

Secrets are never printed. Missing configuration fails loudly with a clear message.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()  # load .env from cwd / project root if present
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
UC_CATALOG = os.environ.get("UC_CATALOG", "benefits_navigator")
UC_SCHEMA = os.environ.get("UC_SCHEMA", "trusted")
OUT_DIR = Path(__file__).resolve().parent.parent / "sample_data"

# Demo PIN codes whose rows must appear in the local sample so the demo works.
DEMO_PINCODES = ["560001"]

# Per-table sample limits (kept small for local development).
LIMITS = {
    "facilities": 25,
    "india_post_pincode_directory": 100,
    "pincode_district_lookup": 100,
    "nfhs_5_district_health_indicators": 50,
    "support_pathways": None,  # tiny reference table -> take all rows
}


def fq(table: str) -> str:
    return f"`{UC_CATALOG}`.`{UC_SCHEMA}`.`{table}`"


def _sql_str_list(values) -> str:
    """Render a Python list as a SQL IN-list of quoted strings (escaped)."""
    return ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)


# ---------------------------------------------------------------------------
# Transport selection
# ---------------------------------------------------------------------------
class Connector:
    """databricks-sql-connector transport (env/.env based)."""

    def __init__(self, host: str, http_path: str, token: str):
        from databricks import sql

        self._conn = sql.connect(
            server_hostname=host, http_path=http_path, access_token=token
        )

    def query(self, statement: str):
        cur = self._conn.cursor()
        try:
            cur.execute(statement)
            cols = [c[0] for c in cur.description]
            rows = [list(r) for r in cur.fetchall()]
            return cols, rows
        finally:
            cur.close()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


class CliStatement:
    """Databricks CLI Statement Execution transport (profile based)."""

    def __init__(self, profile: str, warehouse_id: str):
        self._profile = profile
        self._warehouse = warehouse_id

    def _api(self, method: str, path: str, body=None):
        cmd = ["databricks", "api", method, path, "-p", self._profile]
        if body is not None:
            cmd += ["--json", json.dumps(body)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip())
        return json.loads(r.stdout)

    def query(self, statement: str):
        body = {
            "warehouse_id": self._warehouse,
            "statement": statement,
            "wait_timeout": "50s",
            "on_wait_timeout": "CONTINUE",
            "format": "JSON_ARRAY",
            "disposition": "INLINE",
        }
        resp = self._api("post", "/api/2.0/sql/statements/", body)
        sid = resp.get("statement_id")
        state = resp["status"]["state"]
        while state in ("PENDING", "RUNNING"):
            time.sleep(3)
            resp = self._api("get", f"/api/2.0/sql/statements/{sid}")
            state = resp["status"]["state"]
        if state != "SUCCEEDED":
            msg = resp["status"].get("error", {}).get("message", "")
            raise RuntimeError(f"[{state}] {msg.splitlines()[0] if msg else ''}")
        cols = [c["name"] for c in resp["manifest"]["schema"]["columns"]]
        rows = resp.get("result", {}).get("data_array", []) or []
        return cols, rows

    def close(self):
        pass


def build_transport(args):
    host = os.environ.get("DATABRICKS_SERVER_HOSTNAME")
    http_path = args.http_path or os.environ.get("DATABRICKS_HTTP_PATH")
    token = os.environ.get("DATABRICKS_TOKEN")
    profile = args.profile or os.environ.get("DATABRICKS_CONFIG_PROFILE")

    if host and http_path and token:
        print("Connecting via databricks-sql-connector (env/.env).")
        return Connector(host, http_path, token)

    warehouse_id = args.warehouse
    if not warehouse_id and http_path:
        m = re.search(r"/warehouses/([0-9a-fA-F]+)", http_path)
        if m:
            warehouse_id = m.group(1)
    if profile and warehouse_id:
        print(f"Connecting via Databricks CLI profile '{profile}' (statement execution).")
        return CliStatement(profile, warehouse_id)

    # Nothing usable -> fail loudly, listing exactly what's missing.
    missing = []
    if not host:
        missing.append("DATABRICKS_SERVER_HOSTNAME")
    if not http_path:
        missing.append("DATABRICKS_HTTP_PATH (or --http-path/--warehouse)")
    if not token:
        missing.append("DATABRICKS_TOKEN")
    sys.exit(
        "ERROR: no usable Databricks connection.\n"
        "Provide either (a) env/.env: "
        + ", ".join(missing)
        + "\n   or (b) --profile <name> together with --warehouse <id> "
        "(or DATABRICKS_HTTP_PATH so the warehouse id can be parsed)."
    )


# ---------------------------------------------------------------------------
# Sampling queries (demo-aware ordering, then LIMIT)
# ---------------------------------------------------------------------------
def rows_to_dicts(cols, rows):
    return [dict(zip(cols, r)) for r in rows]


def export(transport):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pins = _sql_str_list(DEMO_PINCODES)

    # Resolve demo districts/states so facilities & NFHS samples include them.
    demo_states, demo_districts = [], []
    try:
        cols, rows = transport.query(
            f"SELECT DISTINCT state_norm, district_norm FROM {fq('pincode_district_lookup')} "
            f"WHERE pincode IN ({pins})"
        )
        for r in rows_to_dicts(cols, rows):
            if r.get("state_norm"):
                demo_states.append(str(r["state_norm"]).upper().strip())
            if r.get("district_norm"):
                demo_districts.append(str(r["district_norm"]).upper().strip())
    except Exception as e:
        print(f"  (warning: could not resolve demo districts: {e})")

    states_in = _sql_str_list(demo_states) if demo_states else "''"
    districts_in = _sql_str_list(demo_districts) if demo_districts else "''"

    queries = {
        "facilities": (
            f"SELECT * FROM {fq('facilities')} ORDER BY CASE "
            f"WHEN address_zipOrPostcode IN ({pins}) THEN 0 "
            f"WHEN upper(trim(address_stateOrRegion)) IN ({states_in}) THEN 1 "
            f"ELSE 2 END LIMIT {LIMITS['facilities']}"
        ),
        "india_post_pincode_directory": (
            f"SELECT * FROM {fq('india_post_pincode_directory')} ORDER BY CASE "
            f"WHEN pincode IN ({pins}) THEN 0 ELSE 1 END "
            f"LIMIT {LIMITS['india_post_pincode_directory']}"
        ),
        "pincode_district_lookup": (
            f"SELECT * FROM {fq('pincode_district_lookup')} ORDER BY CASE "
            f"WHEN pincode IN ({pins}) THEN 0 ELSE 1 END "
            f"LIMIT {LIMITS['pincode_district_lookup']}"
        ),
        # NFHS names districts differently from pincode_district_lookup
        # (e.g. lookup 'BENGALURU URBAN' vs NFHS 'Bangalore'), so bias by the
        # demo STATE to reliably include the demo district's health context.
        "nfhs_5_district_health_indicators": (
            f"SELECT * FROM {fq('nfhs_5_district_health_indicators')} ORDER BY CASE "
            f"WHEN upper(trim(district_name)) IN ({districts_in}) THEN 0 "
            f"WHEN upper(trim(state_ut)) IN ({states_in}) THEN 1 ELSE 2 END "
            f"LIMIT {LIMITS['nfhs_5_district_health_indicators']}"
        ),
        "support_pathways": f"SELECT * FROM {fq('support_pathways')}",
    }

    written = []
    for name, q in queries.items():
        cols, rows = transport.query(q)
        data = rows_to_dicts(cols, rows)
        out = OUT_DIR / f"{name}.json"
        with out.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        written.append((out.name, len(data)))
        print(f"  wrote {out.name:42} {len(data):>4} rows")
    return written


def main():
    ap = argparse.ArgumentParser(description="Export sample data from trusted UC tables.")
    ap.add_argument("--profile", help="Databricks CLI profile (fallback transport).")
    ap.add_argument("--warehouse", help="SQL warehouse id (for CLI transport).")
    ap.add_argument("--http-path", help="Override DATABRICKS_HTTP_PATH.")
    args = ap.parse_args()

    print(f"Source: `{UC_CATALOG}`.`{UC_SCHEMA}`  ->  {OUT_DIR}")
    transport = build_transport(args)
    try:
        written = export(transport)
    finally:
        transport.close()
    total = sum(n for _, n in written)
    print(f"Done. {len(written)} files, {total} total rows exported.")


if __name__ == "__main__":
    main()
