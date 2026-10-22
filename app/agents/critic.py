"""Critic (B-14): checks the Coordinator's draft before it reaches the user - Nemotron Super VL on lane `deep`.

    review = critic.review(question, plan, evidence, forecast, answer, world, round_no=1)
    review["decision"]   'approve' | 'reject'   (+ problems, fix instructions)

Two levels of checking (rule 7 of the agent design guide):
  1. code checks (cannot be overruled by the model): the Forecast verdict and no other, every number from the
     evidence, never advice to walk / wade / drive through water (EN + BM, negated sentences are fine), the JPS level
     name and the confidence label are given, a stale/excluded source is mentioned, every unresolved conflict is
     mentioned;
  2. Zetaris re-queries of its own (not the Data & Reconciler's views): the controlling gauge's newest RAW reading
     from veda_pg.river_levels, and the newest date in data.gov.my /flood-warning - so the stale source is caught
     by the Critic itself, not just repeated;
  then the model reviews draft + evidence + findings and may reject for anything else (unclear, misleading...).
Any code problem = reject, whatever the model says. Without Nightshift (SAMPLE_MODE before B-18, outage) the
review is code + Zetaris only, traced as 'fallback'. The loop allows at most MAX_REJECTIONS.
Reads the forecast and source status from the World Model; writes its review (and a confirmed stale source) back.
"""
import json
import re
import time
from datetime import datetime, timezone

from app import card as card_mod
from app import config, trace
from app.adapters import nightshift, zetaris
from app.agents import coordinator
from app.agents.data_agent import AGREE_M, FRESHNESS, source_id
from app.engines.world_model.veda_ingest import place_id

AGENT = "Critic"
MAX_REJECTIONS = 2
PROBLEM_TYPES = ("unsupported", "wrong_verdict", "unsafe", "missing_level_name", "missing_confidence",
                 "missing_stale_note", "missing_conflict", "conflict", "unclear", "other")
STATION_KEY = re.compile(r"^[A-Za-z0-9_]+$")
RAW_LATEST_SQL = ("SELECT station_key, level_m, observed_at FROM veda_pg.river_levels WHERE station_key = '{key}' "
                  "ORDER BY observed_at DESC")
FLOOD_NEWEST_SQL = ("SELECT MAX(s.water_level_update_datetime) AS newest "
                    "FROM veda_wx.mygov_flood LATERAL VIEW explode(data) AS s")
# Advice to go into floodwater. A sentence that also says don't / never / avoid / jangan is a warning, not advice.
UNSAFE = re.compile(r"\b(wade|wading|walk(ing)? through|driv(e|ing) through|cross(ing)? (the )?(flood|water)|"
                    r"swim|redah|meredah|harung|mengharung|lalu (jalan|kawasan)\s+(yang\s+)?(banjir|dinaiki air))",
                    re.IGNORECASE)
NEGATION = re.compile(r"\b(do not|don't|never|avoid|not safe|jangan|elak|elakkan|tidak selamat|dilarang)\b",
                      re.IGNORECASE)
CONFIDENCE_WORDS = {"high": ("high", "tinggi"), "medium": ("medium", "sederhana"), "low": ("low", "rendah")}
STALE_WORDS = ("data.gov.my", "flood-warning", "stale", "excluded", "lapuk", "usang", "dikecualikan", "diketepikan",
               "tidak dikemas kini")
CONFLICT_WORDS = ("disagree", "conflict", "berbeza", "bercanggah", "tidak sepakat")

