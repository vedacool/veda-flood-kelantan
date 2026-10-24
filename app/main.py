"""VEDA's web entry point (B-19): a small API + one web page that shows each step live.

    python -m app.main                     # http://127.0.0.1:8000  (VEDA_HOST / VEDA_PORT to change)
    curl -X POST localhost:8000/run -H "Content-Type: application/json" -d '{"question": "Tumpat ok?"}'

GET  /health      status + whether Zetaris and Nightshift answer (skipped in SAMPLE_MODE)
POST /run         {"question", "replay"?, "at"?} -> the answer as JSON (official fields: run_id, status, output, agents,
                  trace_id, log_file, execution_time ...)
GET  /run/stream  same input as query parameters -> Server-Sent Events: one "step" event per trace step as it
                  happens (the B-17 listener), then one "result" event
GET  /live        the live log (app/web/live.html): every trace step of the running run as it happens, or a
                  recorded run replayed at 1x / 4x
GET  /live/stream Server-Sent Events: every trace record of whatever run is going (the question is never shown)
GET  /trace/recorded            the recorded live runs in data/sample/live_traces (JPS readings redacted)
GET  /trace/recorded/{name}     one of them, record by record
GET  /trace/run/{run_id}        a run from logs/ - this computer only (127.0.0.1), question not shown
GET  /admin       operator screens (app/web/admin.html) - this computer only: sources + breakers, gauges found by
                  VEDA (approve as context), recent answers, one run in detail with the exact prompts sent to the AI
GET  /admin/api/overview, GET /admin/api/run/{run_id}, POST /admin/api/approve   (same: this computer only)
GET  /ui/words    fixed wording for screens that call no engine (headlines, emergency steps, disclaimer)
GET  /            the web page (app/web/index.html): home, waiting, answer, share, emergency
Bad input -> HTTP 400 {"error": {"code", "message"}}; a second run while one is running -> 429 (one writer for the
World Model on disk). Nothing secret is ever returned: every text goes through the trace's redaction.
"""
import json
import logging
import os
import queue
import re
import threading
from datetime import datetime

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app import card as card_mod
from app import admin, config, progress, trace, view
from app.adapters import nightshift, zetaris
from app.agents.coordinator import SAFETY

load_dotenv(config.ROOT / ".env")
MAX_QUESTION = 500
WEB_PAGE = config.ROOT / "app" / "web" / "index.html"
LIVE_PAGE = config.ROOT / "app" / "web" / "live.html"
ADMIN_PAGE = config.ROOT / "app" / "web" / "admin.html"
RECORDED = config.ROOT / "data" / "sample" / "live_traces"
RUN_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
QUESTION_HIDDEN = "(the question is not shown here - privacy)"
_watchers, _watch_lock = [], threading.Lock()   # /live/stream subscribers: one queue each
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
           "card": None, "disclaimer": dict(SAFETY), "view": view.answer_view(r), "other": view.other_view(r),
           "how": view.how_it_worked(r["trace"])}
    if r.get("card"):
        out["card"] = {lang: trace.redact(card_mod.render(r["card"], lang)) for lang in ("en", "ms")}
    return out


def public_record(rec, question=None):
    """A trace record for the live log: word for word, redacted, without the question - run_start's input, and any
    field holding the question (or a shortened copy of it, e.g. the place finder's input and its 'normalized' copy)."""
    if rec.get("action") == "run_start":
        question = rec.get("input_summary") or question
    out = view.hide_question({k: v for k, v in rec.items() if k != "trace_id"}, question, QUESTION_HIDDEN)
    return json.loads(trace.redact(json.dumps(out, ensure_ascii=False)))


_live_question = {}                     # run_id -> the question as traced (to hide it in every published record)


def _publish(rec):
    run_id = rec.get("run_id")
    if rec.get("action") == "run_start":
        _live_question[run_id] = rec.get("input_summary")
    with _watch_lock:
        watchers = list(_watchers)
    if watchers:
        data = public_record(rec, _live_question.get(run_id))
        for q in watchers:
            q.put(data)
    if rec.get("action") == "run_end":
        _live_question.pop(run_id, None)


def _run(question, replay, at, on_step=None):
    """One run. The full trace goes to logs/trace-<run_id>.jsonl; stdout (docker logs) gets the same short progress
    lines as the page, one per important step, prefixed with the run id - never the question text (privacy). Every
    record also goes to the live log's watchers (/live/stream)."""
    from app import loop, progress

    def step(rec):
        line = progress.describe(rec)
        if line:
            print(f"[{rec.get('run_id')}] {line}", flush=True)
        _publish(rec)
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


def _local(request):
    """This computer only (operator screens and real users' runs): the server's own loopback address."""
    return (request.client.host if request.client else "") in ("127.0.0.1", "::1", "localhost", "testclient")


@app.get("/live", response_class=HTMLResponse)
def live_page():
    return LIVE_PAGE.read_text(encoding="utf-8")


