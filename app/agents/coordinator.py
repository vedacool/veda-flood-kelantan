"""Coordinator (B-12): the agent that talks to the user. The plan is written by code (app/router.py: place from
the gazetteer, quick or full, language); the Coordinator drafts the answer, and Nemotron 3.5 Super VL writes only a
short explanation from the card's key facts - never from the user's question (the question is never sent to a model).

    answer = coordinator.draft(question, plan, evidence)

If Nightshift fails (down, bad JSON, SAMPLE_MODE) the answer is the card written by code, traced as 'fallback'.
The draft is checked before it is used: no number that is not in the evidence, it states the Forecast agent's verdict and no other (B-16), never empty.
The safety line is always added by code, not left to the model.
"""
import json
import re
import time
from datetime import datetime, timezone

from app import card as card_mod
from app import trace
from app.adapters import nightshift
from app.config import MYT

AGENT = "Coordinator"
QUICK_SOURCES = ["jps_levels", "mygov_forecast"]
MAX_TOKENS = 4096          # B-85: Super VL drafts used 1,025-2,735 tokens (23 Oct; Lightning needed 8000 and still ran dry)
SAFETY = {
    "en": "Not an official warning. Follow JPS / APM / police instructions. Emergency: 999, APM (Civil Defence): 991.",
    "ms": "Bukan amaran rasmi. Ikut arahan JPS / APM / polis. Kecemasan: 999, APM: 991.",
}
REVISE_NOTE = ("\nThis is a REVISION: the Critic rejected previous_explanation. Fix every item in critic_problems, "
               "follow critic_fix, keep everything else that was correct.")
VERDICT_WORDS = card_mod.VERDICT_WORDS            # EN + BM verdict words, one definition (card.py)

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


DRAFT_CAP_S = 90               # B-85 (Husaini 23 Oct): the draft never takes more than 90 s, retries included
DRAFT_FAST_FAIL_S = 10          # an NVIDIA HTTP 500 comes back in ~2.5 s -> one retry for a failure this fast ...
DRAFT_TTFB_RETRY_MIN_S = 45     # ... and one retry after Nightshift's ~45 s no-first-byte cut, only with >= 45 s left
DRAFT_MIN_TRY_S = 10            # never start a try with less than this left


def _draft_call(llm, request, feedback, budget_s):
    """The Nemotron draft call (Super VL on the deep lane), at most DRAFT_CAP_S in all. Retries (B-85, Husaini 23 Oct):
    once after a fast failure (< DRAFT_FAST_FAIL_S, e.g. NVIDIA HTTP 500), and once after Nightshift's ~45 s
    no-first-byte cut - but only while >= DRAFT_TTFB_RETRY_MIN_S of the draft's time is left, so a retry never
    pushes the draft past its cap. Otherwise the NightshiftError goes to the caller (card without an explanation)."""
    msgs = [{"role": "system", "content": DRAFT_SYSTEM + (REVISE_NOTE if feedback else "")},
            {"role": "user", "content": json.dumps(request, ensure_ascii=False)}]
    cap = DRAFT_CAP_S if budget_s is None else min(DRAFT_CAP_S, budget_s)
    start, used = time.monotonic(), set()
    while True:
        t = time.monotonic()
        try:
            return llm(nightshift.AI_LANE, msgs, agent=AGENT, json_mode=True, target_agent="Critic",
                       max_tokens=MAX_TOKENS, budget_s=cap - (t - start), max_attempts=1,
                       purpose="write the explanation")
        except nightshift.NightshiftError as e:
            took, left = time.monotonic() - t, cap - (time.monotonic() - start)
            kind = ("fast" if took < DRAFT_FAST_FAIL_S else
                    "ttfb" if nightshift.is_ttfb_cut(e) else
                    "empty" if nightshift.is_empty_response(e) else None)
            # Cowork 24 Oct: an empty response gets the ttfb rule - one retry, only with >= 45 s of the draft left
            need = DRAFT_TTFB_RETRY_MIN_S if kind in ("ttfb", "empty") else DRAFT_MIN_TRY_S
            if kind is None or kind in used or left < need:
                raise
            used.add(kind)
            why = (f"failed fast (< {DRAFT_FAST_FAIL_S} s)" if kind == "fast" else
                   f"cut by Nightshift (no first byte) and {left:.0f} s of {cap:.0f} s left" if kind == "ttfb" else
                   f"draft retry after empty response ({left:.0f} s of {cap:.0f} s left)")
            trace.step(AGENT, "draft.retry", input_summary=f"draft failed after {took:.0f} s",
                       output_summary=str(e)[:150], status="retrying", decision=f"{why} -> one more try")


def draft(question, p, evidence, forecast=None, card=None, llm=None, budget_s=None, feedback=None, previous=None,
          use_model=True, skip_reason=None, by_design=False):
    """The answer -> {'text', 'language', 'drafted_by', 'explanation', 'safety_line'}. Never raises.
    The card lines (action, verdict + JPS level, comparison, range, sources) are inserted by code; Nemotron writes
    only the explanation (B-21). The Coordinator does not check it: the Critic does (card.explanation_problem in its
    code checks + its AI review; B-14, 23 Oct). use_model=False (quick path, or no time left) -> the card alone.
    feedback = the Critic's review of `previous` (revise round). by_design: the card alone on purpose (Part 7: the AI
    raised the level, so the explanation written for the lower level is not used) - 'code', not an AI fallback."""
    llm = llm or nightshift.chat
    card = card or card_mod.build(p, evidence, forecast)
    language = p.get("question_language", "en")
    drafted_by, why, explanation = "llm", None, None
    if not use_model:
        drafted_by = "code" if p.get("effort") == "quick" or by_design else "fallback"
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
    if drafted_by == "fallback":            # B-86: the run says plainly that the AI explanation was not used
        trace.ai_fallback(AGENT, "code-only card, explanation dropped" if use_model else
                          "code-only card, AI explanation not requested", why)
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
