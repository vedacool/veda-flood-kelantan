"""VEDA's web entry point (B-19): a small API + one web page that shows each step live.

    python -m app.main                     # http://127.0.0.1:8000  (VEDA_HOST / VEDA_PORT to change)
    curl -X POST localhost:8000/run -H "Content-Type: application/json" -d '{"question": "Tumpat ok?"}'

GET  /health      status + whether Zetaris and Nightshift answer (skipped in SAMPLE_MODE)
POST /run         {"question", "replay"?, "at"?} -> the answer as JSON (official fields: run_id, status, output, agents,
                  trace_id, log_file, execution_time ...)
GET  /run/stream  same input as query parameters -> Server-Sent Events: one "step" event per trace step as it
                  happens (the B-17 listener), then one "result" event
GET  /ui/words    fixed wording for screens that call no engine (headlines, emergency steps, disclaimer)
GET  /            the web page (app/web/index.html): home, waiting, answer, share, emergency
Bad input -> HTTP 400 {"error": {"code", "message"}}; a second run while one is running -> 429 (one writer for the
World Model on disk). Nothing secret is ever returned: every text goes through the trace's redaction.
"""
import json
import logging
import os
import queue
import threading
from datetime import datetime

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app import card as card_mod
from app import config, progress, trace, view
from app.adapters import nightshift, zetaris
from app.agents.coordinator import SAFETY

load_dotenv(config.ROOT / ".env")
MAX_QUESTION = 500
WEB_PAGE = config.ROOT / "app" / "web" / "index.html"
_busy = threading.Lock()                 # one run at a time: the World Model on disk has one writer
app = FastAPI(title="VEDA", description="Flood-risk answers for Kelantan - multi-agent, every step traced.")


class _NoQueryString(logging.Filter):
    """The access log keeps method, path and status but drops the query string: GET /run/stream carries the user's
    question there (audit 23 Oct - it reached stdout / Docker logs unmasked)."""

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args = list(record.args)
            args[2] = str(args[2]).split("?", 1)[0]
            record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(_NoQueryString())


