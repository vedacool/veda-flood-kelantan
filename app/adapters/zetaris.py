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
import math
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from app import config, trace

FIXTURES = trace.ROOT / "data" / "fixtures" / "zetaris"
BACKOFF_S = (2, 4)       # network / 5xx retries
TIMEOUT_S = 120
_sleep = time.sleep      # patched in tests

READ_ONLY = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
# Words that make a statement write/DDL - refused anywhere in run_sql (checked outside quotes and comments).
WRITE_WORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|CREATE|ALTER|CACHE|UNCACHE|REFRESH|TRUNCATE|SET|ADD|LOAD|GRANT|REVOKE"
    r"|REGISTER|INTO|MSCK|ANALYZE|EXEC|EXECUTE|CALL)\b|\b(REFLECT|JAVA_METHOD)\s*\(", re.IGNORECASE)
# DDL an agent / the self-healer may run (setup=False): cache a table, or add a REST table for an allowed host.
AGENT_DDL = re.compile(r"^\s*(CACHE\s+TABLE|CREATE\s+LIGHTNING\s+REST\s+TABLE)\b", re.IGNORECASE)
# Extra DDL only setup scripts may run (setup=True; guard rule: never in app/agents).
SETUP_DDL = re.compile(
    r"^\s*(CREATE\s+(OR\s+REPLACE\s+)?SCHEMASTORE\s+VIEW|CREATE\s+SCHEMASTORE\s+CONTAINER"
    r"|DROP\s+SCHEMASTORE\s+VIEW|DROP\s+LIGHTNING\s+DATABASE\s+TABLE|CREATE\s+LIGHTNING\s+DATABASE"
    r"|REGISTER\s+DATASOURCE\s+TABLES|CREATE\s+DATASOURCE)\b", re.IGNORECASE)
REST_HOSTS = {"api.data.gov.my", "api.open-meteo.com", "flood-api.open-meteo.com"}  # REST tables may call only these
NUMBER = re.compile(r"^-?(0|[1-9]\d*)(\.\d+)?([eE][-+]?\d+)?$")  # no leading zeros: "0740121" stays text


class ZetarisError(Exception):
    """A Zetaris call failed. `kind` tells the caller what to do:
    auth | sql | source_unavailable | network | bad_response | no_fixture | not_allowed."""

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


def _scan(sql):
    """Walk SQL once, respecting '...' / "..." / `...` quotes (with doubled-quote and backslash escapes).
    Returns (clean, skeleton): clean = comments removed and whitespace collapsed OUTSIDE quotes (quoted text is
    kept exactly); skeleton = clean with every quoted part emptied - used for keyword and ';' checks."""
    clean, skel, i, n = [], [], 0, len(sql)
    pending_space = False

    def emit(text, skel_text):
        nonlocal pending_space
        if pending_space and clean:
            clean.append(" ")
            skel.append(" ")
        pending_space = False
        clean.append(text)
        skel.append(skel_text)

    while i < n:
        c = sql[i]
        if c.isspace():
            pending_space = True
            i += 1
        elif sql.startswith("--", i):          # line comment: drop to end of line
            while i < n and sql[i] != "\n":
                i += 1
            pending_space = True
        elif sql.startswith("/*", i):          # block comment
            end = sql.find("*/", i + 2)
            if end < 0:
                raise ZetarisError("not_allowed", "unterminated /* comment in SQL")
            i = end + 2
            pending_space = True
        elif c in "'\"`":
            j = i + 1
            while True:
                if j >= n:
                    raise ZetarisError("not_allowed", "unterminated quoted text in SQL")
                if sql[j] == "\\" and c != "`":
                    j += 2
                    continue
                if sql[j] == c:
                    if j + 1 < n and sql[j + 1] == c:   # doubled quote = escaped quote
                        j += 2
                        continue
                    break
                j += 1
            emit(sql[i:j + 1], c + c)
            i = j + 1
        else:
            emit(c, c)
            i += 1
    return "".join(clean), "".join(skel)


def normalize_sql(sql):
    """One statement: comments removed, whitespace collapsed outside quotes, trailing ; removed.
    Raises ZetarisError(not_allowed)."""
    text, skeleton = _scan(sql or "")
    text, skeleton = text.strip(), skeleton.strip()
    while skeleton.endswith(";"):
        text, skeleton = text[:-1].rstrip(), skeleton[:-1].rstrip()
    if not text:
        raise ZetarisError("not_allowed", "empty SQL")
    if ";" in skeleton:
        raise ZetarisError("not_allowed", "only one SQL statement per call")
    return text