@app.get("/live/stream")
def live_stream():
    """Every trace record of whatever run is going, as it happens (a comment line every 15 s keeps it open)."""
    q = queue.Queue()
    with _watch_lock:
        _watchers.append(q)

    def stream():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    rec = q.get(timeout=15)
                except queue.Empty:
                    yield ": still here\n\n"
                    continue
                yield f"event: trace\ndata: {json.dumps(rec, ensure_ascii=False)}\n\n"
        finally:
            with _watch_lock:
                if q in _watchers:
                    _watchers.remove(q)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def _read_trace(path, hide_question):
    records, note, question = [], None, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if "redaction" in rec and "action" not in rec:
            note = rec["redaction"]
            continue
        if rec.get("action") == "run_start":
            question = rec.get("input_summary")
        records.append(public_record(rec, question) if hide_question else rec)
    return {"records": records, "note": note}


@app.get("/trace/recorded")
def recorded_list():
    """The recorded live runs (published, JPS readings redacted) for the live log's replay."""
    out = []
    for f in sorted(RECORDED.glob("*.jsonl")):
        first = next((json.loads(x) for x in f.read_text(encoding="utf-8").splitlines()[:3]
                      if '"run_start"' in x), {})
        out.append({"name": f.name, "run_id": first.get("run_id"), "started": first.get("timestamp"),
                    "question": first.get("input_summary")})
    return out


@app.get("/trace/recorded/{name}")
def recorded_one(name: str):
    path = RECORDED / name
    if "/" in name or "\\" in name or not name.endswith(".jsonl") or not path.is_file():
        return _error(404, "not_found", "No recorded run with that name.")
    return _read_trace(path, hide_question=False)


@app.get("/trace/run/{run_id}")
def run_trace(run_id: str, request: Request):
    """A run from logs/ for the live log's per-run view - this computer only; the question is not shown."""
    if not _local(request):
        return _error(403, "local_only", "Run logs are shown on this computer only.")
    path = trace.ROOT / "logs" / f"trace-{run_id}.jsonl"
    if not RUN_ID.match(run_id) or not path.is_file():
        return _error(404, "not_found", "No run with that id.")
    return _read_trace(path, hide_question=True)


LOCAL_ONLY = ("<!doctype html><title>VEDA admin</title><p style='font:18px system-ui;margin:24px'>The operator "
              "screens open on this computer only (http://127.0.0.1).</p>")


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    if not _local(request):
        return HTMLResponse(LOCAL_ONLY, status_code=403)
    return ADMIN_PAGE.read_text(encoding="utf-8")


def _with_world(fn):
    """Run fn(world) holding the run lock (one writer for the World Model on disk); world is None in SAMPLE_MODE
    (each run has its own in-memory World Model, nothing shared to show). -> (result, None) or (None, error)."""
    from app import loop
    if config.sample_mode():
        return fn(None), None
    if not _busy.acquire(blocking=False):
        return None, _error(429, "busy", "VEDA is answering a question - refresh in a minute.")
    run = trace.start_run("admin", quiet=True)          # the World Model's audit file is named after a run
    world = loop.open_world(run.run_id)
    try:
        return fn(world), None
    finally:
        world.store.close()
        trace.end_run("success")
        _busy.release()


@app.get("/admin/api/overview")
def admin_overview(request: Request):
    if not _local(request):
        return _error(403, "local_only", "This computer only.")
    out, err = _with_world(admin.overview)
    return err or out


@app.get("/admin/api/run/{run_id}")
def admin_run(run_id: str, request: Request):
    if not _local(request):
        return _error(403, "local_only", "This computer only.")
    out = admin.run_detail(run_id)
    return out if out is not None else _error(404, "not_found", "No run with that id.")


@app.post("/admin/api/approve")
async def admin_approve(request: Request):
    """'Approve as context': a named person, live mode only. The X-VEDA-Admin header makes a browser ask first
    (CORS preflight), so another web page cannot send this."""
    if not _local(request):
        return _error(403, "local_only", "This computer only.")
    if request.headers.get("x-veda-admin") != "1" or "application/json" not in (request.headers.get("content-type") or ""):
        return _error(400, "bad_request", "Send JSON from the admin page.")
    if config.sample_mode():
        return _error(400, "sample_mode", "SAMPLE_MODE: approval writes to the live World Model - run VEDA live.")
    try:
        body = await request.json()
    except ValueError:
        return _error(400, "bad_json", "Send JSON.")
    key, place, by = (str((body or {}).get(k) or "").strip() for k in ("station_key", "place_id", "by"))
    from app.adapters import zetaris as zt

    def go(world):
        try:
            return admin.approve(world, key, place, by)
        except zt.ZetarisError as e:
            return False, f"cannot check the place: Zetaris {e.kind}"
    out, err = await run_in_threadpool(_with_world, go)
    if err:
        return err
    ok, message = out
    return JSONResponse({"ok": ok, "message": trace.redact(message)}, status_code=200 if ok else 400)


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
