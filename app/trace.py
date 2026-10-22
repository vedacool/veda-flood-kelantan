"""Trace logger: one JSONL line per agent step / Zetaris call / Nightshift call in logs/trace-<run_id>.jsonl.

Usage:
    from app import trace
    trace.start_run("Is Pasir Mas at risk?")
    trace.step("Critic", "review_draft", input_summary="...", output_summary="...",
               status="needs_revision", target_agent="Coordinator", decision="Stale source -> revise")
    trace.end_run("success")

Read a saved trace as sentences:  python -m app.trace logs/trace-<run_id>.jsonl
"""
import json
import os
import re
import sys
import threading
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUSES = {"success", "failed", "retrying", "fallback", "needs_revision", "approved", "injected_fault"}
MAX_SUMMARY = 300

SECRET_PATTERNS = [
    re.compile(r"nvapi-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/\-]{8,}=*"),
    re.compile(r"""(?i)((?:password|passwd|secret|token|api_key)["']?(?:\s*[=:]\s*|\s+(?=["']))["']?)[^"'\s,;]{4,}"""),
]
SECRET_ENV_KEY = re.compile(r"(?i)(TOKEN|KEY|PASSWORD|SECRET)")


class Run:
    """One VEDA run: its id, trace file, step counter and write lock."""

    def __init__(self, run_id, path, quiet=False):
        self.run_id = run_id
        self.path = path
        self.quiet = quiet
        self.step = 0
        self.lock = threading.Lock()


_current: ContextVar = ContextVar("veda_trace_run", default=None)


def redact(text):
    """Mask secret-looking strings and any secret value present in the environment."""
    text = str(text)
    for key, value in os.environ.items():
        if SECRET_ENV_KEY.search(key) and len(value) >= 8:
            text = text.replace(value, "***")
    for pat in SECRET_PATTERNS:
        text = pat.sub(lambda m: (m.group(1) if m.groups() else "") + "***", text)
    return text


def summarize(value, limit=MAX_SUMMARY):
    """Redacted one-line summary, capped at `limit` characters."""
    if value is None:
        return None
    text = redact(" ".join(str(value).split()))
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _clean(obj):
    """Redact every string inside a details dict/list."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, str):
        return summarize(obj, 500)
    return obj


def _sample_mode():
    return os.getenv("SAMPLE_MODE", "false").strip().lower() == "true"


def _write(run, record):
    try:
        with run.lock, run.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:  # logging must never crash a run
        print(f"[trace] WARNING: could not write {run.path}: {e}", file=sys.stderr)


def sentence(rec):
    """One readable line for a trace record (used for stdout and the viewer)."""
    try:  # JSON keeps UTC; sentences show local time (MYT on our machines)
        ts = datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")
    except (KeyError, ValueError):
        ts = "??:??:??"
    who = rec.get("agent_name", "?") + (f" -> {rec['target_agent']}" if rec.get("target_agent") else "")
    why = rec.get("decision") or rec.get("output_summary") or ""
    extra = []
    if rec.get("confidence") is not None:
        extra.append(f"conf {rec['confidence']}")
    if rec.get("retry_count"):
        extra.append(f"retry {rec['retry_count']}")
    if rec.get("duration_ms") is not None:
        extra.append(f"{rec['duration_ms']} ms")
    tail = f" ({', '.join(extra)})" if extra else ""
    return f"{ts} #{rec.get('step')} {who} | {rec.get('action')} | {rec.get('status')} | {why}{tail}"


def current_run():
    """The active Run, or None."""
    return _current.get()


def start_run(question=None, log_dir=None, quiet=False):
    """Start a run: create logs/trace-<run_id>.jsonl, write a run_start line, make it the current run."""
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
    folder = Path(log_dir) if log_dir else ROOT / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    run = Run(run_id, folder / f"trace-{run_id}.jsonl", quiet)
    _current.set(run)
    step("System", "run_start", input_summary=question,
         output_summary=f"Run {run_id} started ({'SAMPLE_MODE' if _sample_mode() else 'live'})",
         details={"sample_mode": _sample_mode()})
    return run


def step(agent, action, input_summary=None, output_summary=None, status="success", target_agent=None,
         confidence=None, retry_count=0, source=None, decision=None, duration_ms=None, details=None):
    """Write one trace line for the current run and print it as a sentence. Returns the record."""
    run = _current.get()
    if run is None:
        raise RuntimeError("trace.step() called before trace.start_run() - this step would be lost")
    if status not in STATUSES:
        raise ValueError(f"unknown trace status {status!r}; allowed: {sorted(STATUSES)}")
    with run.lock:
        run.step += 1
        n = run.step
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "trace_id": run.run_id,
        "run_id": run.run_id,
        "step": n,
        "agent_name": agent,
        "action": action,
        "input_summary": summarize(input_summary),
        "output_summary": summarize(output_summary),
        "decision": summarize(decision),
        "target_agent": target_agent,
        "confidence": confidence,
        "retry_count": retry_count,
        "status": status,
        "source": source,
        "mode": "sample" if _sample_mode() else "live",
        "duration_ms": duration_ms,
        "details": _clean(details or {}),
    }
    _write(run, record)
    if not run.quiet:
        print(sentence(record), flush=True)
    return record


def end_run(status="success", output_summary=None):
    """Write the run_end line and clear the current run. Returns the trace file path."""
    run = _current.get()
    if run is None:
        raise RuntimeError("trace.end_run() called without an active run")
    step("System", "run_end", output_summary=output_summary or f"Run finished after {run.step} steps", status=status)
    _current.set(None)
    return run.path


def main(argv):
    """CLI viewer: print a saved trace file as readable sentences."""
    if len(argv) != 2:
        print("usage: python -m app.trace logs/trace-<run_id>.jsonl")
        return 2
    for line in Path(argv[1]).read_text(encoding="utf-8").splitlines():
        if line.strip():
            print(sentence(json.loads(line)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
