"""B-17 tests: quick vs full path, time budget fallbacks, timing line, parallel prefetch, timeouts.

Offline: replays the committed SAMPLE_MODE fixtures with a stand-in model.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from app import gazetteer, loop, trace
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
        fc = json.loads(messages[1]["content"])["evidence"]["forecast"]
        text = (f"{fc['verdict']} ({fc['jps_level_name']['en']}), confidence {fc['confidence']['label']}. "
                "data.gov.my is stale.")
        return SimpleNamespace(data={"answer": text}, text=text)
    llm.calls = calls
    return llm


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


def test_quick_path_really_skips_steps(offline):
    llm = stub("quick")
    r = loop.run("Is Rantau Panjang ok?", llm=llm, log_dir=offline, quiet=True)
    actions = [x["action"] for x in lines(r)]
    assert "data.quick" in actions and "data.cross_check" not in actions and "critic.requery" not in actions
    assert r["forecast"]["mode"] == "now" and r["reviews"][0]["checked_by"] == ["code"]
    assert llm.calls == ["fast", "fast"]                              # plan + draft; no deep-lane review
    assert r["evidence"]["cross_check"] is None


def test_full_path_runs_everything(offline):
    llm = stub("full")
    r = loop.run("Is Rantau Panjang at risk?", llm=llm, log_dir=offline, quiet=True)
    actions = [x["action"] for x in lines(r)]
    assert {"data.cross_check", "data.reconcile", "critic.requery"} <= set(actions)
    assert r["reviews"][0]["checked_by"] == ["code", "zetaris", "model"] and llm.calls == ["fast", "fast", "deep"]


def test_no_time_left_means_code_answer_and_code_review_with_reasons(offline):
    llm = stub("full")
    r = loop.run("Is Rantau Panjang at risk?", llm=llm, log_dir=offline, quiet=True, budget_s=0.001)
    budget = [x for x in lines(r) if x["action"] == "budget"]
    assert [b["input_summary"] for b in budget] == ["the answer", "the review"]
    assert all(b["status"] == "fallback" and b["decision"].startswith("budget:") for b in budget)
    assert r["answer"]["drafted_by"] == "fallback" and llm.calls == ["fast"]          # only the plan call
    assert r["reviews"][0]["checked_by"] == ["code"] and r["answer"]["approved"]          # no time to re-query either


def test_timing_line_closes_the_run(offline):
    r = loop.run("Is Rantau Panjang at risk?", llm=stub("full"), log_dir=offline, quiet=True)
    t = [x for x in lines(r) if x["action"] == "timing"][0]
    assert set(r["timing"]) == {"plan", "gather", "forecast", "draft", "critique", "total"}
    assert "budget 90 s" in t["output_summary"] and t["details"]["budget_s"] == 90
    states = [x["decision"] for x in lines(r) if x["action"] == "state"]
    assert states[0].startswith("Entering state 'plan' at") and "of the full budget left" in states[1]


def test_prefetch_runs_while_planning_and_feeds_gather(offline):
    r = loop.run("Is Rantau Panjang at risk?", llm=stub("full"), log_dir=offline, quiet=True)
    steps = {x["action"]: x["step"] for x in lines(r) if x["action"] in ("world.write", "plan")}
    assert r["evidence"]["usable"] and steps                                    # one prefetch, used by gather
    writes = [x for x in lines(r) if x["action"] == "world.write" and x["agent_name"] == "Data & Reconciler"]
    assert len(writes) == 1 and writes[0]["details"]["queries_in_parallel"] == 10


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
    assert loop.BUDGET_S == {"quick": 30, "full": 90}


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
