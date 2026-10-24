"""Forecast agent (B-16): turns the evidence into a verdict with a range and a confidence. Plain code - every
verdict can be traced to a rule.

    fc = forecast_agent.forecast(plan, evidence, world)
    fc["verdict"]      NORMAL | WATCH | PREPARE | ACT | INSUFFICIENT_DATA
    fc["triggers"]     which rules fired, in plain words

Rules = D-06 (approved in principle 22 Oct, TENTATIVE - Dr Ariff to review, docs/review_pack_ariff.md section A):
    ACT      controlling gauge >= Danger, or projected to reach Danger within 12 h
    PREPARE  controlling gauge >= Warning, or projected to reach Danger within 24 h, or an upstream sentinel >= Danger,
             or rain: next 72 h >= 200 mm or next 24 h >= 150 mm
    WATCH    controlling gauge >= Alert, or projected to reach Alert within 24 h, or an upstream sentinel >= Alert,
             or rain: next 72 h >= 100 mm on wet ground (past 7 days >= 150 mm)
    rising fast (>= 0.3 m/h at the controlling gauge) moves the verdict up one level
    INSUFFICIENT_DATA when the controlling gauge has no fresh, healthy reading - never NORMAL on missing data.
Projection: straight-line from two rise rates (last 1 h, last 3 h / 3) -> a range at +6/12/24 h; nothing beyond
24 h (for 24-48 h only upstream gauges and rain count). "Projected to reach" uses the EARLIEST time (safety first).
Tide-influenced gauges (mapping role says so: Tambatan Diraja, Kok Majid - tentative) are judged on their current
level only: a few hours of rise there may just be the tide, so no straight-line projection and no "rising fast".
Mode "now" (quick path): current levels only, no projection.
Reads historic peaks from the World Model; writes its forecast there as a fact about the place.
"""
import re
from datetime import datetime, timedelta, timezone

from app import trace
from app.config import MYT
from app.engines.world_model.veda_ingest import place_id

AGENT = "Forecast"
LEVELS = ("NORMAL", "WATCH", "PREPARE", "ACT")
RULES = "D-06 verdict rules, tentative 22 Oct - Dr Ariff to review"
HORIZONS_H = (6, 12, 24)
RISING_FAST_M_PER_H = 0.3        # A2 (tentative)
SENTINEL_RISING_M_3H = 0.3       # an upstream gauge counts as "rising" above this 3-hour change
WET_GROUND_7D_MM = 150.0         # A4 (tentative)
RAIN_WATCH_72H_MM = 100.0
RAIN_PREPARE_72H_MM = 200.0
RAIN_PREPARE_24H_MM = 150.0
BAND_NAMES = {  # JPS level names shown with every verdict (B-21)
    "below_normal": {"en": "Normal", "ms": "Normal"},   # JPS shows Normal / Alert / Warning / Danger only (23 Oct)
    "normal": {"en": "Normal", "ms": "Normal"},
    "alert": {"en": "Alert", "ms": "Waspada"},
    "warning": {"en": "Warning", "ms": "Amaran"},
    "danger": {"en": "Danger", "ms": "Bahaya"},
}
NOT_CHECKED = ["MetMalaysia warnings without a Waspada / Buruk / Bahaya level (rule A uses leveled rain warnings only)", "official warnings / evacuation orders (no source yet)",
               "step-down wait of 12-24 h (A3, needs a verdict history)",
               "JKR road closures and official PPS openings (no source; OSM shows possible PPS and bridges only)"]


def _usable(g):
    return g["level_m"] is not None and g.get("freshness") in ("fresh", "aging") and \
        (g.get("health") or {"ok": True})["ok"]


def rates(g):
    """Rise rates in m/h from the last 1 h and the last 3 h (either may be missing)."""
    out = []
    if g.get("change_1h_m") is not None:
        out.append(g["change_1h_m"])
    if g.get("change_3h_m") is not None:
        out.append(round(g["change_3h_m"] / 3, 3))
    return out


def falling(rs):
    """Both trends point down (Husaini 23 Oct: a falling river gets 'falling', no projected range)."""
    return bool(rs) and all(r <= 0 for r in rs) and any(r < 0 for r in rs)


