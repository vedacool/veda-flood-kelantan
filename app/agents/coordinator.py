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
import time
from datetime import datetime, timezone

from app import card as card_mod
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
MAX_TOKENS = 8000          # Husaini 23 Oct: 4000 -> 0/6 live (empty), 8000 -> 4/5 in ~40-54 s; no retry
SAFETY = {
    "en": "Not an official warning. Follow JPS / APM / police instructions. Emergency: 999, APM (Civil Defence): 991.",
    "ms": "Bukan amaran rasmi. Ikut arahan JPS / APM / polis. Kecemasan: 999, APM: 991.",
}
REVISE_NOTE = ("\nThis is a REVISION: the Critic rejected previous_explanation. Fix every item in critic_problems, "
               "follow critic_fix, keep everything else that was correct.")
VERDICT_WORDS = card_mod.VERDICT_WORDS            # EN + BM verdict words, one definition (card.py)

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
    "You are the Coordinator of VEDA, a flood-risk assistant for Kelantan, Malaysia. VEDA already shows the user a "
    "card with the action to take, the verdict, the river level, the range, the confidence, the sources and the "
    "disclaimer - all written by code; FACTS are its key facts, already in the user's language. Your job: write "
    "ONLY a short explanation (1-2 sentences, max 30 words, under 200 characters) of WHY the verdict is what it is, "
    "for this user, from FACTS. Rules:\n"
    "1. Use only numbers that appear in FACTS (no other numbers at all).\n"
    "2. Do not repeat the action, the verdict line, the sources or the disclaimer.\n"
    "3. Do not name the verdict at all (no NORMAL, WATCH, PREPARE, ACT, BERJAGA-JAGA, BERSEDIA, BERTINDAK) - "
    "the card already shows it.\n"
    "4. Never advise walking, wading or driving through floodwater.\n"
    "5. For family_far_away users, say what they can do from afar (call, check on them).\n"
    "6. Write in `language`: ms = standard Malaysian Bahasa Melayu (never Indonesian words such as alarm, aturan, "
    "kondisi, terpicu, telepon), using the JPS level names in FACTS (Waspada, Amaran, Bahaya); en = plain English.\n"
    "7. No minus signs, no internal terms (rule, trigger, verdict, sentinel, gauge codes).\n"
    "8. Say nothing about the river rising or falling unless FACTS has a trend.\n"
    "9. Say the 24 h range in words, e.g. 'mungkin naik ke 8.65-8.72 m dalam 24 jam' / 'may rise to 8.65-8.72 m in "
    "the next 24 h'.\n"
    "STYLE EXAMPLES - style only, never copy the place or the numbers (Tanah Merah is not the user's place):\n"
    "ms NORMAL: Paras air di Tanah Merah 5.20 m, masih 1.30 m di bawah paras Waspada dan sedang turun. Buat masa ini "
    "tiada tanda banjir.\n"
    "ms PREPARE: Paras air di Tanah Merah 7.10 m sudah melepasi paras Amaran, dan sungai di hulu sudah di paras "
    "Bahaya. Air dijangka terus naik dalam beberapa jam.\n"
    "ms ACT: Paras air di Tanah Merah 9.80 m, 0.80 m di atas paras Bahaya dan masih naik, lebih tinggi daripada "
    "banjir 2014.\n"
    "en NORMAL: The river at Tanah Merah is 5.20 m, still 1.30 m below the Alert level and falling. For now there is "
    "no sign of flooding.\n"
    "en ACT: The river at Tanah Merah is 9.80 m, 0.80 m above the Danger level and still rising, higher than the "
    "2014 flood.\n"
    "Reply with ONE JSON object: {\"explanation\": \"...\"}.")


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


def _validate(question, raw, fixes, resolved=None):
    """Model output -> a plan VEDA can execute. Every correction is appended to `fixes`.
    resolved = the place the code already found (B-17 routing) - then the model's place_text is not used."""
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
    res = resolved or _resolve_place(question, place_text.strip(), fixes)
    return {
        "question_language": _choose(raw.get("language"), LANGUAGES, "en", "language", fixes),
        "intent": _choose(raw.get("intent"), INTENTS, "risk_check", "intent", fixes),
        "user_type": _choose(raw.get("user_type"), USER_TYPES, "unknown", "user_type", fixes),
        "effort": effort, "sources": sources,
        "place": res.place, "place_status": res.status, "place_message": res.message,
        "reason": str(raw.get("reason") or "")[:300],
    }