class BadInput(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _error(status, code, message):
    return JSONResponse({"error": {"code": code, "message": trace.redact(message)}}, status_code=status)


def parse_input(question, replay=None, at=None):
    """Validate a request -> (question, replay, at datetime or None). Raises BadInput."""
    if not isinstance(question, str) or not question.strip():
        raise BadInput("empty_question", "Ask a question about a place in Kelantan.")
    if len(question) > MAX_QUESTION:
        raise BadInput("question_too_long", f"Keep the question under {MAX_QUESTION} characters.")
    if replay in (None, ""):
        if at:
            raise BadInput("at_without_replay", "'at' is only used with 'replay'.")
        return question.strip(), None, None
    if replay not in config.REPLAYS:
        raise BadInput("unknown_replay", f"Known replays: {', '.join(sorted(config.REPLAYS))}.")
    sc = config.REPLAYS[replay]
    try:
        when = datetime.strptime(at or sc["default_at"], "%Y-%m-%d %H:%M").replace(tzinfo=config.MYT)
    except (TypeError, ValueError):
        raise BadInput("bad_time", "'at' must look like 2024-11-26 18:00 (Malaysia time).") from None
    lo, hi = (datetime.strptime(t, "%Y-%m-%d %H:%M").replace(tzinfo=config.MYT) for t in sc["window"])
    if not lo <= when <= hi:
        raise BadInput("outside_replay", f"This replay covers {sc['window'][0]} to {sc['window'][1]} (MYT).")
    return question.strip(), replay, when


def _log_path(path):
    """The trace file relative to the repo when it is inside it (logs/trace-....jsonl), else as is."""
    try:
        return os.path.relpath(path, config.ROOT).replace(os.sep, "/")
    except ValueError:                      # another drive (Windows)
        return str(path)


def result_json(r):
    """loop.run() result -> the API's answer (official fields + VEDA's card in both languages)."""
    a = r["answer"]
    agents = []
    try:
        for line in open(r["trace"], encoding="utf-8"):
            name = json.loads(line).get("agent_name")
            if name and name != "System" and name not in agents:
                agents.append(name)
    except OSError:
        pass
    fc = r.get("forecast") or {}
    out = {"run_id": r["run_id"], "trace_id": r["run_id"], "status": r["status"],
           "output": trace.redact(a["text"] + "\n" + a.get("safety_line", "")), "language": a.get("language"),
           "verdict": fc.get("verdict"), "confidence": (fc.get("confidence") or {}).get("label"),
           "drafted_by": a.get("drafted_by"), "approved_by_critic": bool(a.get("approved")),
           "safety_fixes": a.get("safety", []), "agents": agents,
           "log_file": _log_path(r["trace"]),
           "execution_time": (r.get("timing") or {}).get("total"), "timing": r.get("timing"),
           "card": None, "disclaimer": dict(SAFETY), "view": view.answer_view(r)}
    if r.get("card"):
        out["card"] = {lang: trace.redact(card_mod.render(r["card"], lang)) for lang in ("en", "ms")}
    return out


def _run(question, replay, at, on_step=None):
    """One run. The full trace goes to logs/trace-<run_id>.jsonl; stdout (docker logs) gets the same short progress
    lines as the page, one per important step, prefixed with the run id - never the question text (privacy)."""
    from app import loop, progress

    def step(rec):
        line = progress.describe(rec)
        if line:
            print(f"[{rec.get('run_id')}] {line}", flush=True)
        if on_step:
            on_step(rec)
    return loop.run(question, quiet=True, replay=replay, at=at, on_step=step, default_scene=True)


@app.get("/health")
def health():
    """Is VEDA ready? In SAMPLE_MODE everything is offline replay, so nothing is called."""
    if config.sample_mode():
        return {"status": "ok", "sample_mode": True, "zetaris": "replay (offline)", "nightshift": "not used"}
    status = {"status": "ok", "sample_mode": False, "busy": _busy.locked()}
    try:
        status["zetaris"] = "ok" if zetaris._post("SELECT 1 AS x", 1, timeout=10).ok else "error"
    except (zetaris.ZetarisError, requests.RequestException) as e:
        status["zetaris"] = f"unreachable ({type(e).__name__})"
    try:
        base = os.getenv("METERLESS_BASE_URL", "http://127.0.0.1:8088/v1").rstrip("/").rsplit("/v1", 1)[0]
        status["nightshift"] = "ok" if requests.get(f"{base}/healthz", timeout=5).ok else "error"
    except requests.RequestException as e:
        status["nightshift"] = f"unreachable ({type(e).__name__})"
    if status["zetaris"] != "ok" or status["nightshift"] != "ok":
        status["status"] = "degraded"
    return status


@app.post("/run")
async def run(request: Request):
    """One question -> the answer JSON. 400 on bad input, 429 while another run is going."""
    try:
        body = await request.json()
    except ValueError:
        return _error(400, "bad_json", "Send JSON like {\"question\": \"Is Tumpat safe?\"}.")
    if not isinstance(body, dict):
        return _error(400, "bad_json", "Send a JSON object.")
    try:
        question, replay, at = parse_input(body.get("question"), body.get("replay"), body.get("at"))
    except BadInput as e:
        return _error(400, e.code, str(e))
    if not _busy.acquire(blocking=False):
        return _error(429, "busy", "VEDA is answering another question - try again in a minute.")
    try:
        r = await run_in_threadpool(_run, question, replay, at)
    except nightshift.NightshiftError as e:            # should not happen (agents fall back), but never a 500 page
        return _error(503, "model_unavailable", str(e))
    except zetaris.ZetarisError as e:                  # the loop answers "cannot check now"; this is the backstop
        return _error(503, "data_unavailable", str(e))
    finally:
        _busy.release()
    return result_json(r)


@app.get("/run/stream")
def run_stream(question: str = "", replay: str = "", at: str = ""):
    """The same run, streamed: a 'step' event per trace step as it happens, then a 'result' event."""
    try:
        question, replay, when = parse_input(question, replay or None, at or None)
    except BadInput as e:
        return _error(400, e.code, str(e))
    if not _busy.acquire(blocking=False):
        return _error(429, "busy", "VEDA is answering another question - try again in a minute.")
    events = queue.Queue()

    def on_step(rec):
        active = (rec.get("details") or {}).get("active") if rec.get("action") == "data.met_warnings" else None
        if active:                                   # the waiting screen shows it in place of a tip
            events.put(("warning", {"headings": [trace.redact(w.get("heading") or "") for w in active][:2]}))
        line = progress.describe(rec)
        if line:
            events.put(("step", {"line": trace.redact(line), "agent": rec.get("agent_name"),
                                 "action": rec.get("action"), "status": rec.get("status")}))

    def work():
        try:
            events.put(("result", result_json(_run(question, replay, when, on_step))))
        except Exception as e:                       # report, never hang the page
            events.put(("error", {"code": "run_failed", "message": trace.redact(f"{type(e).__name__}: {e}")}))
        finally:
            _busy.release()
            events.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        while (item := events.get()) is not None:
            kind, data = item
            yield f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/ui/words")
def ui_words():
    """Fixed wording only - no engine call (the emergency screen must work whatever else is down)."""
    return view.words()


@app.get("/", response_class=HTMLResponse)
def page():
    return WEB_PAGE.read_text(encoding="utf-8")


def main():
    import uvicorn
    uvicorn.run(app, host=os.getenv("VEDA_HOST", "127.0.0.1"), port=int(os.getenv("VEDA_PORT", "8000")))


if __name__ == "__main__":
    main()
