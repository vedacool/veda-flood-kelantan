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

from app import config
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


# ---------- checking the expectations against the REAL run output ----------
def compact(result):
    """The parts of a run result the check needs (the page sends exactly this shape, kept under the proxy's 16 KB)."""
    view = result.get("view") or {}
    how = result.get("how") or {}
    return {"verdict": result.get("verdict"),
            "sources": [{"name": s.get("name"), "used": bool(s.get("used"))} for s in (view.get("sources") or {}).get("en", [])],
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
    if "step_present" in check:
        lines = [ln for s in out.get("steps", []) for ln in s.get("lines", []) if ln.get("action") == check["step_present"]]
        ok = bool(lines)
        if ok:
            return ok, {"en": lines[0]["text"], "ms": lines[0]["text"]}
        return ok, {"en": "This step did not happen in the run.", "ms": "Langkah ini tidak berlaku dalam larian."}
    if "safety_passed" in check:
        texts = [ln["text"] for s in out.get("steps", []) if s.get("key") == "safety" for ln in s.get("lines", [])]
        ok = any(t.startswith("all safety checks passed") for t in texts) == check["safety_passed"]
        said = texts[0] if texts else "no safety step in the run"
        return ok, {"en": said, "ms": said}
    return False, {"en": "unknown check", "ms": "semakan tidak dikenali"}


def check(scene_id, out):
    """Every expectation of a scene against a compact run result -> [{id, ok, said}] + the agents' trail."""
    scene = next(s for s in expected()["scenes"] if s["id"] == scene_id)
    rows = []
    for e in scene["expect"]:
        ok, said = _said(e["check"], out)
        rows.append({"id": e["id"], "ok": ok, "said": said})
    trail = [{"key": s["key"], "who": s["who"], "lines": [ln["text"] for ln in s.get("lines", [])][-3:]}
             for s in out.get("steps", [])]
    return {"verdict": out.get("verdict"), "verdict_name": {lang: _name(out.get("verdict"), lang) for lang in ("en", "ms")},
            "rows": rows, "trail": trail}


# ---------- the one route: /scenes, /scenes/<id>, /scenes/data.json, POST /scenes/<id>/check ----------
async def handle(tail, request):
    parts = [p for p in tail.split("/") if p]
    ids = {s["id"] for s in expected()["scenes"]}
    if request.method == "GET" and (not parts or (len(parts) == 1 and parts[0] in ids)):
        return HTMLResponse(PAGE.read_text(encoding="utf-8"))
    if request.method == "GET" and parts == ["data.json"]:
        exp, data = expected(), {s["id"]: s for s in scene_data()["scenes"]}
        return JSONResponse({"bands": exp["_bands"], "levels": HEADLINE,
                             "scenes": [{**s, "data": data.get(s["id"])} for s in exp["scenes"]]})
    if request.method == "POST" and len(parts) == 2 and parts[0] in ids and parts[1] == "check":
        body = await request.body()
        if len(body) > MAX_BODY:
            return JSONResponse({"error": {"code": "too_big", "message": "Send the compact result only."}}, status_code=413)
        try:
            out = json.loads(body)
        except ValueError:
            return JSONResponse({"error": {"code": "bad_json", "message": "Send the run result as JSON."}}, status_code=400)
        return JSONResponse(check(parts[0], out if isinstance(out, dict) else {}))
    return JSONResponse({"error": {"code": "not_found", "message": "No such scene."}}, status_code=404)