def read_only_problem(sql):
    """None if `sql` is a pure read; otherwise a short reason. Checked outside quotes and comments."""
    _, skeleton = _scan(normalize_sql(sql))
    if not READ_ONLY.match(skeleton):
        return "not SELECT/WITH"
    m = WRITE_WORDS.search(skeleton)
    return f"contains {m.group(0).strip('( ').upper()}" if m else None


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
        if not any(c in v for c in ".eE"):
            return int(v)
        f = float(v)
        return f if math.isfinite(f) else value   # '1e400' is not a usable number - keep the text
    return value


def _config():
    url = os.getenv("ZETARIS_API_URL", "").strip().rstrip("/")
    key = os.getenv("ZETARIS_API_KEY", "").strip()
    if not url or not key:
        raise ZetarisError("auth", "ZETARIS_API_URL / ZETARIS_API_KEY not set")
    return url, key, os.getenv("ZETARIS_ORG_ID", "1").strip() or "1"


def _post(sql, limit, timeout=TIMEOUT_S):
    url, key, org = _config()
    headers = {"Authorization": f"Bearer {key}", "X-Org-ID": org, "X-Request-ID": str(uuid.uuid4()),
               "Content-Type": "application/json"}
    body = {"queryId": str(uuid.uuid4()), "sql": sql, "source": "SqlEditor", "limit": limit}
    return requests.post(f"{url}/sql-editor/sqls/run", headers=headers, json=body, timeout=timeout)


def _classify(status, message):
    if status == 401:
        return "auth", "Zetaris refused the API key (401) - check ZETARIS_API_KEY"
    if "REST API call failed" in message or "Server returned HTTP response code" in message:
        return "source_unavailable", message   # e.g. data.gov.my 429 behind a REST table
    if status >= 500:
        return "network", message
    return "sql", message


def _live(sql, limit, agent, label, tolerate=None, budget_s=None):
    """POST with retry on network/5xx/garbage bodies. Returns (payload, attempts).
    If `tolerate` is in Zetaris's error message, returns ({"tolerated": message}, attempts) instead of failing.
    budget_s caps the total time of all attempts (the caller's remaining run time)."""
    attempt = 0
    deadline = time.monotonic() + budget_s if budget_s else None
    while True:
        attempt += 1
        t0 = time.perf_counter()
        left = deadline - time.monotonic() if deadline else TIMEOUT_S
        try:
            if left <= 1:
                raise requests.Timeout("run time budget used up")
            r = _post(sql, limit, timeout=min(TIMEOUT_S, left))
            try:
                payload = r.json()
            except ValueError:
                payload = None
            if r.ok and isinstance(payload, dict):
                return payload, attempt
            if r.ok:                                   # 200 with a list/text body: retryable garbage
                kind, message = "network", "Zetaris returned a body that is not a JSON object"
            else:
                msg = payload.get("msg", r.text) if isinstance(payload, dict) else r.text
                kind, message = _classify(r.status_code, str(msg or "")[:400])
                if tolerate and tolerate in message:
                    return {"tolerated": message}, attempt
        except (requests.ConnectionError, requests.Timeout) as e:
            kind, message = "network", f"cannot reach Zetaris ({type(e).__name__}: {e})"[:200]
        ms = int((time.perf_counter() - t0) * 1000)
        wait = BACKOFF_S[min(attempt, len(BACKOFF_S)) - 1]
        out_of_time = deadline is not None and time.monotonic() + wait >= deadline
        if kind != "network" or attempt > len(BACKOFF_S) or out_of_time:
            trace.step(agent, "zetaris.run_sql", input_summary=label, output_summary=message, status="failed",
                       source="zetaris-live", retry_count=attempt - 1, duration_ms=ms,
                       decision=f"Zetaris error ({kind}) - caller must fall back", details={"kind": kind})
            raise ZetarisError(kind, message)
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