def projection(level, rs, floor=None):
    """{'6h': {'min', 'max'}, ...} straight-line range, or {} without a rate or when falling. Never below `floor`
    (the gauge's lowest level in the past 7 days, Husaini 23 Oct)."""
    if not rs or falling(rs):
        return {}
    low = (lambda v: max(v, floor)) if floor is not None else (lambda v: v)          # noqa: E731
    return {f"{h}h": {"min": round(low(level + min(rs) * h), 2), "max": round(low(level + max(rs) * h), 2)}
            for h in HORIZONS_H}


def hours_to(level, threshold, rs):
    """Hours until `threshold`: {'earliest', 'latest'} (latest None = may not get there), 0 if already there,
    None if not rising or unknown."""
    if threshold is None:
        return None
    if level >= threshold:
        return {"earliest": 0, "latest": 0}
    times = sorted((threshold - level) / r for r in rs if r > 0)
    if not times:
        return None
    return {"earliest": round(times[0], 1), "latest": round(times[-1], 1) if len(times) == len(rs) else None}


def _gauge_rules(g, now_only):
    """Triggers for one controlling gauge -> [(level, rule, reason)], plus its trend summary."""
    th, level, name = g["thresholds"], g["level_m"], g["name"]
    tidal = bool(g.get("tide_influenced"))
    rs = [] if now_only or tidal else rates(g)
    fired = []
    for key, verdict in (("danger_m", "ACT"), ("warning_m", "PREPARE"), ("alert_m", "WATCH")):
        if th.get(key) is not None and level >= th[key]:
            fired.append((verdict, f"level>={key[:-2]}", f"{name} is {level} m, at or above {key[:-2]} "
                                                         f"({th[key]} m)"))
            break
    to = {k[:-2]: hours_to(level, th.get(k), rs) for k in ("alert_m", "warning_m", "danger_m")}
    if not now_only:
        d = to["danger"]
        if d and 0 < d["earliest"] <= 12:
            fired.append(("ACT", "danger<=12h", f"{name} could reach danger in about {d['earliest']} h"))
        elif d and 0 < d["earliest"] <= 24:
            fired.append(("PREPARE", "danger<=24h", f"{name} could reach danger in about {d['earliest']} h"))
        a = to["alert"]
        if a and 0 < a["earliest"] <= 24:
            fired.append(("WATCH", "alert<=24h", f"{name} could reach alert in about {a['earliest']} h"))
    fast = [] if tidal else [r for r in rates(g) if r >= RISING_FAST_M_PER_H]
    trend = {"station": g["station"], "gauge": name, "role": g["role"], "level_m": level, "band": g["band"],
             "band_name": BAND_NAMES.get(g["band"]), "observed_at": g["observed_at"],
             "rate_m_per_h": {"min": min(rs), "max": max(rs)} if rs else None,
             "projection_m": projection(level, rs, g.get("min_7d_m")), "falling": falling(rs),
             "hours_to": {k: v for k, v in to.items() if v},
             "rising_fast": bool(fast), "tide_influenced": tidal,
             "trend_note": "tide-influenced: trend not projected" if tidal and not now_only else None}
    return fired, trend, bool(fast)


def _upstream(sentinels):
    """Sentinel triggers + one line each: band, rising or not, and when a rise would arrive."""
    fired, notes = [], []
    for s in sentinels:
        if not _usable(s):
            notes.append({"gauge": s["name"], "status": "no fresh reading", "chain_order": s.get("chain_order")})
            continue
        lag = s.get("travel_time_h")
        arrives = {"min": lag["min"], "max": lag["max"], "status": lag["status"]} if lag and lag.get("min") is not None \
            else None
        rising = (s.get("change_3h_m") or 0) >= SENTINEL_RISING_M_3H
        when = f", reaches here in {arrives['min']}-{arrives['max']} h" if arrives else ""
        if s["band"] == "danger":
            fired.append(("PREPARE", "sentinel>=danger", f"upstream {s['name']} is at danger ({s['level_m']} m){when}"))
        elif s["band"] in ("alert", "warning"):
            fired.append(("WATCH", "sentinel>=alert", f"upstream {s['name']} is at {s['band']} ({s['level_m']} m){when}"))
        notes.append({"gauge": s["name"], "level_m": s["level_m"], "band": s["band"],
                      "band_name": BAND_NAMES.get(s["band"]), "rising": rising, "arrives_in_h": arrives,
                      "chain_order": s.get("chain_order")})
    return fired, notes


