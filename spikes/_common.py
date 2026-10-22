"""Shared helpers for the B-64 day-1 spike tests.

Throwaway exploration code, NOT part of VEDA. The real modules
(trace logger, Nightshift adapter, run_sql) are built in B-02/B-03/B-04.

Rules kept even here:
- secrets come only from .env and are never printed or logged
- every Zetaris / Nightshift / HTTP call writes one JSONL line to logs/spike-<ts>.jsonl
"""
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ZETARIS_URL = os.getenv("ZETARIS_API_URL", "http://localhost:8888/api/v1.0").rstrip("/")
ZETARIS_ORG = os.getenv("ZETARIS_ORG_ID", "1")
NIGHTSHIFT_URL = os.getenv("METERLESS_BASE_URL", "http://127.0.0.1:8088/v1").rstrip("/")

LOG_PATH = ROOT / "logs" / f"spike-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"


def short(text, n=160):
    """One-line, length-capped summary for logs (never full prompts/answers). Redacts passwords in SQL."""
    text = " ".join(str(text).split())
    text = re.sub(r'(password\s+)"[^"]*"', r'\1"***"', text, flags=re.IGNORECASE)
    return text if len(text) <= n else text[: n - 3] + "..."


def log(spike, action, **fields):
    line = {"ts": datetime.now(timezone.utc).isoformat(), "spike": spike, "action": action, **fields}
    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return line


def run_sql(sql, spike, limit=1000, timeout=300):
    """POST one SQL statement to Zetaris. Returns (ok, rows_or_error, seconds)."""
    sql = sql.strip().rstrip(";")
    headers = {
        "Authorization": f"Bearer {os.environ['ZETARIS_API_KEY']}",
        "X-Org-ID": ZETARIS_ORG,
        "X-Request-ID": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    body = {"queryId": str(uuid.uuid4()), "sql": sql, "source": "SqlEditor", "limit": limit}
    t0 = time.perf_counter()
    try:
        r = requests.post(f"{ZETARIS_URL}/sql-editor/sqls/run", headers=headers, json=body, timeout=timeout)
        secs = round(time.perf_counter() - t0, 2)
        if r.ok:
            data = r.json().get("data", [])
            log(spike, "zetaris.run_sql", sql=short(sql, 300), ok=True, http=r.status_code, rows=len(data), secs=secs)
            return True, data, secs
        log(spike, "zetaris.run_sql", sql=short(sql, 300), ok=False, http=r.status_code, error=short(r.text, 400), secs=secs)
        return False, r.text, secs
    except requests.RequestException as e:
        secs = round(time.perf_counter() - t0, 2)
        log(spike, "zetaris.run_sql", sql=short(sql, 300), ok=False, error=short(e, 400), secs=secs)
        return False, str(e), secs


def nightshift(method, path, spike, json_body=None, timeout=180):
    """Call Nightshift. Logs only status, latency and a short summary — never token or headers."""
    headers = {
        "Authorization": f"Bearer {os.environ['METERLESS_RUNTIME_TOKEN']}",
        "meterless-app": "veda",
        "meterless-scope": "user",
    }
    t0 = time.perf_counter()
    try:
        r = requests.request(method, f"{NIGHTSHIFT_URL}{path}", headers=headers, json=json_body, timeout=timeout)
    except requests.RequestException as e:
        secs = round(time.perf_counter() - t0, 2)
        log(spike, f"nightshift.{method} {path}", ok=False, error=short(e), secs=secs)
        return False, str(e), secs
    secs = round(time.perf_counter() - t0, 2)
    try:
        payload = r.json()
    except ValueError:
        payload = r.text
    return r.ok, payload, secs