def run_sql(sql, agent, purpose=None, limit=1000, budget_s=None):
    """Run one read-only SQL statement through Zetaris (or replay it in SAMPLE_MODE). Returns SqlResult.
    budget_s: optional cap on total seconds (pass the run's remaining time)."""
    text = normalize_sql(sql)
    qh = query_hash(text)
    label = purpose or text
    problem = read_only_problem(text)
    if problem:
        trace.step(agent, "zetaris.run_sql", input_summary=label, output_summary=f"refused: {problem}",
                   status="failed", source="zetaris", decision="run_sql is read-only; writes and DDL are refused")
        raise ZetarisError("not_allowed", f"run_sql is read-only ({problem}); use run_ddl for allowed DDL")

    t0 = time.perf_counter()
    attempts = 1
    if config.sample_mode():
        doc = _load_fixture(qh)
        if doc is None:
            trace.step(agent, "zetaris.run_sql", input_summary=label, output_summary=f"no fixture {qh}.json",
                       status="failed", source="zetaris-replay", decision="SAMPLE_MODE has no recording of this query",
                       details={"query_hash": qh, "sql": text})
            raise ZetarisError("no_fixture", f"SAMPLE_MODE: no recorded result for this query ({qh})")
        columns, raw_rows, fetched_at, source = doc["columns"], doc["rows"], doc["recorded_at"], "zetaris-replay"
    else:
        payload, attempts = _live(text, limit, agent, label, budget_s=budget_s)
        columns, raw_rows = payload.get("headers") or [], payload.get("data") or []
        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        source = "zetaris-live"

    if not isinstance(raw_rows, list) or any(not isinstance(r, list) or len(r) != len(columns) for r in raw_rows):
        trace.step(agent, "zetaris.run_sql", input_summary=label, output_summary="rows do not match the column list",
                   status="failed", source=source, decision="Malformed result - not used",
                   details={"query_hash": qh, "columns": len(columns)})
        raise ZetarisError("bad_response", "Zetaris rows do not match the column list")
    if source == "zetaris-live" and config.flag("ZETARIS_RECORD"):
        _save_fixture(qh, text, columns, raw_rows, fetched_at)

    rows = [[coerce(v) for v in row] for row in raw_rows]
    records = [dict(zip(columns, row)) for row in rows]
    ms = int((time.perf_counter() - t0) * 1000)
    recorded = source == "zetaris-live" and config.flag("ZETARIS_RECORD")
    trace.step(agent, "zetaris.run_sql", input_summary=label,
               output_summary=f"{len(rows)} rows x {len(columns)} columns ({', '.join(map(str, columns[:6]))})",
               source=source, retry_count=attempts - 1, duration_ms=ms,
               decision=("Recorded fixture for SAMPLE_MODE" if recorded else None),
               details={"query_hash": qh, "sql": text, "rows": len(rows), "fetched_at": fetched_at})
    return SqlResult(sql=text, query_hash=qh, columns=columns, rows=rows, source=source, duration_ms=ms,
                     fetched_at=fetched_at, records=records)


def ddl_problem(sql, setup=False):
    """None if this DDL may run; otherwise a short reason.
    Agents (setup=False): only CACHE TABLE, or CREATE LIGHTNING REST TABLE whose endpoints are https on REST_HOSTS.
    Setup scripts (setup=True) may also create/replace views, drop tables, register/create datasources."""
    text = normalize_sql(sql)
    if setup and SETUP_DDL.match(text):
        return None
    if not AGENT_DDL.match(text):
        return "not on the DDL allow-list" + ("" if setup else " for agents")
    if re.match(r"^\s*CREATE\s+LIGHTNING\s+REST\s+TABLE", text, re.IGNORECASE):
        endpoints = re.findall(r"""\b(?:endpoint|url)\s+["']([^"']+)["']""", text, re.IGNORECASE)
        if not endpoints:
            return "REST table without an endpoint"
        for url in endpoints:
            u = urlparse(url)
            if u.scheme != "https" or (u.hostname or "").lower() not in REST_HOSTS:
                return f"endpoint host not allowed: {u.hostname or url[:40]}"
    return None


def run_ddl(sql, agent, purpose=None, setup=False, budget_s=None):
    """Run one allow-listed DDL statement (setup / self-healing). 'Already exists' counts as success.
    Returns True if Zetaris applied it, False if it already existed. Never runs in SAMPLE_MODE.
    setup=True unlocks SETUP_DDL - for scripts/ only (guard rule: never in app/agents)."""
    text = normalize_sql(sql)
    label = purpose or text
    problem = ddl_problem(text, setup=setup)
    if problem:
        trace.step(agent, "zetaris.run_ddl", input_summary=label, output_summary=f"refused: {problem}",
                   status="failed", source="zetaris", decision="Only allow-listed DDL may run")
        raise ZetarisError("not_allowed", f"DDL refused: {problem}")
    if config.sample_mode():
        raise ZetarisError("not_allowed", "SAMPLE_MODE: DDL is not replayed")
    t0 = time.perf_counter()
    payload, _ = _live(text, 1, agent, label, tolerate="already exists", budget_s=budget_s)
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
        print(f"FAILED ({e.kind}): {trace.redact(str(e))}")
        return 1
    print(r.columns)
    for row in r.rows[:20]:
        print(row)
    print(f"source={r.source} rows={r.row_count} hash={r.query_hash}")
    print("trace:", trace.end_run())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
