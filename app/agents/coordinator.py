"""Coordinator (B-12): the agent that talks to the user - Nemotron on Nightshift lane `fast`.

    plan = coordinator.plan(question, world)            what is asked, about which place, by whom, what to fetch
    answer = coordinator.draft(question, plan, evidence)

The model proposes, code decides: the place always comes from the gazetteer (never from the model), and every
field is checked against the allowed values below - anything else is corrected and the correction is traced.
If Nightshift fails (down, bad JSON, SAMPLE_MODE before B-18) the Coordinator falls back to a plan / answer
written by code from the same evidence, traced as 'fallback'. The draft is checked before it is used: no number
that is not in the evidence, it states the Forecast agent's verdict and no other (B-16), never empty.
The safety line is always added by code, not left to the model.
"""
import json
import re
from datetime import datetime, timezone

from app import gazetteer, trace
from app.adapters import nightshift
from app.agents.data_agent import SOURCES
from app.config import MYT

AGENT = "Coordinator"
INTENTS = ("risk_check", "evacuation", "cut_off", "other")
USER_TYPES = ("resident", "family_far_away", "school", "unknown")
EFFORTS = ("quick", "full")
LANGUAGES = ("en", "ms")
QUICK_SOURCES = ["jps_levels", "mygov_forecast"]
SAFETY = {
    "en": "Not an official warning. Follow JPS / APM / police instructions. Emergency: 999, APM (Civil Defence): 991.",
    "ms": "Bukan amaran rasmi. Ikut arahan JPS / APM / polis. Kecemasan: 999, APM: 991.",
}
VERDICT_WORDS = re.compile(r"\b(NORMAL|WATCH|PREPARE|ACT|INSUFFICIENT[ _]DATA)\b")

PLAN_SYSTEM = (
    "You are the Coordinator of VEDA, a flood-risk assistant for Kelantan, Malaysia. Read the user's question and "
    "reply with ONE JSON object with these keys:\n"
    f"intent: one of {list(INTENTS)} (risk_check = is my area at risk / what is the river doing; evacuation = should "
    "we move / where to go; cut_off = will roads or the area be cut off; other = anything else)\n"
    f"user_type: one of {list(USER_TYPES)} (family_far_away = asking about relatives in another place)\n"
    "place_text: the place name exactly as the user wrote it, or \"\" if none\n"
    f"sources: list from {list(SOURCES)} - jps_levels = river gauges, open_meteo = rain forecast, "
    "mygov_forecast = MetMalaysia town forecast, mygov_warning = MetMalaysia warnings\n"
    f"effort: one of {list(EFFORTS)} (quick = a simple status question; full = anything about the coming hours/days, "
    "moving people, or safety)\n"
    f"language: one of {list(LANGUAGES)} - the language of the question\n"
    "reason: one short sentence explaining the plan.\nOutput only the JSON object.")

DRAFT_SYSTEM = (
    "You are the Coordinator of VEDA, a flood-risk assistant for Kelantan, Malaysia. Write the answer to the user "
    "from the EVIDENCE only. Rules:\n"
    "1. Use only numbers and facts that appear in the evidence. Say the reading time (MYT) for river levels.\n"
    "2. Lead with what matters for the user's question, in plain words, max 120 words.\n"
    "3. The verdict is decided by the Forecast agent: state forecast.verdict exactly as written (NORMAL, WATCH, "
    "PREPARE, ACT or INSUFFICIENT_DATA) with the JPS level name, the projected range and the confidence label. Never "
    "give a different verdict. If there is no forecast, give no verdict.\n"
    "4. If usable is false, say clearly that the current river status cannot be confirmed, and why.\n"
    "5. Mention stale or excluded sources in one short clause if the evidence notes them, and every item in "
    "conflicts_unresolved (say the sources disagree and VEDA did not pick one).\n"
    "6. Never advise walking, wading or driving through floodwater.\n"
    "7. Write in the language given by `language` (en = English, ms = Bahasa Melayu).\n"
    "Reply with ONE JSON object: {\"answer\": \"...\"}. Do not add the official-warning disclaimer; VEDA adds it.")


def _choose(value, allowed, default, field, fixes):
    if value in allowed:
        return value
    fixes.append(f"{field} {value!r} not allowed -> {default}")
    return default


