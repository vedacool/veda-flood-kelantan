"""B-17 tests: quick vs full path, time budget fallbacks, timing line, parallel prefetch, timeouts.

Offline: replays the committed SAMPLE_MODE fixtures with a stand-in model.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app import gazetteer, loop, router, trace
from app.adapters import nightshift, zetaris
from app.agents import coordinator, data_agent
from app.engines.world_model import WorldModel
from app.engines.world_model import veda_ingest

PLAN = {"intent": "risk_check", "user_type": "resident", "place_text": "Rantau Panjang",
        "sources": ["jps_levels", "open_meteo", "mygov_forecast"], "effort": "full", "language": "en"}


def stub(effort="full"):
    calls = []

    def llm(lane, messages, agent, **kw):
        calls.append(lane)
        if messages[0]["content"] == coordinator.PLAN_SYSTEM:
            return SimpleNamespace(data={**PLAN, "effort": effort}, text="")
        if lane == "deep":
            return SimpleNamespace(data={"decision": "approve", "problems": [], "fix": ""}, text="")
        return SimpleNamespace(data={"explanation": "The river is steady for now."}, text="")
    llm.calls = calls
    return llm


@pytest.fixture
def force(monkeypatch):
    """Make the router's data say quick (no reasons) or full (one reason), whatever the recorded data shows."""
    def set_route(effort):
        monkeypatch.setattr(router, "data_triggers", lambda *a: [] if effort == "quick" else ["test: forced full"])
    return set_route


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    yield tmp_path
    gazetteer.clear_cache()


def lines(r):
    return [json.loads(x) for x in open(r["trace"], encoding="utf-8")]


def test_quick_path_really_skips_steps(offline, force):
    force("quick")
    llm = stub()
    r = loop.run("Is Rantau Panjang ok?", llm=llm, log_dir=offline, quiet=True)
    actions = [x["action"] for x in lines(r)]
    assert "data.quick" in actions and "data.cross_check" not in actions and "critic.requery" not in actions
    assert r["forecast"]["mode"] == "now" and r["reviews"][0]["checked_by"] == ["code"]
    assert llm.calls == [] and r["plan"]["planned_by"] == "code"          # no Nemotron call at all
    assert r["answer"]["drafted_by"] == "code" and r["evidence"]["cross_check"] is None
    route = [x for x in lines(r) if x["action"] == "route"][0]
    assert route["decision"].startswith("quick:") and route["output_summary"].startswith("quick path")


def test_full_path_runs_everything(offline, force):
    force("full")
    llm = stub("full")
    r = loop.run("Is Rantau Panjang at risk?", llm=llm, log_dir=offline, quiet=True)
    actions = [x["action"] for x in lines(r)]
    assert {"data.cross_check", "data.reconcile", "critic.requery"} <= set(actions)
    assert r["reviews"][0]["checked_by"] == ["code", "zetaris", "model"] and llm.calls == ["fast", "fast", "deep"]
    assert [x for x in lines(r) if x["action"] == "route"][0]["decision"] == "full: test: forced full"


def test_the_model_cannot_lower_the_effort_code_decided(offline, force):
    force("full")
    r = loop.run("Is Rantau Panjang at risk?", llm=stub("quick"), log_dir=offline, quiet=True)
    plan = [x for x in lines(r) if x["action"] == "plan"][0]
    assert r["plan"]["effort"] == "full" and "effort quick -> full (decided by code)" in plan["details"]["fixes"]


def test_question_words_alone_send_it_down_the_full_path(offline, force):
    force("quick")
    r = loop.run("Mak saya di Tumpat, kena pindah malam ni?", llm=stub(), log_dir=offline, quiet=True)
    assert r["plan"]["effort"] == "full" and r["plan"]["question_language"] == "ms"
    assert "kena pindah" in [x for x in lines(r) if x["action"] == "route"][0]["decision"]


def test_place_not_covered_ends_without_any_model_call(offline):
    llm = stub()
    r = loop.run("Is Gua Musang flooding?", llm=llm, log_dir=offline, quiet=True)
    assert llm.calls == [] and r["evidence"] is None and "not covered" in r["answer"]["text"]