def plan(question, world=None, llm=None, budget_s=None, resolved=None, effort=None, language=None):
    """Plan for one question. llm(lane, messages, agent=..., json_mode=..., ...) -> LLMResult (default: Nightshift).
    resolved / effort / language: already decided by code (B-17 router) - the model cannot change them; any
    difference is listed in the trace's fixes."""
    llm = llm or nightshift.chat
    fixes, planned_by, why = [], "llm", None
    try:
        r = llm("fast", [{"role": "system", "content": PLAN_SYSTEM}, {"role": "user", "content": question}],
                agent=AGENT, json_mode=True, target_agent="Data & Reconciler", max_tokens=MAX_TOKENS, budget_s=budget_s)
        raw = r.data
    except nightshift.NightshiftError as e:
        raw, planned_by, why = {}, "fallback", f"Nightshift unavailable ({e}) -> plan written by code"
    p = _validate(question, raw, fixes if planned_by == "llm" else [], resolved)
    p["planned_by"] = planned_by
    for key, value in (("effort", effort), ("question_language", language)):
        if value and p[key] != value:
            if planned_by == "llm":
                fixes.append(f"{key} {p[key]} -> {value} (decided by code)")
            p[key] = value
    if effort == "full" and planned_by == "llm" and len(p["sources"]) < 2:
        p["sources"] = list(SOURCES)
        fixes.append("full path -> every source")
    if planned_by == "fallback":
        p["reason"] = "Fallback plan: full effort, every source."
    trace.step(AGENT, "plan", input_summary=question,
               output_summary=(f"intent={p['intent']} user={p['user_type']} place={(p['place'] or {}).get('name')} "
                               f"({p['place_status']}) effort={p['effort']} sources={','.join(p['sources'])}"),
               status="success" if planned_by == "llm" else "fallback", target_agent="Data & Reconciler",
               decision=why or ("; ".join(fixes) if fixes else p["reason"]), details={"plan": p, "fixes": fixes})
    if world is not None and run_id():
        remember(world, p)
    return p


def run_id():
    run = trace.current_run()
    return run.run_id if run else None


def remember(world, p):
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
            "projection_m": (main or {}).get("projection_m"),
            "hours_to": {k: v for k, v in ((main or {}).get("hours_to") or {}).items() if v["earliest"] > 0},
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
    said = card_mod.verdict_codes(text)
    if said - {allowed}:
        return (f"gives a verdict ({', '.join(sorted(said))}) that is not the Forecast agent's ({allowed})" if allowed
                else f"gives a verdict ({', '.join(sorted(said))}) without a forecast")
    if allowed and allowed not in said:
        return f"does not state the Forecast agent's verdict ({allowed})"
    unknown = [n for n in re.findall(r"\d+\.\d+", text) if n not in _numbers(facts)]
    if unknown:
        return f"number(s) not in the evidence: {', '.join(unknown[:3])}"
    return None


DRAFT_TRIES = 1                 # Husaini 23 Oct (later): at 8000 tokens a draft takes ~50 s - no retry
DRAFT_FAST_FAIL_S = 15          # (kept for DRAFT_TRIES > 1: retry only a failure this fast ...)
DRAFT_RETRY_MIN_LEFT_S = 70     # ... and the wording rewrite only with this much budget left (draft ~50 s + Critic)


def _draft_call(llm, request, feedback, budget_s):
    """One Nemotron draft call, retried once on a fast failure (an empty reply or error within DRAFT_FAST_FAIL_S)
    when enough budget is left; otherwise the NightshiftError goes to the caller (card without an explanation)."""
    msgs = [{"role": "system", "content": DRAFT_SYSTEM + (REVISE_NOTE if feedback else "")},
            {"role": "user", "content": json.dumps(request, ensure_ascii=False)}]
    start = time.monotonic()
    for attempt in range(1, DRAFT_TRIES + 1):
        t = time.monotonic()
        left = None if budget_s is None else budget_s - (t - start)
        try:
            return llm("fast", msgs, agent=AGENT, json_mode=True, target_agent="Critic", max_tokens=MAX_TOKENS,
                       budget_s=left, max_attempts=1)
        except nightshift.NightshiftError as e:
            took = time.monotonic() - t
            room = budget_s is None or budget_s - (time.monotonic() - start) >= DRAFT_RETRY_MIN_LEFT_S
            if attempt == DRAFT_TRIES or took >= DRAFT_FAST_FAIL_S or not room:
                raise
            trace.step(AGENT, "draft.retry", input_summary=f"draft failed after {took:.0f} s",
                       output_summary=str(e)[:150], status="retrying",
                       decision=f"failed fast (< {DRAFT_FAST_FAIL_S} s) and enough time left -> one more try")


