"""Trace logger: one JSONL line per agent step / Zetaris call / Nightshift call in logs/trace-<run_id>.jsonl.

Usage:
    from app import trace
    trace.start_run("Is Pasir Mas at risk?")
    trace.step("Critic", "review_draft", input_summary="...", output_summary="...",
               status="needs_revision", target_agent="Coordinator", decision="Stale source -> revise")
    trace.end_run("success")

Read a saved trace as sentences:  python -m app.trace logs/trace-<run_id>.jsonl
"""
import contextvars
import json
import sys
import threading
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from app import config

ROOT = config.ROOT
STATUSES = {"success", "failed", "retrying", "fallback", "needs_revision", "approved", "injected_fault"}
MAX_SUMMARY = 300

class Run:
    """One VEDA run: its id, trace file, step counter and write lock."""

    def __init__(self, run_id, path, quiet=False, listener=None):
        self.run_id = run_id
        self.path = path
        self.quiet = quiet
        self.listener = listener        # called with every record as it is written (live progress: CLI, web page)
        self.step = 0
        self.lock = threading.Lock()
        self.fallbacks = []             # B-86: every AI fallback in this run ("<agent>: <what>"), repeated at run_end
        self.ai_calls = 0               # B-93: Nightshift requests in this run (each attempt), repeated at run_end


_current: ContextVar = ContextVar("veda_trace_run", default=None)


def _mask(match):
    """Replace only the `secret` group of a pattern match with ***."""
    start, end = match.span("secret")
    return match.group(0)[: start - match.start()] + "***" + match.group(0)[end - match.start():]


def redact(text):
    """Mask secret-looking strings (config.SECRET_PATTERNS), VEDA's secret env values, and personal data
    (phone / IC numbers, config.PERSONAL_PATTERNS)."""
    text = str(text)
    for _key, value in config.secret_env_values(min_len=6):
        text = text.replace(value, "***")
    for pat in config.SECRET_PATTERNS.values():
        text = pat.sub(_mask, text)
    for label, pat in config.PERSONAL_PATTERNS.items():
        text = pat.sub(label, text)
    return text


def summarize(value, limit=MAX_SUMMARY):
    """Redacted one-line summary, capped at `limit` characters."""
    if value is None:
        return None
    text = redact(" ".join(str(value).split()))
    return text if len(text) <= limit else text[: limit - 3] + "..."


PROMPT_CAP = 20000      # details["prompt"]: the exact prompt sent to the AI is kept whole (shown on /admin)


def _clean(obj, cap=500):
    """Redact every string inside a details dict/list (the 'prompt' key keeps up to PROMPT_CAP characters)."""
    if isinstance(obj, dict):
        return {k: _clean(v, PROMPT_CAP if k == "prompt" else cap) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v, cap) for v in obj]
    if isinstance(obj, str):
        if cap == PROMPT_CAP:                       # keep the prompt's own lines; redacted, capped
            text = redact(obj)
            return text if len(text) <= cap else text[: cap - 3] + "..."
        return summarize(obj, cap)
    return obj


def _write(run, record):
    try:
        with run.lock, run.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:  # logging must never crash a run
        print(f"[trace] WARNING: could not write {run.path}: {e}", file=sys.stderr)


def sentence(rec):
    """One readable line for a trace record (used for stdout and the viewer)."""
    try:  # JSON keeps UTC; sentences always show Malaysia time, whatever the machine's zone
        ts = datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00")).astimezone(config.MYT).strftime("%H:%M:%S")
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


def start_run(question=None, log_dir=None, quiet=False, listener=None):
    """Start a run: create logs/trace-<run_id>.jsonl, write a run_start line, make it the current run.
    listener(record) is called for every step as it happens (B-17: live progress); its errors never stop a run."""
    run_id = f"{datetime.now(config.MYT):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"  # MYT
    folder = Path(log_dir) if log_dir else ROOT / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    run = Run(run_id, folder / f"trace-{run_id}.jsonl", quiet, listener)
    _current.set(run)
    step("System", "run_start", input_summary=question,
         output_summary=f"Run {run_id} started ({'SAMPLE_MODE' if config.sample_mode() else 'live'})",
         details={"sample_mode": config.sample_mode()})
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
        if action == "nightshift.chat":
            run.ai_calls += 1
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
        "mode": "sample" if config.sample_mode() else "live",
        "duration_ms": duration_ms,
        "details": _clean(details or {}),
    }
    _write(run, record)
    if not run.quiet:
        print(sentence(record), flush=True)
    if run.listener:
        try:
            run.listener(record)
        except Exception as e:  # a broken progress display must never stop the run
            print(f"WARNING: progress listener failed: {type(e).__name__}", file=sys.stderr)
    return record


def notify(agent, action, **details):
    """Tell the live view something is starting (e.g. 'ai.waiting' when a Nemotron call goes out) without writing a
    trace line - the call's own line follows when it ends. Marked transient; never stops a run."""
    run = _current.get()
    if run is None or not run.listener:
        return
    try:
        run.listener({"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                      "run_id": run.run_id, "agent_name": agent, "action": action, "transient": True,
                      "status": "running", "details": _clean(details)})
    except Exception as e:  # noqa: BLE001 - a broken display must never stop the run
        print(f"WARNING: progress listener failed: {type(e).__name__}", file=sys.stderr)


def ai_fallback(agent, what, reason):
    """B-86 (organiser answer, 23 Oct): mark plainly where an AI step fell back - one `ai.fallback` line
    ("fallback: <what> (<reason>)"), next to the served-model line that every successful AI call writes. The run
    keeps the list and repeats it on run_end."""
    run = _current.get()
    if run is not None:
        with run.lock:
            run.fallbacks.append(f"{agent}: {what}")
    return step(agent, "ai.fallback", output_summary=f"fallback: {what} ({summarize(reason, 160)})",
                status="fallback", decision="AI step not used for this answer - the code-checked card still goes out",
                details={"what": what, "reason": summarize(reason, 300)})


def end_run(status="success", output_summary=None, details=None):
    """Write the run_end line and clear the current run. Returns the trace file path. details are added to the
    line (the loop adds the final verdict and, when it changed, the first one)."""
    run = _current.get()
    if run is None:
        raise RuntimeError("trace.end_run() called without an active run")
    if status not in STATUSES:
        status = "failed"  # never leave a run open because of a bad status
    try:
        step("System", "run_end", output_summary=output_summary or f"Run finished after {run.step} steps",
             status=status, decision=("AI fallback used: " + "; ".join(run.fallbacks)) if run.fallbacks
             else "no AI fallback in this run", details={"ai_fallbacks": list(run.fallbacks), "ai_calls": run.ai_calls,
                                                        **({"ai": "no AI calls"} if not run.ai_calls else {}),
                                                        **(details or {})})
    finally:
        _current.set(None)
    return run.path


def bind(fn):
    """Wrap fn so it runs inside the current trace run - use when handing work to a plain thread/executor:
    executor.submit(trace.bind(work), ...) or executor.map(trace.bind(work), items). Each call runs in its own copy
    of the context, so several threads can use one bound function at the same time. (FastAPI's threadpool already
    copies the context.)"""
    ctx = contextvars.copy_context()
    return lambda *a, **k: ctx.copy().run(fn, *a, **k)


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
