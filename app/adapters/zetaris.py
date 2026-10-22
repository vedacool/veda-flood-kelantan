"""Zetaris adapter: run_sql() is the only way VEDA reads data (live, record, or SAMPLE_MODE replay).

    from app.adapters import zetaris
    r = zetaris.run_sql("SELECT ...", agent="Data", purpose="latest river levels")
    r.columns, r.rows, r.source          # source = "zetaris-live" | "zetaris-replay"

Modes (from env):
    live (default)        POST to ZETARIS_API_URL/sql-editor/sqls/run
    ZETARIS_RECORD=true   live, and save each result to data/fixtures/zetaris/<query_hash>.json
    SAMPLE_MODE=true      never touch the network; replay the fixture for this exact SQL

Check from the command line:  python -m app.adapters.zetaris "SELECT 1 AS x"
"""
import hashlib
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests

from app import trace

FIXTURES = trace.ROOT / "data" / "fixtures" / "zetaris"
BACKOFF_S = (2, 4)       # network / 5xx retries
TIMEOUT_S = 120
_sleep = time.sleep      # patched in tests

READ_ONLY = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
DDL_ALLOWED = re.compile(
    r"^\s*(CREATE\s+LIGHTNING\s+REST\s+TABLE|CREATE\s+(OR\s+REPLACE\s+)?SCHEMASTORE\s+VIEW|CACHE\s+TABLE"
    r"|DROP\s+LIGHTNING\s+DATABASE\s+TABLE|REGISTER\s+DATASOURCE\s+TABLES)\b", re.IGNORECASE)
NUMBER = re.compile(r"^-?(0|[1-9]\d*)(\.\d+)?([eE][-+]?\d+)?$")  # no leading zeros: "0740121" stays text


class ZetarisError(Exception):
    """A Zetaris call failed. `kind` tells the caller what to do:
    auth | sql | source_unavailable | network | no_fixture | not_allowed."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


@dataclass
class SqlResult:
    """What one run_sql() call returns."""
    sql: str
    query_hash: str
    columns: list
    rows: list
    source: str                 # zetaris-live | zetaris-replay
    duration_ms: int
    fetched_at: str             # when Zetaris produced the rows (recording time on replay)
    records: list = field(default_factory=list)  # rows as dicts {column: value}

    @property
    def row_count(self):
        return len(self.rows)


def _flag(name):
    return os.getenv(name, "false").strip().lower() == "true"


def normalize_sql(sql):
    """One statement, trailing ; removed, whitespace collapsed. Raises ZetarisError(not_allowed)."""
    text = " ".join((sql or "").split()).rstrip(";").strip()
    if not text:
        raise ZetarisError("not_allowed", "empty SQL")
    if ";" in re.sub(r"'[^']*'|\"[^\"]*\"", "", text):
        raise ZetarisError("not_allowed", "only one SQL statement per call")
    return text


def query_hash(sql):
    """Stable 16-char id for a normalised SQL string (fixture file name)."""
    return hashlib.sha256(normalize_sql(sql).encode("utf-8")).hexdigest()[:16]


def coerce(value):
    """Zetaris returns text: turn numbers into int/float, keep everything else (IDs, dates) as text."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    v = value.strip()
    if v == "" or v.lower() == "null":
        return None
    if NUMBER.match(v):
        return float(v) if any(c in v for c in ".eE") else int(v)
    return value


def _config():
    url = os.getenv("ZETARIS_API_URL", "").strip().rstrip("/")
    key = os.getenv("ZETARIS_API_KEY", "").strip()
    if not url or not key:
        raise ZetarisError("auth", "ZETARIS_API_URL / ZETARIS_API_KEY not set")
    return url, key, os.getenv("ZETARIS_ORG_ID", "1").strip() or "1"


def _post(sql, limit):
    url, key, org = _config()
    headers = {"Authorization": f"Bearer {key}", "X-Org-ID": org, "X-Request-ID": str(uuid.uuid4()),
               "Content-Type": "application/json"}
    body = {"queryId": str(uuid.uuid4()), "sql": sql, "source": "SqlEditor", "limit": limit}
    return requests.post(f"{url}/sql-editor/sqls/run", headers=headers, json=body, timeout=TIMEOUT_S)


def _classify(status, message):
    if status == 401:
        return "auth", "Zetaris refused the API key (401) - check ZETARIS_API_KEY"
    if "REST API call failed" in message or "Server returned HTTP response code" in message:
        return "source_unavailable", message   # e.g. data.gov.my 429 behind a REST table
    if status >= 500:
        return "network", message
    return "sql", message


def _live(sql, limit, agent, label, tolerate=None):
    """POST with retry on network/5xx. Returns (payload, attempts).
    If `tolerate` is in Zetaris's error message, returns ({"tolerated": message}, attempts) instead of failing."""
    attempt = 0
    while True:
        attempt += 1
        t0 = time.perf_counter()
        try:
            r = _post(sql, limit)
            try:
                payload = r.json()
            except ValueError:
                payload = {"msg": r.text[:300]}
            if r.ok:
                return payload, attempt
            kind, message = _classify(r.status_code, str(payload.get("msg", r.text))[:400])
            if tolerate and tolerate in message:
                return {"tolerated": message}, attempt
        except (requests.ConnectionError, requests.Timeout) as e:
            kind, message = "network", f"cannot reach Zetaris ({type(e).__name__})"
        ms = int((time.perf_counter() - t0) * 1000)
        if kind != "network" or attempt > len(BACKOFF_S):
            trace.step(agent, "zetaris.run_sql", input_summary=label, output_summary=message, status="failed",
                       source="zetaris-live", retry_count=attempt - 1, duration_ms=ms,
                       decision=f"Zetaris error ({kind}) - caller must fall back", details={"kind": kind})
            raise ZetarisError(kind, message)
        wait = BACKOFF_S[attempt - 1]
        trace.step(agent, "zetaris.run_sql", input_summary=label, output_summary=message, status="retrying",
                   source="zetaris-live", retry_count=attempt, duration_ms=ms, decision=f"Retrying in {wait}s")
        _sleep(wait)