def _rain(rain):
    if not rain:
        return [], None
    past7, n24, n72 = rain.get("rain_past_7d_mm"), rain.get("rain_next_24h_mm"), rain.get("rain_next_72h_mm")
    fired = []
    if (n72 or 0) >= RAIN_PREPARE_72H_MM or (n24 or 0) >= RAIN_PREPARE_24H_MM:
        parts = [f"{v} mm in {h} h" for v, h in ((n24, 24), (n72, 72)) if v is not None]   # A-P3-5: never "None mm"
        fired.append(("PREPARE", "rain-heavy", "heavy rain forecast: " + ", ".join(parts)))
    elif (n72 or 0) >= RAIN_WATCH_72H_MM and (past7 or 0) >= WET_GROUND_7D_MM:
        fired.append(("WATCH", "rain-wet-ground", f"{n72} mm forecast in 72 h on wet ground ({past7} mm in 7 days)"))
    return fired, {"next_24h_mm": n24, "next_72h_mm": n72, "past_7d_mm": past7, "wet_ground":
                   past7 is not None and past7 >= WET_GROUND_7D_MM, "freshness": rain.get("freshness")}


# Rule A (review pack, approved by Cowork 24 Oct, tentative until Dr Ariff answers L11): an active MetMalaysia rain
# warning for the town's district sets a MINIMUM verdict - it can only raise. The level is read from the heading
# (MetMalaysia: Waspada = alert, Buruk = severe / bad weather, Bahaya = danger); a warning without a level (e.g. a
# thunderstorm warning) sets nothing.
MET_LEVELS = (("bahaya", "PREPARE", re.compile(r"\b(DANGER\s+LEVEL|TAHAP\s+BAHAYA)\b", re.I)),
              ("buruk", "PREPARE", re.compile(r"\b(SEVERE\s+LEVEL|BAD\s+WEATHER\s+LEVEL|TAHAP\s+BURUK)\b", re.I)),
              ("waspada", "WATCH", re.compile(r"\b(ALERT\s+LEVEL|TAHAP\s+WASPADA)\b", re.I)))


THUNDER = re.compile(r"THUNDERSTORM|RIBUT\s+PETIR", re.I)


def thunderstorm(active):
    """True when an active district warning is a thunderstorm warning without a rain level (Cowork 24 Oct: no verdict
    change, a flash-flood advice line on the card at any verdict)."""
    return any(THUNDER.search(w.get("heading") or "") and not warning_level(w.get("heading"))[0] for w in active or [])


def warning_level(heading):
    """('waspada' | 'buruk' | 'bahaya', minimum verdict) from a MetMalaysia warning heading, or (None, None)."""
    for level, minimum, rx in MET_LEVELS:
        if rx.search(heading or ""):
            return level, minimum
    return None, None


def _met_warning(evidence):
    """Rule A: [(minimum verdict, 'met-warning', reason)] for the highest-level active warning; traced either way."""
    active = ((evidence or {}).get("met_warnings") or {}).get("active") or []
    if not active:
        return []
    levels = [(w, *warning_level(w.get("heading"))) for w in active]
    leveled = [x for x in levels if x[1]]
    if not leveled:
        other = [w for w in active if not THUNDER.search(w.get("heading") or "")]   # thunderstorms: traced in _finish
        if other:
            trace.step(AGENT, "forecast.met_warning", output_summary="active MetMalaysia warning without a level: "
                       + "; ".join(str(w.get("heading")) for w in other[:2]),
                       decision="no Waspada / Buruk / Bahaya level -> no minimum set (rule A)")
        return []
    # the highest minimum, then the highest level: Bahaya before Buruk (both PREPARE) - audit 24 Oct P3
    order = [lv for lv, _, _ in reversed(MET_LEVELS)]
    w, level, minimum = max(leveled, key=lambda x: (LEVELS.index(x[2]), order.index(x[1])))
    trace.step(AGENT, "forecast.met_warning", output_summary=f"rain warning ({level.capitalize()}) → minimum {minimum}",
               input_summary=w.get("heading"), target_agent="Coordinator",
               decision="rule A (tentative, L11): an official MetMalaysia rain warning for this district sets a "
                        "minimum verdict - it can only raise")
    return [(minimum, "met-warning", f"MetMalaysia {level.capitalize()} rain warning: {w.get('heading')}")]


