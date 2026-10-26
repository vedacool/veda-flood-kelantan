"""B-91 Scenes test page (/scenes): read the situation, see the data, know what to expect and why, run the scene,
then check VEDA against the expectation.

    data/scenes/scenes_expected.json   the REVIEWED part: story, question, source label, expectations (+ reason, source,
                                       a check on the run output). Written from the inputs and official guidance.
    data/scenes/scenes_data.json       the inputs shown before the run, BUILT from the fixtures by
                                       `python scripts/make_scenes_data.py` (the same offline path a run takes; each
                                       river value keeps its fixture query hash) - never typed in.

The ✓ / ✗ comes from the REAL run output the page just received (verdict, sources used / left out, the agents'
steps): `check()` never looks at anything else. The page only shows offline demo scenes (replay = river readings
reported in the news, citing JPS; synthetic = made up) - never a live JPS reading (B-75).
"""
import csv
import io
import json
import re
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.responses import HTMLResponse, JSONResponse

from app import config, frame, trail
from app.view import HEADLINE

ROOT = config.ROOT
EXPECTED = ROOT / "data" / "scenes" / "scenes_expected.json"
DATA = ROOT / "data" / "scenes" / "scenes_data.json"
PAGE = ROOT / "app" / "web" / "scenes.html"
ANCHORS = ROOT / "data" / "replay" / "nov2024_anchors.csv"
MYT = timezone(timedelta(hours=8))
QUESTION = {"en": "Is {town} at risk of flooding right now?", "ms": "Adakah {town} berisiko banjir sekarang?"}  # the app's
STEPS_SENT = ("gather", "forecast", "critique", "safety")          # the steps the check and the trail look at
MAX_BODY = 15 * 1024                                                # the demo proxy accepts 16 KB
WHY_MAX = 400                                                       # the plain "why" kept in compact() (Cowork 26 Oct)
# a sentence ends at . ! ? before a space or the end - not in "Kg. Salor" / "Sg. Golok" (names) or "34.7" (numbers)
SENTENCE_END = re.compile(r"(?<!\bKg)(?<!\bSg)(?<!\bKpg)(?<!\bJln)(?<!\bDr)(?<!\bSt)[.!?](?=\s|$)")


def expected():
    return json.loads(EXPECTED.read_text(encoding="utf-8"))


def scene_data():
    return json.loads(DATA.read_text(encoding="utf-8"))


# ---------- building the inputs from the fixtures (scripts/make_scenes_data.py) ----------
def _plain(name):
    return re.sub(r"\s*\(F\d\)$", "", name or "")