CRITIC_SYSTEM = (
    "You are the Critic of VEDA, a flood-risk assistant for Kelantan, Malaysia. You review a draft answer before "
    "a worried resident sees it. Approve only if ALL are true: every claim is supported by the EVIDENCE; the verdict "
    "is exactly forecast.verdict; data age / stale or excluded sources and unresolved conflicts are mentioned; the "
    "advice is safe (never walk, wade or drive through water); the wording is clear for a non-expert and correct "
    "in the answer's language. Reject as 'unclear' when the draft contradicts itself (e.g. gives a reading and "
    "also says the status cannot be confirmed), shows a number a non-expert would misread (odd ranges such as "
    "'0-0 h', units missing), or has a wrong translation (e.g. rain probability called confidence). CODE_FINDINGS are problems already found by code - if there are any you must reject. "
    "ZETARIS_RECHECK is your own re-query of the source data. Reply with ONE JSON object: "
    "{\"decision\": \"approve\" or \"reject\", \"problems\": [{\"type\": one of "
    f"{list(PROBLEM_TYPES)}, \"detail\": \"...\"}}], \"fix\": \"one or two sentences telling the writer exactly "
    "what to change\"}. Output only the JSON object.")


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def code_checks(text, facts, evidence, card=None, explanation=None):
    """Deterministic problems in a draft -> [{'type', 'detail', 'by': 'code'}].
    With a card (B-21): the whole text may name only the card's verdict, and the model's explanation may only use
    numbers that are in the card; without one: the older whole-draft check against the evidence."""
    found = []
    if card is not None:
        said = {w.replace(" ", "_") for w in coordinator.VERDICT_WORDS.findall(text or "")}
        if said - {card["verdict"]}:
            found.append({"type": "wrong_verdict",
                          "detail": f"names {', '.join(sorted(said))} but the card says {card['verdict']}"})
        problem = card_mod.explanation_problem(explanation, card) if explanation else None
    else:
        problem = coordinator.draft_problem(text, facts)
    if problem:
        found.append({"type": "wrong_verdict" if "verdict" in problem else "unsupported", "detail": problem})
    for s in _sentences(text or ""):
        if UNSAFE.search(s) and not NEGATION.search(s):
            found.append({"type": "unsafe", "detail": f"advises going into water: {s.strip()[:120]!r}"})
    low = (text or "").lower()
    fc = facts.get("forecast")
    if fc and fc["verdict"] != "INSUFFICIENT_DATA":
        names = [n.lower() for n in (fc.get("jps_level_name") or {}).values() if n]
        if names and not any(n in low for n in names):
            found.append({"type": "missing_level_name", "detail": f"JPS level name not given ({' / '.join(names)})"})
        words = CONFIDENCE_WORDS.get(fc["confidence"]["label"], ())
        if not any(re.search(rf"\b{w}\b", low) for w in words):
            found.append({"type": "missing_confidence",
                          "detail": f"confidence '{fc['confidence']['label']}' not stated"})
    if (evidence.get("cross_check") or {}).get("status") == "stale" and not any(w in low for w in STALE_WORDS):
        found.append({"type": "missing_stale_note", "detail": "the excluded stale source (data.gov.my "
                                                              "/flood-warning) is not mentioned"})
    if evidence.get("replay") and "replay" not in low:      # B-70: a replay always says so
        found.append({"type": "other", "detail": "a replay answer must say REPLAY at the top"})
    if facts.get("conflicts_unresolved") and not any(w in low for w in CONFLICT_WORDS):
        found.append({"type": "missing_conflict", "detail": "an unresolved conflict between sources is not mentioned"})
    return [{**f, "by": "code"} for f in found]


def _utc(text):
    try:
        t = datetime.fromisoformat(str(text).split(".")[0].replace(" ", "T").replace("Z", ""))
    except ValueError:
        return None
    return t.replace(tzinfo=timezone.utc)