def _resolve_place(question, place_text, fixes):
    """The gazetteer decides the place: first what the model extracted, then the whole question."""
    first = gazetteer.resolve(place_text, agent=AGENT) if place_text else None
    if first and first.status == "found":
        return first
    whole = gazetteer.resolve(question, agent=AGENT)
    if first is None:
        return whole
    if whole.status == "found":
        fixes.append(f"place_text {place_text!r} not covered -> {whole.place['name']} found in the question")
        return whole
    return first            # keep the "Did you mean...?" / not-covered reply for the name the user gave


def _validate(question, raw, fixes):
    """Model output -> a plan VEDA can execute. Every correction is appended to `fixes`."""
    raw = raw if isinstance(raw, dict) else {}
    effort = _choose(raw.get("effort"), EFFORTS, "full", "effort", fixes)
    asked = raw.get("sources") if isinstance(raw.get("sources"), list) else []
    sources = [s for s in dict.fromkeys(asked) if s in SOURCES]
    if len(sources) != len(asked):
        fixes.append(f"dropped unknown source(s): {sorted(set(map(str, asked)) - set(sources))}")
    if not sources:
        sources = list(QUICK_SOURCES if effort == "quick" else SOURCES)
        fixes.append(f"no sources -> default for {effort} effort")
    if "jps_levels" not in sources:
        sources.insert(0, "jps_levels")
        fixes.append("added jps_levels: every flood answer needs the river gauges")
    place_text = raw.get("place_text") if isinstance(raw.get("place_text"), str) else ""
    res = _resolve_place(question, place_text.strip(), fixes)
    return {
        "question_language": _choose(raw.get("language"), LANGUAGES, "en", "language", fixes),
        "intent": _choose(raw.get("intent"), INTENTS, "risk_check", "intent", fixes),
        "user_type": _choose(raw.get("user_type"), USER_TYPES, "unknown", "user_type", fixes),
        "effort": effort, "sources": sources,
        "place": res.place, "place_status": res.status, "place_message": res.message,
        "reason": str(raw.get("reason") or "")[:300],
    }


def plan(question, world=None, llm=None, budget_s=None):
    """Plan for one question. llm(lane, messages, agent=..., json_mode=..., ...) -> LLMResult (default: Nightshift)."""
    llm = llm or nightshift.chat
    fixes, planned_by, why = [], "llm", None
    try:
        r = llm("fast", [{"role": "system", "content": PLAN_SYSTEM}, {"role": "user", "content": question}],
                agent=AGENT, json_mode=True, target_agent="Data & Reconciler", max_tokens=2000, budget_s=budget_s)
        raw = r.data
    except nightshift.NightshiftError as e:
        raw, planned_by, why = {}, "fallback", f"Nightshift unavailable ({e}) -> plan written by code"
    p = _validate(question, raw, fixes if planned_by == "llm" else [])
    p["planned_by"] = planned_by
    if planned_by == "fallback":
        p["reason"] = "Fallback plan: full effort, every source."
    trace.step(AGENT, "plan", input_summary=question,
               output_summary=(f"intent={p['intent']} user={p['user_type']} place={(p['place'] or {}).get('name')} "
                               f"({p['place_status']}) effort={p['effort']} sources={','.join(p['sources'])}"),
               status="success" if planned_by == "llm" else "fallback", target_agent="Data & Reconciler",
               decision=why or ("; ".join(fixes) if fixes else p["reason"]), details={"plan": p, "fixes": fixes})
    if world is not None and run_id():
        _remember(world, p)
    return p


def run_id():
    run = trace.current_run()
    return run.run_id if run else None


def _remember(world, p):
    """Question radar in the World Model: intent tags only, never the question text (no personal data)."""
    at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    world.upsert_context("run", external_key={"system": "veda", "id": run_id()}, attrs={
        "intent": p["intent"], "user_type": p["user_type"], "effort": p["effort"], "planned_by": p["planned_by"],
        "place": (p["place"] or {}).get("place_id"), "place_status": p["place_status"]},
        source={"kind": "agent", "at": at, "agent": AGENT, "run_id": run_id(), "origin": "Coordinator plan"})
    trace.step(AGENT, "world.write", output_summary=f"run context {run_id()} (intent tags only)",
               source="world_model", decision="Question radar: the plan's tags, no personal data")