def _rain_upstream(ru):
    """B-88: heavy rain at an upstream rain point -> at least WATCH (also when its arrival time is not known)."""
    if not ru or not ru.get("heavy_upstream"):
        return []
    heavy = [u for u in ru["upstream"] if u["point"] in ru["heavy_upstream"]]
    what = "; ".join(f"{u['name']} {u['past_72h_mm']} mm in 72 h / {u['past_24h_mm']} mm in 24 h"
                     + (f" (forecast {u['next_24h_mm']} mm in 24 h)" if u["heavy_forecast"] and not u["heavy_fallen"] else "")
                     + (f", may reach here in {u['window']['min']:g}-{u['window']['max']:g} h" if u["window"]
                        else ", arrival time not known") for u in heavy)
    return [("WATCH", "upstream-rain", f"heavy rain upstream: {what}")]


def peak_time(p):
    """From when a historic peak is KNOWN to have happened (MYT), from 'observed_when' ('27 Nov 2024 19:30',
    '29 Nov 2024', '2014') or the event name ('Dec 2014 ...'); None if it cannot be read. A date without a time counts
    from the END of that day (month / year: the end of it) - the peak may have come late that day, and a replay must
    never use it earlier (audit A-P3-5: date-only peaks parsed to midnight)."""
    for text, fmt in ((p.get("observed_when"), "%d %b %Y %H:%M"), (p.get("observed_when"), "%d %b %Y"),
                      ((p.get("event") or "")[:8], "%b %Y"), (p.get("observed_when"), "%Y")):
        try:
            t = datetime.strptime(str(text).strip(), fmt).replace(tzinfo=MYT)
        except (ValueError, TypeError):
            continue
        if fmt == "%d %b %Y":
            return t + timedelta(days=1)
        if fmt == "%b %Y":
            return t.replace(year=t.year + (t.month == 12), month=t.month % 12 + 1)
        if fmt == "%Y":
            return t.replace(year=t.year + 1)
        return t
    return None


def _history(world, g, top, clock=None):
    """Historic peaks at the controlling gauge (World Model read) compared with now and the projection. With a
    clock (replay, B-70) only peaks from BEFORE that time are used - a later flood is hindsight."""
    facts = world.facts_about(g["station"], "historic_peaks") if world else []
    peaks = facts[-1]["value"] if facts else []
    if clock is not None:
        peaks = [p for p in peaks if (peak_time(p) or clock) < clock]
    out = [{"event": p["event"], "peak_m": p["peak_m"], "above_now_m": round(p["peak_m"] - g["level_m"], 2),
            "source": p["source_type"], "reconstructed": bool(p.get("reconstructed"))} for p in peaks[:3]]
    dec2014 = next((p for p in peaks if p["event"] == "Dec 2014"), None)
    if dec2014 is not None and dec2014 not in peaks[:3]:          # the card always compares with 2014 (B-70)
        out.append({"event": dec2014["event"], "peak_m": dec2014["peak_m"],
                    "above_now_m": round(dec2014["peak_m"] - g["level_m"], 2), "source": dec2014["source_type"],
                    "reconstructed": bool(dec2014.get("reconstructed"))})
    bigger = None if dec2014 is None else (top if top is not None else g["level_m"]) > dec2014["peak_m"]
    return out, bigger


def _confidence(main, others, fired, rain, now_only):
    score, why = 0.85, []
    replay = ((main.get("provenance") or {}).get("replay") or {})
    if replay and not replay.get("time_exact", True):       # Husaini 22 Oct night: approximate times -> medium
        score = min(score, 0.69)
        why.append("trend built on readings with approximate times (replay)")
    if main.get("backup_for"):                                 # B-15: a stand-in gauge -> one step lower
        score = min(score, 0.69)
        why.append(f"backup gauge in use ({main['backup_for']} silent)")
    if main.get("freshness") == "aging":
        score = min(score - 0.15, 0.69)          # A-P3-5: an aging reading is never "high" confidence
        why.append("controlling reading is aging")
    rs = rates(main)
    if now_only:
        score -= 0.1
        why.append("quick check: current levels only, no projection")
    elif main.get("tide_influenced"):
        score -= 0.1
        why.append("tide-influenced gauge: trend not projected")
    elif not rs:
        score -= 0.15
        why.append("no recent change data - trend unknown")
    elif max(rs) > 0.05 and min(rs) < -0.05:
        score -= 0.1
        why.append("1 h and 3 h trends disagree")
    if any(r[1] == "upstream-rain" for r in fired):
        score -= 0.05
        why.append("the upstream rain rule and its arrival times are tentative")
    if any(r[1].startswith("sentinel") for r in fired):
        score -= 0.05
        why.append("upstream travel times are tentative")
    if any(r[1].startswith("rain") for r in fired) and (rain or {}).get("freshness") != "fresh":
        score -= 0.1
        why.append("rain forecast age not confirmed")
    if any(not _usable(g) for g in others):
        score -= 0.1
        why.append("second controlling gauge has no fresh reading")
    score = round(max(0.1, score), 2)
    return {"score": score, "label": "high" if score >= 0.7 else "medium" if score >= 0.5 else "low",
            "reasons": why or ["fresh readings, consistent trend"]}