def _myt(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(MYT).strftime("%Y-%m-%d %H:%M") if iso else None


def _anchor_source(station_key, at_text):
    """The news report behind the newest reported reading of this gauge at the scene time (the replay anchors)."""
    rows = [r for r in csv.DictReader(ANCHORS.open(encoding="utf-8"))
            if r["station_key"] == station_key and r["observed_at_myt"] <= at_text]
    return max(rows, key=lambda r: r["observed_at_myt"])["source_name"] if rows else None


def build(scene):
    """The inputs of one scene, from an offline run of the app's own path (Data & Reconciler only is kept)."""
    from app import main                                           # here: main imports this module
    town = scene["town"]
    q, rp, when = main.parse_input(QUESTION["en"].format(town=town), scene["replay"], scene["at"])
    with redirect_stdout(io.StringIO()):
        r = main._run(q, rp, when, None, "en")
    ev = r["evidence"]
    ctx = ev.get("context") or {}
    synthetic = config.synthetic(scene["replay"])
    gauges = []
    for g in (ctx.get("gauges") or []) + (ctx.get("sentinels") or []):
        if "Critic's request" in (g.get("selection_reason") or ""):
            continue                                 # found during the run - part of the result, not the inputs
        prov = g.get("provenance") or {}
        th = g.get("thresholds") or {}
        gauges.append({
            "name": _plain(g.get("name")), "station": (g.get("station") or "").split(":")[-1],
            "role": {"controlling": "here", "controlling_secondary": "here", "sentinel": "upstream"}.get(g.get("role"),
                                                                                                       g.get("role")),
            "level_m": g.get("level_m"), "at": _myt(g.get("observed_at")), "age_minutes": g.get("age_minutes"),
            "thresholds": {k: th.get(f"{k}_m") for k in ("normal", "alert", "warning", "danger")},
            "change_1h_m": g.get("change_1h_m"), "change_3h_m": g.get("change_3h_m"),
            "fresh": g.get("freshness") == "fresh", "tide": bool(g.get("tide_influenced")),
            "kind": (prov.get("replay") or {}).get("kind"), "query_hash": prov.get("query_hash")})
    ru = ctx.get("rain_upstream") or {}
    local = ru.get("local") or {}
    rain = {"here": {"name": _plain(local.get("name")), "past_12h_mm": local.get("past_12h_mm"),
                     "past_24h_mm": (ctx.get("rain") or {}).get("rain_past_24h_mm"), "heavy": bool(local.get("heavy"))}
            if local or ctx.get("rain") else None,
            "upstream": [{"name": _plain(u.get("name")), "past_24h_mm": u.get("past_24h_mm"),
                          "past_72h_mm": u.get("past_72h_mm")} for u in ru.get("upstream") or []]}
    src = ev.get("sources") or {}
    based = None
    if not synthetic:
        controlling = next((g for g in gauges if g["role"] == "here"), None)
        cited = _anchor_source(controlling["station"], scene["at"]) if controlling else None
        based = {lang: scene["based_on"][lang] + (f" · {cited}" if cited else "") for lang in ("en", "ms")}
    return {"id": scene["id"], "replay": scene["replay"], "at": scene["at"], "town": town,
            "kind": "synthetic" if synthetic else "replay",
            "source_label": based or {"en": "Made-up example", "ms": "Contoh rekaan"},
            "question": {lang: QUESTION[lang].format(town=town) for lang in ("en", "ms")},
            "gauges": gauges, "rain": rain,
            "met_warnings": {"status": (src.get("mygov_warning") or {}).get("status"),
                             "note": (src.get("mygov_warning") or {}).get("note")},
            "missing": list((ev.get("selected") or {}).get("skipped") or [])}


def build_all():
    return {"_about": "BUILT by scripts/make_scenes_data.py from the fixtures (offline run of each scene, Data & "
                      "Reconciler inputs only) - do not edit by hand. Demo data: replay = river readings reported in "
                      "the news citing JPS; synthetic = made up. Never live JPS readings.",
            "scenes": [build(s) for s in expected()["scenes"]]}


# ---------- where each shown value comes from (Cowork B-91b) ----------
def news_values(scene, gauge):
    """The values of one gauge row that the cited news article itself states (the reviewed allow-list in
    scenes_expected.json) -> [{field, value, source, url}]. Every other value in the row is demo data."""
    shown = {"level": gauge["level_m"], **{k: gauge["thresholds"].get(k) for k in ("alert", "warning", "danger")}}
    out = []
    for article in scene.get("news") or []:
        for v in article["values"]:
            if v["station"] == gauge["station"] and shown.get(v["field"]) == v["value"]:
                out.append({"field": v["field"], "value": v["value"], "source": article["source"], "url": article["url"]})
    return out


def station_lines():
    """The official JPS lines VEDA holds for each gauge (data/stations_mapping.csv) -> {station: {field: m}}."""
    path = ROOT / "data" / "stations_mapping.csv"
    num = lambda v: float(v) if v else None                                          # noqa: E731
    return {r["station_key"]: {k: num(r[f"jps_{k}_m"]) for k in ("alert", "warning", "danger")}
            for r in csv.DictReader(path.open(encoding="utf-8")) if r["record_type"] == "gauge"}


def tagged(scene, data):
    """Each gauge row with where its values come from (Cowork B-91c): `news` = the values the cited article states;
    `lines` = the other JPS lines, from the station list (only when they equal data/stations_mapping.csv);
    `demo` = the row also has generated values (a trend, or a reading no article states). Rain: Open-Meteo archive."""
    if not data:
        return data
    official, out = station_lines(), []
    for g in data["gauges"]:
        news = news_values(scene, g)
        in_news = {n["field"] for n in news}
        lines = [{"field": k, "value": v} for k, v in g["thresholds"].items()
                 if k != "normal" and v is not None and k not in in_news
                 and (official.get(g["station"]) or {}).get(k) == v]
        demo = "level" not in in_news or g["change_1h_m"] is not None or g["change_3h_m"] is not None
        out.append({**g, "news": news, "lines": lines, "demo": demo})
    return {**data, "gauges": out}


# ---------- checking the expectations against the REAL run output ----------
def fit_why(text, limit=WHY_MAX):
    """The plain "why", never cut mid-sentence: whole if it fits, else the whole sentences that fit + " …" (a first
    sentence longer than the limit is kept whole). The page's fitWhy() in scenes.html does the same."""
    if len(text) <= limit:
        return text
    ends = [m.end() for m in SENTENCE_END.finditer(text)]
    fit = [e for e in ends if e + 2 <= limit]
    end = fit[-1] if fit else (ends[0] if ends else len(text))
    return text[:end] + (" …" if end < len(text) else "")


def compact(result):
    """The parts of a run result the check needs (the page sends exactly this shape, kept under the proxy's 16 KB)."""
    view = result.get("view") or {}
    how = result.get("how") or {}
    by_lang = {lang: [{"name": s.get("name"), "used": bool(s.get("used")), "note": (s.get("note") or "")[:80]}
                      for s in (view.get("sources") or {}).get(lang, [])] for lang in ("en", "ms")}
    return {"verdict": result.get("verdict"),
            "why": {lang: fit_why((view.get("why") or {}).get(lang) or "") for lang in ("en", "ms")},
            "sources": [{"name": s["name"], "used": s["used"]} for s in by_lang["en"]],
            "sources_by_lang": by_lang,
            "steps": [{"key": r.get("key"), "who": r.get("who"),
                       "lines": [{"action": ln.get("action"), "text": (ln.get("text") or "")[:160]} for ln in r.get("lines", [])][:12]}
                      for r in how.get("rows", []) if r.get("key") in STEPS_SENT]}


def _name(code, lang):
    return (HEADLINE.get(code) or {}).get(lang, code or "-")


def _said(check, out):
    """One check -> (ok, what VEDA did in plain words {en, ms})."""
    v = out.get("verdict")
    if "verdict_in" in check or "verdict_not_in" in check:
        ok = v in check["verdict_in"] if "verdict_in" in check else v not in check["verdict_not_in"]
        return ok, {lang: ("VEDA said: " if lang == "en" else "VEDA kata: ") + _name(v, lang) for lang in ("en", "ms")}
    if "used" in check or "left_out" in check:
        want_used = "used" in check
        parts, ok = {"en": [], "ms": []}, True
        for sub in check.get("used") or check.get("left_out"):
            hits = [s for s in out.get("sources", []) if sub.lower() in (s.get("name") or "").lower()]
            used = any(s["used"] for s in hits)
            if not hits:
                ok = False
                parts["en"].append(f"{sub}: not in VEDA's source list")
                parts["ms"].append(f"{sub}: tiada dalam senarai sumber VEDA")
            else:
                ok = ok and (used if want_used else not used)
                parts["en"].append(f"{sub}: {'used' if used else 'left out'}")
                parts["ms"].append(f"{sub}: {'digunakan' if used else 'diketepikan'}")
        return ok, {lang: "; ".join(parts[lang]) for lang in parts}
    if "step_present" in check:          # plain words on screen (B-96); the raw step text stays in the technical log
        ok = any(ln.get("action") == check["step_present"] for s in out.get("steps", []) for ln in s.get("lines", []))
        return ok, STEP_SAID[ok]
    if "safety_passed" in check:
        texts = [ln["text"] for s in out.get("steps", []) if s.get("key") == "safety" for ln in s.get("lines", [])]
        passed = any(t.startswith("all safety checks passed") for t in texts)
        return passed == check["safety_passed"], SAFETY_SAID[passed]
    return False, {"en": "unknown check", "ms": "semakan tidak dikenali"}


STEP_SAID = {True: {"en": "This step happened in the run.", "ms": "Langkah ini berlaku semasa ujian."},
             False: {"en": "This step did not happen in the run.", "ms": "Langkah ini tidak berlaku semasa ujian."}}
SAFETY_SAID = {True: {"en": "All safety checks passed.", "ms": "Semua semakan keselamatan lulus."},
               False: {"en": "The safety gate had to fix the answer.",
                       "ms": "Semakan keselamatan terpaksa membetulkan jawapan."}}


def check(scene_id, out):
    """Every expectation of a scene against a compact run result -> [{id, ok, said}], "N of M matched", the plain
    "How VEDA got there" lines (app/trail.py) and the raw step text for the technical log."""
    scene = next(s for s in expected()["scenes"] if s["id"] == scene_id)
    rows = []
    for e in scene["expect"]:
        ok, said = _said(e["check"], out)
        rows.append({"id": e["id"], "ok": ok, "said": said})
    log = [{"key": s["key"], "who": s["who"], "lines": [ln["text"] for ln in s.get("lines", [])]}
           for s in out.get("steps", [])]                  # raw text: only behind "Show technical log"
    return {"verdict": out.get("verdict"), "verdict_name": {lang: _name(out.get("verdict"), lang) for lang in ("en", "ms")},
            "rows": rows, "matched": sum(r["ok"] for r in rows), "total": len(rows),
            "how": {lang: trail.how_lines(out, lang) for lang in ("en", "ms")}, "log": log}


def compact_shape_ok(out):
    """True when `out` has the types compact() gives (every key optional): what check() and trail.how_lines() read."""
    def strs(d):
        return isinstance(d, dict) and all(isinstance(v, str) for v in d.values())

    def source(s):
        return isinstance(s, dict) and isinstance(s.get("name", ""), str) and isinstance(s.get("used", False), bool) \
            and isinstance(s.get("note", ""), str)

    def step(s):
        return isinstance(s, dict) and isinstance(s.get("key", ""), str) and isinstance(s.get("who", ""), str) \
            and isinstance(s.get("lines", []), list) and all(
                isinstance(ln, dict) and isinstance(ln.get("action", ""), (str, type(None)))
                and isinstance(ln.get("text", ""), str) for ln in s.get("lines", []))

    if not isinstance(out, dict):
        return False
    by_lang = out.get("sources_by_lang", {})
    return (isinstance(out.get("verdict"), (str, type(None))) and strs(out.get("why", {}))
            and isinstance(out.get("sources", []), list) and all(map(source, out.get("sources", [])))
            and isinstance(by_lang, dict) and all(isinstance(v, list) and all(map(source, v)) for v in by_lang.values())
            and isinstance(out.get("steps", []), list) and all(map(step, out.get("steps", []))))


# ---------- the one route: /scenes, /scenes/<id>, /scenes/data.json, POST /scenes/<id>/check ----------
async def handle(tail, request):
    parts = [p for p in tail.split("/") if p]
    ids = {s["id"] for s in expected()["scenes"]}
    if request.method == "GET" and (not parts or (len(parts) == 1 and parts[0] in ids)):
        return HTMLResponse(frame.framed(PAGE.read_text(encoding="utf-8"), "scenes"))   # B-96 shared frame
    if request.method == "GET" and parts == ["data.json"]:
        exp, data = expected(), {s["id"]: s for s in scene_data()["scenes"]}
        return JSONResponse({"bands": exp["_bands"], "levels": HEADLINE,
                             "scenes": [{**s, "data": tagged(s, data.get(s["id"]))} for s in exp["scenes"]]})
    if request.method == "POST" and len(parts) == 2 and parts[0] in ids and parts[1] == "check":
        body = await request.body()
        if len(body) > MAX_BODY:
            return JSONResponse({"error": {"code": "too_big", "message": "Send the compact result only."}}, status_code=413)
        try:
            out = json.loads(body)
        except ValueError:
            return JSONResponse({"error": {"code": "bad_json", "message": "Send the run result as JSON."}}, status_code=400)
        if not compact_shape_ok(out):                      # audit 26 Oct: a malformed body is a 400, never a 500
            return JSONResponse({"error": {"code": "bad_shape", "message": "Send the compact result (see compact())."}},
                                status_code=400)
        return JSONResponse(check(parts[0], out))
    return JSONResponse({"error": {"code": "not_found", "message": "No such scene."}}, status_code=404)
