"""The agent loop: a plain Python state machine (decided 22 Oct - no LangGraph, so every step is readable).

    result = loop.run("Is Rantau Panjang at risk?")

    plan -> gather -> forecast -> draft -> critique -> (revise -> critique) -> done

plan      Coordinator: intent, user type, place (gazetteer), sources, effort. Unknown place -> done with the
          gazetteer's reply ("Did you mean...?" / not covered).
gather    Data & Reconciler agent: Zetaris -> health checks -> World Model -> evidence.
forecast  Forecast agent: verdict + range + confidence from the evidence (quick plan -> current levels only).
draft     Coordinator writes the answer from the evidence.
critique  Critic: code checks + its own Zetaris re-queries + deep-lane review -> approve or reject.
revise    after a rejection the Coordinator redrafts with the Critic's problems, then back to critique. After
          critic.MAX_REJECTIONS (2) rejections the answer is the code-written summary, labelled low confidence.
Every state change is one trace line. A 10-minute deadline ends the run with whatever is safe to say.
"""
import time

from app import config, trace
from app.agents import coordinator, critic, data_agent, forecast_agent
from app.engines.world_model import WorldModel

STATES = ("plan", "gather", "forecast", "draft", "critique", "revise", "done")
DEADLINE_S = 600
WORLD_PATH = config.ROOT / "data" / "world" / "world.sqlite"


def open_world(run_id):
    """The shared World Model: on disk (grows across runs) when live; in memory in SAMPLE_MODE (replay only)."""
    if config.sample_mode():
        return WorldModel()
    WORLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    return WorldModel(storage=WORLD_PATH, audit_jsonl=config.ROOT / "logs" / f"worldmodel-audit-{run_id}.jsonl")


def run(question, llm=None, world=None, now=None, deadline_s=DEADLINE_S, log_dir=None, quiet=False):
    """One question end to end. Returns {run_id, status, answer, plan, evidence, forecast, reviews, trace}.
    Never raises for data or model problems; those end up in the answer and the trace."""
    run_ = trace.start_run(question, log_dir=log_dir, quiet=quiet)
    t0 = time.monotonic()
    own_world = world is None
    world = world or open_world(run_.run_id)
    state, p, evidence, fc, answer, status = "plan", None, None, None, None, "success"
    reviews = []

    def left():
        return max(1.0, deadline_s - (time.monotonic() - t0))

    try:
        while state != "done":
            if time.monotonic() - t0 > deadline_s:
                trace.step("System", "deadline", output_summary=f"{deadline_s} s passed in state '{state}'",
                           status="failed", decision="Stop and answer with what is safe to say")
                status = "failed"
                if answer is None:
                    answer = {"text": "VEDA ran out of time before it could check the data. Please try again.",
                              "language": "en", "drafted_by": "fallback"}
                break
            trace.step("System", "state", input_summary=state, decision=f"Entering state '{state}'")
            if state == "plan":
                p = coordinator.plan(question, world=world, llm=llm, budget_s=left())
                if p["place_status"] != "found":
                    answer = {"text": p["place_message"], "language": p["question_language"], "drafted_by": "code"}
                    state = "done"
                else:
                    state = "gather"
            elif state == "gather":
                evidence = data_agent.gather(p, world, now=now)
                state = "forecast"
            elif state == "forecast":
                fc = forecast_agent.forecast(p, evidence, world)
                state = "draft"
            elif state == "draft":
                answer = coordinator.draft(question, p, evidence, forecast=fc, llm=llm, budget_s=left())
                state = "critique"
            elif state == "critique":
                reviews.append(critic.review(question, p, evidence, fc, answer, world, round_no=len(reviews) + 1,
                                             llm=llm, budget_s=left()))
                if reviews[-1]["decision"] == "approve":
                    answer["approved"] = True
                    state = "done"
                elif len(reviews) >= critic.MAX_REJECTIONS:
                    answer = coordinator.low_confidence_answer(evidence, fc, reviews[-1])
                    state = "done"
                else:
                    state = "revise"
            elif state == "revise":
                answer = coordinator.draft(question, p, evidence, forecast=fc, llm=llm, budget_s=left(),
                                           feedback=reviews[-1], previous=answer)
                state = "critique"
        answer.setdefault("safety_line", coordinator.SAFETY.get(answer.get("language"), coordinator.SAFETY["en"]))
    except Exception as e:          # a bug must still close the trace with a clear failure line
        status = "failed"
        trace.step("System", "error", output_summary=f"{type(e).__name__}: {e}", status="failed")
        raise
    finally:
        path = trace.end_run(status, (answer or {}).get("text"))
        if own_world:
            world.close()
    return {"run_id": run_.run_id, "status": status, "answer": answer, "plan": p, "evidence": evidence,
            "forecast": fc, "reviews": reviews, "trace": str(path)}
