"""The agent loop: a plain Python state machine (decided 22 Oct - no LangGraph, so every step is readable).

    result = loop.run("Is Rantau Panjang at risk?")

    plan -> gather -> forecast -> draft -> critique -> (revise -> critique) -> done

plan      Code first: the gazetteer finds the place (not covered -> done, no AI call) and the router decides
          quick or full + the answer language from the question and the prefetched data, and writes the plan
          (intent, user type, sources) - no AI planning on either path (22 Oct night).
          The Data & Reconciler agent prefetches the world in the background from the very start.
gather    Data & Reconciler agent: health checks -> World Model -> evidence for the planned place.
forecast  Forecast agent: verdict + range + confidence (quick plan -> current levels only).
draft     The answer card (app/card.py) in the user's language, built by code; on the full path Nemotron adds
          only a short explanation that may use only the card's numbers.
critique  Critic: code checks + its own Zetaris re-queries + deep-lane review -> approve or reject.
revise    after a rejection the Coordinator redrafts with the Critic's problems, then back to critique. After
          critic.MAX_REJECTIONS (2) rejections the answer is the code-written summary, labelled low confidence.
Paths (B-17): quick = jps + MET forecast, no cross-check, "now" forecast, answer and review by code (no Nemotron
call at all); full = everything. Time budget from the start of the run: quick 30 s, full 150 s. When too little is left for a model call, that step
falls back to code (answer written by code, review by code checks) and the trace says why ("budget: ...").
Every answer then passes the safety gate (app/safety.py, B-58). Every state change is one trace line with the elapsed time; a timing line closes the run. A 10-minute hard
deadline ends the run with whatever is safe to say.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app import card as card_mod
from app import config, gazetteer, router, safety, trace
from app.adapters import zetaris
from app.agents import coordinator, critic, data_agent, forecast_agent
from app.engines.world_model import WorldModel

DEADLINE_S = 600
BUDGET_S = {"quick": 30, "full": 150}    # Husaini 22 Oct night: the longest the user should wait for an answer
REPLAY_BUDGET_S = 240                    # replay runs only (B-70, Husaini 22 Oct night) - traced as "replay budget 240 s"
MIN_MODEL_S = 10                         # don't start a model call with less time than this left
RESERVE_S = 2                            # kept back from every model call for the steps after it
RECHECK_S = 6                            # the Critic's own Zetaris re-query needs about this long
FINAL_RESERVE_S = 10                     # the Critic's model must leave this much for writing the final answer
WORLD_PATH = config.ROOT / "data" / "world" / "world.sqlite"


def open_world(run_id):
    """The shared World Model: on disk (grows across runs) when live; in memory in SAMPLE_MODE (replay only)."""
    if config.sample_mode():
        return WorldModel()
    WORLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    return WorldModel(storage=WORLD_PATH, audit_jsonl=config.ROOT / "logs" / f"worldmodel-audit-{run_id}.jsonl")


def run(question, llm=None, world=None, now=None, deadline_s=DEADLINE_S, log_dir=None, quiet=False, budget_s=None,
        on_step=None, replay=None, at=None, default_scene=False):
    """One question end to end. Returns {run_id, status, answer, plan, evidence, forecast, card, reviews, timing,
    trace}.
    budget_s overrides the per-effort budget (tests); on_step(record) sees every trace step live.
    replay='nov2024', at=<aware datetime> (B-70): a flood replay - the clock is set to `at`, every data source is cut
    there, the World Model is a fresh in-memory one, the budget is REPLAY_BUDGET_S. Never raises for data or model problems; those end up in the
    answer and the trace."""
    run_ = trace.start_run(question, log_dir=log_dir, quiet=quiet, listener=on_step)
    t0 = time.monotonic()
    own_world = world is None
    if not replay and default_scene and config.sample_mode():   # entry points (CLI, API, evals) ask for it
        # B-75 (organiser ruling 23 Oct): no JPS readings offline - a bare question runs on the SYNTHETIC calm day
        replay = config.SAMPLE_SCENE
        at = datetime.strptime(config.REPLAYS[replay]["default_at"], "%Y-%m-%d %H:%M").replace(tzinfo=config.MYT)
        trace.step("System", "sample_scene", input_summary=replay,
                   output_summary=config.REPLAYS[replay]["title"],
                   decision="SAMPLE_MODE has no live data and redistributes no JPS readings -> the SYNTHETIC calm-day "
                            "scene (choose another scene with --replay)")
    if replay:
        if replay not in config.REPLAYS or at is None:
            raise ValueError(f"unknown replay {replay!r} or no replay time")
        now, budget_s = at, budget_s or REPLAY_BUDGET_S
        world = world or WorldModel()               # 2024 facts never mix with today's World Model
        trace.step("System", "replay", input_summary=replay,
                   output_summary=f"{config.REPLAYS[replay]['title']} at {at.astimezone(config.MYT):%d %b %Y %H:%M} MYT",
                   decision=f"replay budget {REPLAY_BUDGET_S} s; all data cut at the replay time; reconstructed levels "
                            "are labelled", details={"scenario": replay, "at": at.isoformat()})
    world = world or open_world(run_.run_id)
    state, p, evidence, fc, card, answer, status = "plan", None, None, None, None, None, "success"
    reviews, timing, budget = [], {}, None
    pool = ThreadPoolExecutor(max_workers=1)
    pre = pool.submit(trace.bind(data_agent.prefetch), world, now, replay)    # world refresh while code routes

    def elapsed():
        return time.monotonic() - t0

    def left():
        """Seconds left: the effort budget once the plan is known, never beyond the hard deadline."""
        hard = deadline_s - elapsed()
        return max(0.0, min(hard, budget - elapsed()) if budget else hard)

    def model_time():
        """Time a model call may use: what is left minus a small reserve for the steps after it."""
        return max(1.0, left() - RESERVE_S)

    def short(step):
        """Too little time for a model call in `step`? -> the reason (also traced), else None."""
        if left() >= MIN_MODEL_S:
            return None
        why = f"budget: {left():.0f} s of {budget} s left - {step} by code"
        trace.step("System", "budget", input_summary=step, output_summary=why, status="fallback", decision=why)
        return why

    try:
        while state != "done":
            if elapsed() > deadline_s:
                trace.step("System", "deadline", output_summary=f"{deadline_s} s passed in state '{state}'",
                           status="failed", decision="Stop and answer with what is safe to say")
                status = "failed"
                if answer is None:
                    answer = {"text": "VEDA ran out of time before it could check the data. Please try again.",
                              "language": "en", "drafted_by": "fallback"}
                break
            trace.step("System", "state", input_summary=state,
                       decision=f"Entering state '{state}' at {elapsed():.1f} s"
                                + (f" ({left():.0f} s of the {p['effort']} budget left)" if budget else ""))
            current, started = state, elapsed()
            if state == "plan":
                lang = router.language(question)
                try:
                    res, down = gazetteer.resolve(question, agent=coordinator.AGENT), None
                except zetaris.ZetarisError as e:        # audit 23 Oct: Zetaris down / no keys -> an answer, not a 500
                    res, down = None, e
                if down is not None:
                    trace.step("System", "data.unavailable", output_summary=f"{down.kind}: {down}", status="fallback",
                               decision="Zetaris cannot be reached -> 'cannot check now' answer, no place, no verdict"
                                        + (" (set SAMPLE_MODE=true to run offline on recorded data)"
                                           if down.kind == "auth" else ""))
                    p = {"question_language": lang, "place": None, "place_status": "unavailable",
                         "place_message": str(down), "planned_by": "code"}
                    answer = {"text": card_mod.unavailable_reply(lang), "language": lang, "drafted_by": "code"}
                    status, state = "fallback", "done"
                elif res.status != "found":
                    p = {"question_language": lang, "place": None, "place_status": res.status,
                         "place_message": res.message, "planned_by": "code"}
                    text = card_mod.place_reply(res, lang)
                    if router.emergency(question):          # someone in trouble: safety advice first, place or not
                        text = card_mod.emergency_reply(lang, text)
                        trace.step("System", "emergency", input_summary=router.emergency(question),
                                   output_summary="ACT advice first", decision="the question says the person is "
                                   "trapped / stranded -> ACT advice (999 / 991) before anything else")
                    answer = {"text": text, "language": lang, "drafted_by": "code"}
                    state = "done"
                else:
                    r = router.route(question, res.place, world, pre.result())
                    budget = budget_s or BUDGET_S[r["effort"]]
                    p = router.code_plan(question, res, r)          # both paths: no AI planning (22 Oct night)
                    coordinator.remember(world, p)
                    p["route_reasons"] = r["reasons"]
                    state = "gather"
            elif state == "gather":
                evidence = data_agent.gather(p, world, now=now, pre=pre.result())
                state = "forecast"
            elif state == "forecast":
                old = fc["verdict"] if fc else None
                fc = forecast_agent.forecast(p, evidence, world)
                if old is not None:                       # B-71(b): back here after the Critic's request
                    trace.step("System", "verdict.recomputed", input_summary="new source from the Data & Reconciler",
                               output_summary=f"verdict recomputed after the Critic's request: {old} → {fc['verdict']}",
                               target_agent="Coordinator", decision=("verdict changed -> a new answer is drafted"
                                                                     if fc["verdict"] != old else
                                                                     "verdict unchanged -> the answer is redrafted with "
                                                                     "the new source and checked again"))
                card = card_mod.build(p, evidence, fc)
                if router.emergency(question):            # also when the verdict is already ACT: the label stays
                    card["action"] = card_mod.ADVICE["ACT"]  # trapped / stranded: ACT advice whatever the river says
                    card["emergency"] = True                  # labelled "safety first" + a note under a NORMAL verdict
                    trace.step("System", "emergency", input_summary=router.emergency(question),
                               output_summary="action line = ACT advice", decision="the question says the person "
                               "is trapped / stranded -> ACT advice on the card; the verdict still shows the data")
                state = "draft"
            elif state == "draft":
                why = "quick path: answer written by code" if p["effort"] == "quick" else short("the answer")
                answer = coordinator.draft(question, p, evidence, forecast=fc, card=card, llm=llm,
                                           budget_s=model_time(), use_model=why is None, skip_reason=why)
                state = "critique"
            elif state == "critique":
                quick = p["effort"] == "quick"
                why = "quick plan: review by code checks only" if quick else short("the review")
                rv = critic.review(question, p, evidence, fc, answer, world, round_no=len(reviews) + 1,
                                   llm=llm, budget_s=max(1.0, left() - FINAL_RESERVE_S), use_model=why is None,
                                   recheck_data=not quick and (why is None or left() >= RECHECK_S), skip_reason=why)
                if (rv.get("data_request") or {}).get("found"):
                    state = "forecast"                    # B-71(b): new source -> recompute, redraft, re-check
                    timing[current] = round(timing.get(current, 0) + elapsed() - started, 1)
                    continue
                reviews.append(rv)
                upstream_missing = [m for m in evidence.get("missing_sources") or [] if m["role"] == "upstream"]
                if upstream_missing and not card.get("missing"):
                    card["missing"] = upstream_missing     # the card says what is missing (B-71(b))
                    answer = {**answer, "card": card, "text": card_mod.render(
                        card, answer.get("language", "en"), answer.get("explanation"),
                        low_confidence=bool(answer.get("low_confidence")))}
                if answer.get("explanation") and "model" not in reviews[-1]["checked_by"]:
                    # Husaini 22 Oct night: nothing goes out that the AI Critic has not checked
                    answer = coordinator.template_answer(card, p["question_language"],
                                                         "the Critic's AI review did not run or timed out")
                    trace.ai_fallback("System", "explanation dropped, not reviewed by AI",
                                      "the Critic's AI review did not run or timed out - nothing unreviewed goes out")
                if reviews[-1]["decision"] == "approve":
                    answer["approved"] = True
                    state = "done"
                elif len(reviews) >= critic.MAX_REJECTIONS or short("the revision"):
                    answer = coordinator.low_confidence_answer(evidence, fc, reviews[-1], card,
                                                               p["question_language"])
                    state = "done"
                else:
                    state = "revise"
            elif state == "revise":
                answer = coordinator.draft(question, p, evidence, forecast=fc, card=card, llm=llm,
                                           budget_s=model_time(), feedback=reviews[-1], previous=answer)
                state = "critique"
            timing[current] = round(timing.get(current, 0) + elapsed() - started, 1)
        answer = safety.gate(answer, card, evidence, fc)      # B-58: the last check on every answer, every path
        timing["total"] = round(elapsed(), 1)
        over = budget is not None and timing["total"] > budget
        trace.step("System", "timing", output_summary=f"total {timing['total']} s"
                   + (f" (budget {budget} s, {'OVER' if over else 'within'})" if budget else "")
                   + " - " + ", ".join(f"{k} {v} s" for k, v in timing.items() if k != "total"),
                   status="fallback" if over else "success", details={"timing": timing, "budget_s": budget})
    except Exception as e:          # a bug must still close the trace with a clear failure line
        status = "failed"
        trace.step("System", "error", output_summary=f"{type(e).__name__}: {e}", status="failed")
        raise
    finally:
        try:
            pre.result()                     # never close the world while the prefetch thread still writes
        except Exception:                    # its own failure is already in the trace
            pass
        pool.shutdown()
        path = trace.end_run(status, (answer or {}).get("text"))
        if own_world:
            world.close()
    return {"run_id": run_.run_id, "status": status, "answer": answer, "plan": p, "evidence": evidence,
            "forecast": fc, "card": card, "reviews": reviews, "timing": timing, "trace": str(path)}