def draft(question, p, evidence, forecast=None, card=None, llm=None, budget_s=None, feedback=None, previous=None,
          use_model=True, skip_reason=None):
    """The answer -> {'text', 'language', 'drafted_by', 'explanation', 'safety_line'}. Never raises.
    The card lines (action, verdict + JPS level, comparison, range, sources) are inserted by code; Nemotron writes
    only the explanation (B-21), which must pass card.explanation_problem. use_model=False (quick path, or no time
    left) -> the card alone. feedback = the Critic's review of `previous` (revise round)."""
    llm = llm or nightshift.chat
    card = card or card_mod.build(p, evidence, forecast)
    language = p.get("question_language", "en")
    drafted_by, why, explanation = "llm", None, None
    if not use_model:
        drafted_by = "code" if p.get("effort") == "quick" else "fallback"
        why = (skip_reason or "model not used") + " -> card written by code"
    else:
        # Husaini 23 Oct: the card's key facts only (no card text, no question - user_type carries who is asking)
        # facts as words in the answer's language - no rule names, no signed numbers (Husaini 23 Oct)
        request = {"language": language, "intent": p["intent"], "user_type": p["user_type"],
                   "FACTS": card_mod.key_facts(card, forecast, language)}
        if feedback:                # revise after a Critic rejection: the previous explanation + what to fix
            request["previous_explanation"] = (previous or {}).get("explanation")
            request["critic_problems"] = [f"{x['type']}: {x['detail']}" for x in feedback.get("problems", [])]
            request["critic_fix"] = feedback.get("fix")
        try:
            # Husaini 23 Oct (B-14): the Coordinator only drafts - every check on the explanation (numbers, verdict,
            # wording, trend, safety) is the Critic's, so a bad draft shows as reject -> rewrite -> re-check
            r = _draft_call(llm, request, feedback, budget_s)
            explanation = (r.data or {}).get("explanation") if isinstance(r.data, dict) else None
            if not isinstance(explanation, str) or not explanation.strip():
                drafted_by, why, explanation = "fallback", "the model's reply had no explanation -> card without it", None
            else:
                explanation = explanation.strip()
        except nightshift.NightshiftError as e:
            drafted_by, why = "fallback", f"Nightshift unavailable ({e}) -> card without an explanation"
    answer = {"text": card_mod.render(card, language, explanation), "language": language, "drafted_by": drafted_by,
              "explanation": explanation, "card": card, "safety_line": SAFETY.get(language, SAFETY["en"])}
    trace.step(AGENT, "revise" if feedback else "draft", input_summary=question, output_summary=answer["text"],
               status="success" if drafted_by in ("llm", "code") else "fallback", target_agent="Critic",
               decision=why or f"Card + explanation in {language}, verdict {card['verdict']}",
               details={"drafted_by": drafted_by, "revision": bool(feedback), "explanation": explanation})
    return answer


def template_answer(card, language, why):
    """The card alone (no AI explanation), in the user's language - used when the AI Critic could not check the
    explanation (Husaini 22 Oct night). The reason is traced."""
    answer = {"text": card_mod.render(card, language), "language": language, "drafted_by": "code",
              "explanation": None, "card": card, "safety_line": SAFETY.get(language, SAFETY["en"])}
    trace.step(AGENT, "final_answer", output_summary=answer["text"], status="fallback",
               decision=f"AI explanation dropped: {why} -> template answer only")
    return answer


def low_confidence_answer(evidence, forecast, review, card=None, language="en", plan=None):
    """After the Critic's last rejection: the card alone, labelled low confidence, in the user's language. Built by
    code only, so it passes the code checks by construction."""
    card = card or card_mod.build(plan or {}, evidence, forecast)
    text = card_mod.render(card, language, low_confidence=True)
    answer = {"text": text, "language": language, "drafted_by": "fallback", "low_confidence": True,
              "explanation": None, "card": card, "safety_line": SAFETY.get(language, SAFETY["en"])}
    kinds = ", ".join(sorted({x["type"] for x in review.get("problems", [])}))
    trace.step(AGENT, "final_answer", output_summary=text, status="fallback",
               decision=f"Critic rejected {review.get('round')} time(s) ({kinds}) -> card only, low confidence")
    return answer