def forecast(plan, evidence, world=None, now=None):
    """Verdict + range + confidence for plan['place'] from the Data & Reconciler evidence. Never raises."""
    run = trace.current_run()
    run_id = run.run_id if run else None
    now_only = plan.get("effort") == "quick"
    ctx = evidence.get("context") or {}
    controlling = [g for g in ctx.get("gauges", []) if g["role"] in ("controlling", "controlling_secondary")]
    main = next((g for g in controlling if g["role"] == "controlling"), None)
    out = {"place": (evidence.get("place") or {}).get("name"), "mode": "now" if now_only else "full",
           "rules": RULES, "not_checked": NOT_CHECKED}
    if not evidence.get("usable") or main is None or not any(main["thresholds"].get(k) for k in
                                                             ("alert_m", "warning_m", "danger_m")):
        why = ("no controlling gauge for this place" if main is None else
               "the controlling gauge has no thresholds" if evidence.get("usable") else
               "the controlling gauge has no fresh, healthy reading")
        triggers = [{"level": "INSUFFICIENT_DATA", "rule": "fail-safe", "reason": why}]
        verdict = "INSUFFICIENT_DATA"
        # Cowork 24 Oct (tentative, L11): no river reading + an official Buruk / Bahaya rain warning for the district
        # -> Get ready anyway (an official warning is enough to prepare); Waspada stays "Can't confirm"
        severe = [(w, lvl) for w in ((evidence.get("met_warnings") or {}).get("active") or [])
                  for lvl, _ in [warning_level(w.get("heading"))] if lvl in ("buruk", "bahaya")]
        if severe:
            w, lvl = max(severe, key=lambda x: x[1] == "bahaya")
            verdict = "PREPARE"
            triggers.insert(0, {"level": "PREPARE", "rule": "met-warning-no-river",
                                "reason": f"MetMalaysia {lvl.capitalize()} rain warning: {w.get('heading')}; {why}"})
            trace.step(AGENT, "forecast.met_warning", input_summary=w.get("heading"), target_agent="Coordinator",
                       output_summary=f"rain warning ({lvl.capitalize()}) + no river reading → PREPARE",
                       decision=f"{why}; an official {lvl.capitalize()} warning for the district -> get ready anyway "
                                "(tentative, L11)")
        out.update({"verdict": verdict, "level_name": None,     # no band from an unusable reading
                    "triggers": triggers, "no_river": why,
                    "confidence": {"score": 0.1, "label": "low", "reasons": [why]}, "controlling": [], "upstream": [],
                    "rain": None, "history": [], "bigger_than_2014": None,
                    # B-88: the rain picture is still shown on the card as context - never a trigger here
                    "rain_upstream": None if now_only else ctx.get("rain_upstream")})
        return _finish(out, plan, world, evidence, run_id)
    fired, trends, fast = [], [], False
    for g in controlling:
        if not _usable(g):
            continue
        f, t, is_fast = _gauge_rules(g, now_only)
        fired += f
        trends.append(t)
        fast = fast or (is_fast and g is main)
    up_fired, upstream = _upstream(ctx.get("sentinels", []))
    rain_fired, rain = ([], None) if now_only else _rain(ctx.get("rain"))
    ru = None if now_only else ctx.get("rain_upstream")
    fired += up_fired + rain_fired + _rain_upstream(ru) + _met_warning(evidence)
    base = max((LEVELS.index(f[0]) for f in fired), default=0)
    triggers = [{"level": f[0], "rule": f[1], "reason": f[2]} for f in fired]
    if fast and base < len(LEVELS) - 1:
        base += 1
        triggers.append({"level": LEVELS[base], "rule": "rising-fast",
                         "reason": f"{main['name']} is rising fast (>= {RISING_FAST_M_PER_H} m/h) - one level up"})
    if ru and ru.get("combined") and base < len(LEVELS) - 1:      # B-88 (tentative): hulu + hilir -> one level up
        base += 1
        local = ru.get("local") or {}
        came = [u for u in ru["upstream"] if u["point"] in ru["arriving_24h"]]
        triggers.append({"level": LEVELS[base], "rule": "upstream+local-rain", "reason": (
            "heavy rain upstream arriving within 24 h (" + "; ".join(
                f"{u['name']}, {u['window']['min']:g}-{u['window']['max']:g} h" for u in came)
            + f") while it rains heavily here ({local.get('max_12h_mm')} mm in 12 h) - one level up")})
    ai = evidence.get("ai_minimum")          # Part 7: an AI raise the Critic's code accepted - applied last, only up
    if ai and ai.get("level") in LEVELS and LEVELS.index(ai["level"]) > base:
        base = LEVELS.index(ai["level"])
        triggers.append({"level": ai["level"], "rule": "ai-judgement", "reason": ai["reason"],
                         "texts": ai.get("texts")})
    main_trend = next(t for t in trends if t["role"] == "controlling")
    top = (main_trend["projection_m"].get("24h") or {}).get("max")
    history, bigger = _history(world, main, top, _clock(evidence) if evidence.get("replay") else None)
    out.update({"verdict": LEVELS[base], "level_name": BAND_NAMES.get(main["band"]),
                "triggers": triggers or [{"level": "NORMAL", "rule": "no-trigger",
                                          "reason": "controlling gauge below alert and no other rule fired"}],
                "confidence": _confidence(main, [g for g in controlling if g is not main], fired, ctx.get("rain"),
                                          now_only),
                "controlling": trends, "upstream": upstream, "rain": rain, "rain_upstream": ru, "history": history,
                "bigger_than_2014": bigger})
    return _finish(out, plan, world, evidence, run_id)