# -- draft --------------------------------------------------------------------------------------------------------
def _myt(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(MYT).strftime("%d %b %H:%M MYT")
    except ValueError:
        return None


def _forecast_facts(fc):
    """The Forecast agent's result, compact."""
    if not fc:
        return None
    main = next((c for c in fc.get("controlling", []) if c["role"] == "controlling"), None)
    return {"verdict": fc["verdict"], "jps_level_name": fc.get("level_name"),
            "confidence": {"label": fc["confidence"]["label"], "score": fc["confidence"]["score"]},
            "why": [t["reason"] for t in fc["triggers"]], "mode": fc["mode"],
            "projection_m": (main or {}).get("projection_m"), "hours_to": (main or {}).get("hours_to"),
            "upstream": [u for u in fc.get("upstream", []) if u.get("rising") or u.get("band") in
                         ("alert", "warning", "danger")],
            "history": fc.get("history"), "bigger_than_2014": fc.get("bigger_than_2014")}


def facts_for_model(evidence, forecast=None):
    """The compact evidence the model sees (no SQL, no provenance noise) - also what the number check uses."""
    ctx = evidence.get("context") or {}
    gauges = []
    for g in ctx.get("gauges", []) + ctx.get("sentinels", []):
        item = {"gauge": g["name"], "role": g["role"], "level_m": g["level_m"], "band": g["band"],
                "read_at": _myt(g["observed_at"]) if g["observed_at"] else None, "age_minutes": g["age_minutes"],
                "freshness": g.get("freshness"), "change_1h_m": g.get("change_1h_m"),
                "change_3h_m": g.get("change_3h_m"),
                "thresholds_m": {k.replace("_m", ""): v for k, v in g["thresholds"].items() if v is not None},
                "checks_ok": (g.get("health") or {"ok": True})["ok"]}
        if g.get("travel_time_h"):
            item["travel_time_h"] = {"min": g["travel_time_h"]["min"], "max": g["travel_time_h"]["max"],
                                     "status": g["travel_time_h"]["status"]}
        gauges.append(item)
    rain = ctx.get("rain")
    met = ctx.get("met_forecast")
    return {
        "place": (evidence.get("place") or {}).get("name"), "usable": evidence.get("usable"), "gauges": gauges,
        "rain": None if not rain else {k: rain.get(k) for k in ("rain_past_24h_mm", "rain_next_24h_mm",
                                                                "rain_next_72h_mm", "max_prob_next_24h_pct",
                                                                "freshness")},
        "met_forecast_today": None if not met else {"summary": met.get("summary"), "when": met.get("when")},
        "source_notes": evidence.get("notes", []),
        "conflicts_unresolved": [{"quantity": c["quantity"], "reason": c["reason"]}
                                 for c in evidence.get("conflicts_unresolved", [])],
        "forecast": _forecast_facts(forecast),
    }


def _numbers(obj):
    """Every number in the evidence, in the forms an answer might write it."""
    out = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out.update({f"{v}", f"{v:.1f}", f"{v:.2f}", f"{abs(v)}", f"{abs(v):.1f}", f"{abs(v):.2f}"})
        elif isinstance(v, str):
            out.update(re.findall(r"\d+(?:\.\d+)?", v))
    walk(obj)
    return out


def draft_problem(text, facts):
    """None if the draft may be used, else why not (cheap guard until the Critic, B-14)."""
    if not isinstance(text, str) or not text.strip():
        return "empty answer"
    allowed = (facts.get("forecast") or {}).get("verdict")
    said = {w.replace(" ", "_") for w in VERDICT_WORDS.findall(text)}
    if said - {allowed}:
        return (f"gives a verdict ({', '.join(sorted(said))}) that is not the Forecast agent's ({allowed})" if allowed
                else f"gives a verdict ({', '.join(sorted(said))}) without a forecast")
    if allowed and allowed not in said:
        return f"does not state the Forecast agent's verdict ({allowed})"
    unknown = [n for n in re.findall(r"\d+\.\d+", text) if n not in _numbers(facts)]
    if unknown:
        return f"number(s) not in the evidence: {', '.join(unknown[:3])}"
    return None


def fallback_answer(facts):
    """An answer written by code from the same facts (used when the model is unavailable or its draft fails).
    English only for now."""
    place = facts.get("place") or "this place"
    lines = []
    fc = facts.get("forecast")
    if fc:
        name = (fc.get("jps_level_name") or {}).get("en")
        lines.append(f"{place}: {fc['verdict']}" + (f" (JPS level: {name})" if name else "")
                     + f", confidence {fc['confidence']['label']}. Why: {'; '.join(fc['why'][:3])}.")
        rng = (fc.get("projection_m") or {}).get("24h")
        if rng:
            lines.append(f"Projected level in 24 h: {rng['min']}-{rng['max']} m (straight-line trend).")
    if not facts.get("usable"):
        lines.append(f"The current river status for {place} cannot be confirmed: the controlling gauge has no "
                     "fresh, healthy reading.")
    for g in facts["gauges"]:
        if g["role"] in ("controlling", "controlling_secondary") and g["level_m"] is not None:
            th = ", ".join(f"{k} {v} m" for k, v in g["thresholds_m"].items())
            lines.append(f"{g['gauge']}: {g['level_m']} m at {g['read_at']} ({g['age_minutes']} min ago), "
                         f"band '{g['band']}'" + (f" (thresholds: {th})" if th else "") + ".")
    ups = [g for g in facts["gauges"] if g["role"] == "sentinel" and g["level_m"] is not None]
    if ups:
        lines.append("Upstream: " + "; ".join(
            f"{g['gauge']} {g['level_m']} m ({g['band']}, {g['read_at']})"
            + (f", reported travel time {g['travel_time_h']['min']}-{g['travel_time_h']['max']} h"
               if g.get("travel_time_h") and g["travel_time_h"]["min"] is not None else "") for g in ups) + ".")
    if facts.get("rain"):
        r = facts["rain"]
        lines.append(f"Rain (Open-Meteo): past 24 h {r['rain_past_24h_mm']} mm, next 24 h {r['rain_next_24h_mm']} mm, "
                     f"next 72 h {r['rain_next_72h_mm']} mm.")
    if facts.get("met_forecast_today"):
        m = facts["met_forecast_today"]
        lines.append(f"MetMalaysia today: {m['summary']}" + (f" ({m['when']})" if m.get("when") else "") + ".")
    lines += facts.get("source_notes", [])[:3]
    for c in facts.get("conflicts_unresolved", []):
        lines.append(f"Sources disagree on {c['quantity']} and VEDA did not pick one ({c['reason']}).")
    if fc and fc.get("history"):
        h = fc["history"][0]
        lines.append(f"Highest recorded here: {h['peak_m']} m ({h['event']}), {h['above_now_m']} m above now.")
    if not fc:
        lines.append("No flood outlook was made for this answer.")
    return " ".join(lines)


def draft(question, p, evidence, forecast=None, llm=None, budget_s=None):
    """Answer for the user -> {'text', 'language', 'drafted_by', 'safety_line'}. Never raises."""
    llm = llm or nightshift.chat
    facts = facts_for_model(evidence, forecast)
    language = p.get("question_language", "en")
    drafted_by, why, text = "llm", None, None
    try:
        r = llm("fast", [{"role": "system", "content": DRAFT_SYSTEM},
                         {"role": "user", "content": json.dumps({"question": question, "language": language,
                                                                 "intent": p["intent"], "user_type": p["user_type"],
                                                                 "evidence": facts}, ensure_ascii=False)}],
                agent=AGENT, json_mode=True, target_agent="Critic", max_tokens=2000, budget_s=budget_s)
        text = (r.data or {}).get("answer") if isinstance(r.data, dict) else None
        problem = draft_problem(text, facts)
        if problem:
            drafted_by, why = "fallback", f"Model draft rejected by code check: {problem} -> code-written answer"
    except nightshift.NightshiftError as e:
        drafted_by, why = "fallback", f"Nightshift unavailable ({e}) -> code-written answer"
    if drafted_by == "fallback":
        text, language = fallback_answer(facts), "en"
    answer = {"text": text.strip(), "language": language, "drafted_by": drafted_by,
              "safety_line": SAFETY.get(language, SAFETY["en"])}
    trace.step(AGENT, "draft", input_summary=question, output_summary=answer["text"],
               status="success" if drafted_by == "llm" else "fallback", target_agent="Critic",
               decision=why or (f"Drafted from {len(facts['gauges'])} gauge(s), usable={facts['usable']}, "
                                f"verdict={(facts['forecast'] or {}).get('verdict', 'none')}"),
               details={"drafted_by": drafted_by})
    return answer