def requery(evidence, world, run_id):
    """The Critic's own Zetaris checks -> {'gauge': ..., 'flood_warning': ..., 'problems': [...]}."""
    out, problems = {}, []
    main = next((g for g in (evidence.get("context") or {}).get("gauges", []) if g["role"] == "controlling"), None)
    key = main["station"].split(":", 2)[2] if main else None
    if key and STATION_KEY.match(key):
        try:
            r = zetaris.run_sql(RAW_LATEST_SQL.format(key=key), agent=AGENT, purpose="re-check: newest raw reading",
                                limit=1)
            raw = r.records[0] if r.records else None
        except zetaris.ZetarisError as e:
            raw, out["gauge"] = None, {"status": "failed", "detail": f"re-query failed ({e.kind})"}
        if raw:
            raw_at, ev_at = _utc(raw["observed_at"]), _utc(main["observed_at"])
            same_time = raw_at and ev_at and raw_at == ev_at
            diff = abs((raw["level_m"] or 0) - (main["level_m"] or 0))
            if same_time and diff <= AGREE_M:
                status, detail = "confirmed", f"{main['name']} {raw['level_m']} m at the same time as the evidence"
            elif same_time:
                status, detail = "conflict", (f"raw table says {raw['level_m']} m, evidence says {main['level_m']} m "
                                              "for the same reading time")
                problems.append({"type": "conflict", "detail": detail, "by": "zetaris"})
            elif raw_at and ev_at and raw_at > ev_at:
                status, detail = "newer", f"a newer reading exists: {raw['level_m']} m at {raw_at.isoformat()}"
            else:
                status, detail = "unclear", "the raw reading time could not be matched"
            out["gauge"] = {"status": status, "detail": detail, "raw_level_m": raw["level_m"],
                            "raw_at": raw_at.isoformat() if raw_at else None, "query_hash": r.query_hash}
    try:
        r = zetaris.run_sql(FLOOD_NEWEST_SQL, agent=AGENT, purpose="re-check: data.gov.my /flood-warning newest date")
        newest = r.rows[0][0] if r.rows else None
        newest_dt = datetime.fromisoformat(str(newest)).replace(tzinfo=config.MYT) if newest else None
        clock = _utc((evidence.get("clock") or "").replace("T", " ")) or datetime.now(timezone.utc)
        age_min = int((clock - newest_dt).total_seconds() // 60) if newest_dt else None
        stale = age_min is None or age_min > FRESHNESS["jps_levels"][1]
        out["flood_warning"] = {"newest": str(newest), "age_days": age_min // 1440 if age_min else None,
                                "stale": stale, "query_hash": r.query_hash}
        excluded = (evidence.get("cross_check") or {}).get("status") == "stale"
        if stale and not excluded:
            problems.append({"type": "conflict", "by": "zetaris",
                             "detail": "data.gov.my /flood-warning is stale but the evidence did not exclude it"})
        if stale and world is not None:
            world.assert_fact(source_id("mygov_flood"), "stale_confirmed",
                              {"newest_reading": str(newest), "age_days": out["flood_warning"]["age_days"]},
                              confidence=1.0, source={"kind": "zetaris", "at": evidence.get("clock") or
                                                      clock.isoformat(), "sql": r.sql, "query_hash": r.query_hash,
                                                      "agent": AGENT, "run_id": run_id, "origin": "Critic re-query"})
    except zetaris.ZetarisError as e:
        out["flood_warning"] = {"status": "failed", "detail": f"re-query failed ({e.kind})"}
    trace.step(AGENT, "critic.requery", input_summary="own Zetaris checks",
               output_summary=f"gauge: {(out.get('gauge') or {}).get('status', 'n/a')}; flood-warning stale: "
                              f"{(out.get('flood_warning') or {}).get('stale')} "
                              f"({(out.get('flood_warning') or {}).get('age_days')} days)",
               status="success" if not problems else "needs_revision", source="zetaris",
               decision="; ".join(p["detail"] for p in problems) or "re-query agrees with the evidence",
               details=out)
    return {**out, "problems": problems}


SMALL_EVIDENCE_NOTE = ("Every line of the draft except the explanation was written by code from verified data "
                       "(checked against the evidence by code). The card as written by code: ")


def _model_review(question, answer, facts, findings, recheck, llm, budget_s):
    """The deep-lane review -> (decision, problems, fix) or raises NightshiftError.
    With a card (B-21) the model gets the SMALL input: the card text instead of the whole evidence - measured 22 Oct
    night: full input 0/3 (cut at 45 s), small input 3/3 when streamed. The code checks already hold every card
    line to the evidence; the model judges the explanation, clarity and safety."""
    card = answer.get("card")
    evidence = (SMALL_EVIDENCE_NOTE + card_mod.render(card, answer.get("language") or "en")) if card else facts
    r = llm("deep", [{"role": "system", "content": CRITIC_SYSTEM},
                     {"role": "user", "content": json.dumps({
                         "question": question, "language": answer.get("language"), "draft": answer["text"],
                         "EVIDENCE": evidence, "CODE_FINDINGS": findings,
                         "ZETARIS_RECHECK": {k: v for k, v in recheck.items() if k != "problems"}},
                         ensure_ascii=False, default=str)}],
            agent=AGENT, json_mode=True, thinking=False, target_agent="Coordinator", max_tokens=3000,
            budget_s=budget_s, max_attempts=1)
    data = r.data if isinstance(r.data, dict) else {}
    decision = data.get("decision") if data.get("decision") in ("approve", "reject") else "reject"
    problems = [{"type": p.get("type") if p.get("type") in PROBLEM_TYPES else "other",
                 "detail": str(p.get("detail") or "")[:300], "by": "model"}
                for p in (data.get("problems") or []) if isinstance(p, dict)]
    if decision == "reject" and not problems:
        problems = [{"type": "other", "detail": "model rejected without a usable reason", "by": "model"}]
    return decision, problems, str(data.get("fix") or "")[:500]


def review(question, plan, evidence, forecast, answer, world=None, round_no=1, llm=None, budget_s=None,
           use_model=True, recheck_data=True, skip_reason=None):
    """Approve or reject one draft. Returns {decision, problems, fix, round, checked_by, recheck}. Never raises.
    use_model / recheck_data = False (quick path, or no time left - B-17): code checks only, reason in the trace."""
    llm = llm or nightshift.chat
    t_start = time.monotonic()
    run = trace.current_run()
    run_id = run.run_id if run else None
    facts = coordinator.facts_for_model(evidence, forecast)
    if world is not None and plan.get("place"):           # read back what the Forecast agent stored
        stored = world.facts_about(place_id(plan["place"]["place_id"]), "forecast")
        trace.step(AGENT, "world.read", input_summary="the Forecast agent's stored verdict",
                   output_summary=f"stored verdict {stored[-1]['value']['verdict'] if stored else 'none'}",
                   source="world_model")
    findings = code_checks(answer["text"], facts, evidence, answer.get("card"), answer.get("explanation"))
    trace.step(AGENT, "critic.code_checks", input_summary=f"draft round {round_no}",
               output_summary=f"{len(findings)} problem(s)", source="code",
               status="needs_revision" if findings else "success",
               decision="; ".join(f"{f['type']}: {f['detail']}" for f in findings) or "all code checks pass")
    checked_by, status_note = ["code"], None
    if not recheck_data:
        recheck = {"problems": [], "note": skip_reason or "re-query skipped"}
    elif round_no == 1:
        recheck = requery(evidence, world, run_id)
        checked_by.append("zetaris")
    else:
        recheck = {"problems": [], "note": "re-query done in round 1"}
    code_problems = findings + recheck["problems"]
    if not use_model:
        decision, model_problems, fix = ("reject" if code_problems else "approve"), [], ""
        status_note = skip_reason or "model review skipped"
    else:
        try:
            remaining = None if budget_s is None else max(1.0, budget_s - (time.monotonic() - t_start))
            decision, model_problems, fix = _model_review(question, answer, facts, code_problems, recheck, llm,
                                                          remaining)          # the re-query time is already used
            checked_by.append("model")
        except nightshift.NightshiftError as e:
            decision, model_problems, fix = ("reject" if code_problems else "approve"), [], ""
            status_note = f"Nightshift unavailable ({e}) -> review by code + Zetaris only"
    if code_problems and decision == "approve":
        decision = "reject"
        status_note = (status_note + "; " if status_note else "") + "model approved, but code checks found problems"
    problems = code_problems + model_problems
    if decision == "reject" and not fix:
        fix = "; ".join(p["detail"] for p in problems[:4])
    result = {"decision": decision, "problems": problems, "fix": fix, "round": round_no, "checked_by": checked_by,
              "recheck": {k: v for k, v in recheck.items() if k != "problems"}}
    trace.step(AGENT, "critic.review", input_summary=f"draft round {round_no} ({answer.get('drafted_by')})",
               output_summary=f"{decision}: {len(problems)} problem(s)" + (f" - fix: {fix}" if fix else ""),
               status="approved" if decision == "approve" else "needs_revision", target_agent="Coordinator",
               decision=status_note or ("; ".join(f"{p['type']}: {p['detail']}" for p in problems[:4])
                                        or "evidence supports the draft"),
               details={"problems": problems, "checked_by": checked_by, "round": round_no})
    if world is not None and plan.get("place"):
        at = evidence.get("clock") or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        world.assert_fact(place_id(plan["place"]["place_id"]), "critic_review",
                          {"round": round_no, "decision": decision, "problems": sorted({p["type"] for p in problems})},
                          confidence=1.0, source={"kind": "agent", "at": at, "agent": AGENT, "run_id": run_id,
                                                  "origin": "Critic review"})
        trace.step(AGENT, "world.write", output_summary=f"review round {round_no}: {decision}", source="world_model")
    return result