def test_no_time_left_means_code_answer_and_code_review_with_reasons(offline, force):
    force("full")
    llm = stub("full")
    r = loop.run("Is Rantau Panjang at risk?", llm=llm, log_dir=offline, quiet=True, budget_s=0.001)
    budget = [x for x in lines(r) if x["action"] == "budget"]
    assert [b["input_summary"] for b in budget] == ["the answer", "the review"]
    assert all(b["status"] == "fallback" and b["decision"].startswith("budget:") for b in budget)
    assert r["answer"]["drafted_by"] == "fallback" and llm.calls == ["fast"]          # only the plan call
    assert r["reviews"][0]["checked_by"] == ["code"] and r["answer"]["approved"]          # no time to re-query either


def test_timing_line_closes_the_run(offline, force):
    force("full")
    r = loop.run("Is Rantau Panjang at risk?", llm=stub("full"), log_dir=offline, quiet=True)
    t = [x for x in lines(r) if x["action"] == "timing"][0]
    assert set(r["timing"]) == {"plan", "gather", "forecast", "draft", "critique", "total"}
    assert "budget 150 s" in t["output_summary"] and t["details"]["budget_s"] == 150
    states = [x["decision"] for x in lines(r) if x["action"] == "state"]
    assert states[0].startswith("Entering state 'plan' at") and "of the full budget left" in states[1]


def test_progress_listener_sees_every_step_live(offline, force):
    force("quick")
    seen = []
    r = loop.run("Kota Bharu ok?", log_dir=offline, quiet=True, on_step=seen.append)
    assert [x["step"] for x in seen] == [x["step"] for x in lines(r)]          # every line, in order, as it happened


def test_prefetch_runs_while_planning_and_feeds_gather(offline):
    r = loop.run("Is Rantau Panjang at risk?", llm=stub("full"), log_dir=offline, quiet=True)
    steps = {x["action"]: x["step"] for x in lines(r) if x["action"] in ("world.write", "plan")}
    assert r["evidence"]["usable"] and steps                                    # one prefetch, used by gather
    writes = [x for x in lines(r) if x["action"] == "world.write" and x["agent_name"] == "Data & Reconciler"]
    assert len(writes) == 1 and writes[0]["details"]["queries_in_parallel"] == 11


def test_parallel_fetch_returns_the_same_rows_as_one_by_one(offline):
    trace.start_run("parallel", log_dir=offline, quiet=True)
    try:
        sqls = veda_ingest.NETWORK_SQL + veda_ingest.READINGS_SQL
        together = veda_ingest.fetch_all(sqls, "test")
        alone = {q: zetaris.run_sql(q, agent="test") for q in sqls}
    finally:
        trace.end_run()
    assert all(together[q].rows == alone[q].rows and together[q].query_hash == alone[q].query_hash for q in sqls)


def test_gather_without_prefetch_still_works(offline):
    trace.start_run("gather alone", log_dir=offline, quiet=True)
    try:
        plan = {"intent": "risk_check", "effort": "full", "place": gazetteer.resolve("Tumpat").place,
                "sources": ["jps_levels"]}
        ev = data_agent.gather(plan, WorldModel())
    finally:
        trace.end_run()
    assert ev["usable"] and ev["cross_check"]["status"] == "stale"


def test_timeouts_follow_the_plan_change_log():
    assert nightshift.TIMEOUT_S == 60 and zetaris.TIMEOUT_S == 30
    assert loop.BUDGET_S == {"quick": 30, "full": 150}


def test_bound_function_can_run_in_many_threads_at_once(tmp_path):
    trace.start_run("threads", log_dir=tmp_path, quiet=True)
    try:
        work = trace.bind(lambda i: trace.step("T", f"job{i}")["run_id"])
        with ThreadPoolExecutor(5) as ex:
            ids = list(ex.map(work, range(10)))
        run_id = trace.current_run().run_id
    finally:
        trace.end_run()
    assert ids == [run_id] * 10
