"""VEDA's public API, version 1 (B-92) - run the agents without the web page. Mounted at /api by app/main.py:

    POST /api/v1/ask      {"question": "...", "lang": "en" | "bm", "scene": "<id>"?} -> the answer as JSON
    GET  /api/v1/scenes   the offline scenes (id, title, source label)
    GET  /api/v1/health   the same status as /health
    GET  /api/docs        these three routes only, with a filled-in example (/api/openapi.json)

The same code path as the web page: main.parse_input -> main._run (loop.run: Coordinator -> Data & Reconciler ->
Forecast -> Critic -> safety gate) -> main.result_json, then this module picks the public fields. ask() is the one
function behind both the endpoint and the CLI (python -m veda ask ...). Nothing here changes a level: the answer is
the loop's, after the safety gate. Errors are JSON: {"error": {"code", "message"}}.
"""
import json

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app import config, trace, view
from app.agents import critic

MAX_QUESTION = 300               # Cowork 24 Oct: the API takes 1-300 characters (the web page allows 500)
MAX_BODY = 4096                  # bytes
LANGS = {"en": "en", "bm": "ms", "ms": "ms"}       # the API says "bm"; inside VEDA it is "ms"
SCENE_SOURCE = {"replay": "past flood replay", "synthetic": "made-up test scene"}   # the live log's own words
# /api/docs only: Swagger UI loads its script and style from jsDelivr (the rest of VEDA loads nothing from outside)
DOCS_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")

EXAMPLE_REQUEST = {"question": "Is Tumpat safe tonight?", "lang": "en", "scene": "synthetic_calm"}
EXAMPLE_RESPONSE = {  # a real offline answer to EXAMPLE_REQUEST (24 Oct), trimmed - documentation only
    "run_id": "20261024-223923-6789", "mode": "offline sample", "scene": "SYNTHETIC · calm day", "place": "Tumpat",
    "level": "NORMAL", "level_label": {"en": "Normal for now", "bm": "Normal buat masa ini"},
    "what_to_do": ["Nothing to do now.", "No action needed.", "Keep an eye on JPS updates."],
    "why": ["The river is 0.62 m below the alert level.",
            "The river is below the alert level and nothing else points to a flood."],
    "facts_used": [{"source": "River level: Sg. Kelantan di Kg. Kok Majid", "note": "used"},
                   {"source": "Rain upstream (8 rain points, Open-Meteo)", "note": "used"}],
    "facts_left_out": [{"source": "Flood warnings (data.gov.my)", "reason": "left out: out of date"}],
    "critic_checks": {"approved": True, "checked_by": ["code", "zetaris"], "problems": [],
                      "checks": ["verdict words = the card's verdict", "every number is on the card", "..."]},
    "ai_judgement": "live mode only",
    "steps": [{"step": "Understand the question", "agent": "Coordinator", "seconds": 0.0, "ai_calls": 0,
               "note": "full path, answer in English - question mentions 'tonight' (next days)"},
              {"step": "Double-check the answer", "agent": "Critic", "seconds": 0.0, "ai_calls": 0,
               "note": "approve: 0 problem(s)"}],
    "text": "WHAT TO DO NOW: Nothing to do now. ...", "language": "en", "emergency": False, "nearest_covered": None,
    "disclaimer": "Not an official warning. Follow JPS / APM / police instructions. Emergency: 999, APM (Civil "
                  "Defence): 991.",
}