def _save_fixture(qh, sql, columns, raw_rows, fetched_at):
    FIXTURES.mkdir(parents=True, exist_ok=True)
    doc = {"sql": sql, "query_hash": qh, "recorded_at": fetched_at, "columns": columns, "rows": raw_rows}
    (FIXTURES / f"{qh}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                                         newline="\n")


def _load_fixture(qh):
    path = FIXTURES / f"{qh}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_sql(sql, agent, purpose=None, limit=1000):
    """Run one read-only SQL statement through Zetaris (or replay it in SAMPLE_MODE). Returns SqlResult."""
    text = normalize_sql(sql)
    qh = query_hash(text)
    label = purpose or text
    if not READ_ONLY.match(text):
        trace.step(agent, "zetaris.run_sql", input_summary=label, output_summary="refused: not SELECT/WITH",
                   status="failed", source="zetaris", decision="run_sql is read-only; use run_ddl for setup")
        raise ZetarisError("not_allowed", "run_sql only accepts SELECT / WITH; use run_ddl for allowed DDL")

    t0 = time.perf_counter()
    attempts = 1
    if _flag("SAMPLE_MODE"):
        doc = _load_fixture(qh)
        if doc is None:
            trace.step(agent, "zetaris.run_sql", input_summary=label, output_summary=f"no fixture {qh}.json",
                       status="failed", source="zetaris-replay", decision="SAMPLE_MODE has no recording of this query",
                       details={"query_hash": qh, "sql": text})
            raise ZetarisError("no_fixture", f"SAMPLE_MODE: no recorded result for this query ({qh})")
        columns, raw_rows, fetched_at, source = doc["columns"], doc["rows"], doc["recorded_at"], "zetaris-replay"
    else:
        payload, attempts = _live(text, limit, agent, label)
        columns, raw_rows = payload.get("headers") or [], payload.get("data") or []
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        source = "zetaris-live"
        if _flag("ZETARIS_RECORD"):
            _save_fixture(qh, text, columns, raw_rows, fetched_at)

    rows = [[coerce(v) for v in row] for row in raw_rows]
    records = [dict(zip(columns, row)) for row in rows]
    ms = int((time.perf_counter() - t0) * 1000)
    recorded = source == "zetaris-live" and _flag("ZETARIS_RECORD")
    trace.step(agent, "zetaris.run_sql", input_summary=label,
               output_summary=f"{len(rows)} rows x {len(columns)} columns ({', '.join(map(str, columns[:6]))})",
               source=source, retry_count=attempts - 1, duration_ms=ms,
               decision=("Recorded fixture for SAMPLE_MODE" if recorded else None),
               details={"query_hash": qh, "sql": text, "rows": len(rows), "fetched_at": fetched_at})
    return SqlResult(sql=text, query_hash=qh, columns=columns, rows=rows, source=source, duration_ms=ms,
                     fetched_at=fetched_at, records=records)


def run_ddl(sql, agent, purpose=None):
    """Run one allow-listed DDL statement (setup / self-healing). 'Already exists' counts as success.
    Returns True if Zetaris applied it, False if it already existed. Never runs in SAMPLE_MODE."""
    text = normalize_sql(sql)
    label = purpose or text
    if not DDL_ALLOWED.match(text):
        trace.step(agent, "zetaris.run_ddl", input_summary=label, output_summary="refused: not on DDL allow-list",
                   status="failed", source="zetaris", decision="Only allow-listed DDL may run")
        raise ZetarisError("not_allowed", "DDL not on the allow-list")
    if _flag("SAMPLE_MODE"):
        raise ZetarisError("not_allowed", "SAMPLE_MODE: DDL is not replayed")
    t0 = time.perf_counter()
    payload, _ = _live(text, 1, agent, label, tolerate="already exists")
    applied = "tolerated" not in payload
    note = "applied" if applied else "already exists - treated as success"
    trace.step(agent, "zetaris.run_ddl", input_summary=label, output_summary=note, source="zetaris-live",
               duration_ms=int((time.perf_counter() - t0) * 1000), details={"sql": text})
    return applied


def main(argv):
    """CLI check: run one SELECT and print the rows."""
    from dotenv import load_dotenv
    load_dotenv(trace.ROOT / ".env")
    sql = " ".join(argv[1:]) or "SELECT 1 AS x"
    trace.start_run(f"zetaris CLI: {sql}")
    try:
        r = run_sql(sql, agent="Data", purpose="CLI check")
    except ZetarisError as e:
        trace.end_run("failed", f"{e.kind}: {e}")
        print(f"FAILED ({e.kind}): {e}")
        return 1
    print(r.columns)
    for row in r.rows[:20]:
        print(row)
    print(f"source={r.source} rows={r.row_count} hash={r.query_hash}")
    print("trace:", trace.end_run())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