def _clock(evidence):
    return datetime.fromisoformat(evidence["clock"].replace("Z", "+00:00"))


def _finish(out, plan, world, evidence, run_id):
    active = ((evidence or {}).get("met_warnings") or {}).get("active") or []
    if active and out["verdict"] == "INSUFFICIENT_DATA":     # no river reading, no Buruk / Bahaya: "Can't confirm"
        trace.step(AGENT, "forecast.met_warning", input_summary=out["place"],
                   output_summary="active MetMalaysia warning: " + "; ".join(str(w.get("heading")) for w in active[:2]),
                   decision="shown on the card; no river reading and no Buruk / Bahaya warning -> stays "
                            "INSUFFICIENT_DATA (tentative, L11)", status="fallback")
    if thunderstorm(active):
        trace.step(AGENT, "forecast.thunderstorm", input_summary=out["place"],
                   output_summary="thunderstorm warning → flash-flood advice",
                   decision="no verdict change; the card adds the small-streams advice line")
    out["thunderstorm"] = thunderstorm(active)
    trace.step(AGENT, "forecast.verdict", input_summary=out["place"],
               output_summary=f"{out['verdict']} (confidence {out['confidence']['label']}, "
                              f"{out['confidence']['score']})",
               confidence=out["confidence"]["score"], target_agent="Coordinator",
               status="fallback" if out["verdict"] == "INSUFFICIENT_DATA" else "success",
               decision="; ".join(t["reason"] for t in out["triggers"]),
               details={"mode": out["mode"], "rules": RULES, "triggers": out["triggers"]})
    if world is not None and plan.get("place"):
        if out.get("history"):
            trace.step(AGENT, "world.read", input_summary="historic peaks",
                       output_summary=f"{len(out['history'])} peak(s) at the controlling gauge", source="world_model")
        at = evidence.get("clock") or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        world.assert_fact(place_id(plan["place"]["place_id"]), "forecast",
                          {k: out[k] for k in ("verdict", "mode", "confidence", "triggers", "bigger_than_2014")},
                          confidence=out["confidence"]["score"],
                          source={"kind": "agent", "at": at, "agent": AGENT, "run_id": run_id, "origin": RULES})
        trace.step(AGENT, "world.write", output_summary=f"forecast fact for {out['place']}", source="world_model",
                   decision="Verdict stored with its triggers, so later runs (and the Critic) can see it")
    return out