class BadInput(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code = status, code


def _error(status, code, message):
    return JSONResponse({"error": {"code": code, "message": trace.redact(message)}}, status_code=status)


def ask(question, lang="en", scene=None, on_step=None):
    """One question through VEDA's agents -> the public answer (dict). Raises BadInput (bad input, or busy). The
    function behind POST /api/v1/ask and the CLI."""
    from app import main                                      # main mounts this module: import it late
    if not isinstance(question, str) or not question.strip():
        raise BadInput(400, "empty_question", "Ask a question about a place in Kelantan (1-300 characters).")
    if len(question) > MAX_QUESTION:
        raise BadInput(400, "question_too_long", f"Please keep the question to {MAX_QUESTION} characters or fewer.")
    if lang not in LANGS:
        raise BadInput(400, "bad_lang", "lang must be \"en\" or \"bm\".")
    if scene not in (None, "") and scene not in config.REPLAYS:
        raise BadInput(400, "unknown_scene", f"Known scenes: {', '.join(sorted(config.REPLAYS))} (GET /api/v1/scenes).")
    try:
        q, replay, at = main.parse_input(question, scene or None, None)
    except main.BadInput as e:
        raise BadInput(400, e.code, str(e)) from None
    if not main._busy.acquire(blocking=False):
        raise BadInput(429, "busy", "VEDA is answering another question - try again in a minute.")
    try:
        r = main._run(q, replay, at, on_step, LANGS[lang])
    finally:
        main._busy.release()
    return public_answer(main.result_json(r), r, lang)


def public_answer(out, r, lang):
    """main.result_json() (the web page's answer) -> the API's fields, in `lang`."""
    lg = LANGS[lang]
    v = out.get("view") or {}
    level = out.get("verdict") if v else None
    rv = (r.get("reviews") or [{}])[-1]
    srcs = (v.get("sources") or {}).get(lg) or []
    j = out.get("ai_judgement")
    scene = ((r.get("evidence") or {}).get("replay") or {}).get("scenario")
    steps = [{"step": row["name"][lg], "agent": row["who"], "seconds": row.get("seconds"),
              "ai_calls": len(row.get("ai") or []),
              "note": row["lines"][-1]["text"] if row.get("lines") else None}
             for row in (out.get("how") or {}).get("rows") or []]
    why = [x for x in ((v.get("line") or {}).get(lg), (v.get("why") or {}).get(lg)) if x] if v else []
    return {
        "run_id": out["run_id"], "mode": "offline sample" if r.get("sample_mode", config.sample_mode()) else "live",
        "scene": (config.REPLAYS.get(scene) or {}).get("title"), "place": v.get("place"),
        "level": level,
        "level_label": {"en": view.HEADLINE[level]["en"], "bm": view.HEADLINE[level]["ms"]} if level else None,
        "what_to_do": list(dict.fromkeys(((v.get("action") or {}).get(lg) or []) + ((v.get("steps") or {}).get(lg) or [])
                                         + ((v.get("todo_more") or {}).get(lg) or []))),
        "why": list(dict.fromkeys(why)),
        "facts_used": [{"source": s["name"], "note": s["note"]} for s in srcs if s["used"]],
        "facts_left_out": [{"source": s["name"], "reason": s["note"]} for s in srcs if not s["used"]],
        "critic_checks": {"approved": out.get("approved_by_critic"), "checked_by": rv.get("checked_by") or [],
                          "problems": sorted({p["type"] for p in rv.get("problems") or []}),
                          "checks": list(critic.CODE_CHECKS)},
        "ai_judgement": ("live mode only" if (j or {}).get("status") == "live_only" else j
                         if j else "not run (quick path: answer and review by code)" if v else None),
        "steps": steps,
        "signs": ({"title": v["signs"]["title"][lg], "lines": v["signs"]["lines"][lg], "footer": v["signs"]["footer"][lg]}
                  if v.get("signs") else None),                                   # B-105
        "trail": [{"who": r["who"], "text": r["text"]} for r in ((out.get("trail") or {}).get(lg) or [])],   # B-96
        "text": out.get("output"), "language": "bm" if out.get("language") == "ms" else out.get("language"),
        "emergency": bool(v.get("emergency")), "nearest_covered": out.get("nearest_covered"),
        "disclaimer": (out.get("disclaimer") or {}).get(lg),
    }


def scenes():
    return [{"id": k, "title": s["title"], "source": SCENE_SOURCE.get(s.get("kind"), s.get("kind")),
             "default_at": s["default_at"]} for k, s in config.REPLAYS.items()]


api = FastAPI(title="VEDA API", version="1.0",
              description="Ask VEDA about flood risk for a place in Kelantan - the same agents as the web page "
                          "(Coordinator, Data & Reconciler, Forecast, Critic, safety gate). Decision support only.",
              docs_url=None, redoc_url=None, openapi_url="/openapi.json", servers=[{"url": "/api"}])


@api.get("/docs", include_in_schema=False)
def docs():
    page = get_swagger_ui_html(openapi_url="/api/openapi.json", title="VEDA API")
    page.headers["Content-Security-Policy"] = DOCS_CSP
    return page


@api.post("/v1/ask", summary="Ask VEDA one question", openapi_extra={
    "requestBody": {"required": True, "content": {"application/json": {
        "schema": {"type": "object", "required": ["question"], "properties": {
            "question": {"type": "string", "minLength": 1, "maxLength": MAX_QUESTION},
            "lang": {"type": "string", "enum": ["en", "bm"], "default": "en"},
            "scene": {"type": "string", "description": "an offline scene id from GET /api/v1/scenes"}}},
        "example": EXAMPLE_REQUEST}}},
    "responses": {"200": {"description": "The answer", "content": {"application/json": {"example": EXAMPLE_RESPONSE}}},
                  "400": {"description": "Bad input", "content": {"application/json": {"example": {
                      "error": {"code": "question_too_long", "message": "Please keep the question to 300 characters or fewer."}}}}},
                  "413": {"description": "Body over 4 KB"}, "415": {"description": "Not JSON"},
                  "429": {"description": "Another question is being answered"}}})
async def ask_endpoint(request: Request):
    if "application/json" not in (request.headers.get("content-type") or ""):
        return _error(415, "json_only", "Send JSON (Content-Type: application/json).")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return _error(413, "body_too_large", f"The body must be {MAX_BODY} bytes or less.")
    try:
        body = json.loads(raw or b"null")
    except ValueError:
        return _error(400, "bad_json", "Send JSON like {\"question\": \"Is Tumpat safe tonight?\"}.")
    if not isinstance(body, dict):
        return _error(400, "bad_json", "Send a JSON object.")
    try:
        return await run_in_threadpool(ask, body.get("question"), body.get("lang") or "en", body.get("scene"))
    except BadInput as e:
        return _error(e.status, e.code, str(e))


@api.get("/v1/scenes", summary="The offline scenes")
def scenes_endpoint():
    return {"scenes": scenes()}


@api.get("/v1/health", summary="Is VEDA ready?")
async def health_endpoint():
    from app import main
    return await main.health()
