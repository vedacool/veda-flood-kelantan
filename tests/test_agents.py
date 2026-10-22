"""B-12 / B-13 tests: Data & Reconciler agent health checks + gather, Coordinator plan/draft, and the loop.

Offline tests replay the committed SAMPLE_MODE fixtures (data/fixtures/zetaris/) and use a stand-in model, so they
run in CI with an empty .env. The live test (VEDA_LIVE=1) asks Nemotron two different questions.
"""
import json
import os
from types import SimpleNamespace

import pytest

from app import gazetteer, loop, trace
from app.adapters import nightshift
from app.agents import coordinator, data_agent
from app.engines.world_model import WorldModel

GOOD_PLAN = {"intent": "risk_check", "user_type": "resident", "place_text": "Rantau Panjang",
             "sources": ["jps_levels", "open_meteo", "mygov_forecast"], "effort": "full", "language": "en",
             "reason": "River status and rain for Rantau Panjang."}


def stub_llm(plan=None, answer=None, fail=False, review=None):
    """A stand-in for nightshift.chat: returns the given plan for the plan call and the answer for the draft."""
    calls = []

    def llm(lane, messages, agent, json_mode=False, **kw):
        calls.append({"lane": lane, "system": messages[0]["content"][:40]})
        if fail:
            raise nightshift.NightshiftError("stub: Nightshift down")
        if messages[0]["content"] == coordinator.PLAN_SYSTEM:
            data = plan
        elif lane == "deep":                    # Critic: approve unless told otherwise
            data = {"decision": review or "approve", "problems": [], "fix": ""}
        else:                                   # draft: only the explanation (B-21) - the card is code
            data = {"explanation": answer if answer is not None else "The river is steady for now."}
        return SimpleNamespace(data=data, text=json.dumps(data))
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


@pytest.fixture
def run(offline):
    trace.start_run("agents test", log_dir=offline, quiet=True)
    yield offline
    trace.end_run()


def lines(path):
    return [json.loads(x) for x in open(path, encoding="utf-8")]


# -- Data & Reconciler: checks --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("age, expected", [(0, "fresh"), (60, "fresh"), (61, "aging"), (180, "aging"),
                                           (181, "stale"), (None, "unknown")])
def test_jps_freshness_limits(age, expected):
    assert data_agent.freshness("jps_levels", age) == expected


def test_forecast_freshness_limits():
    assert data_agent.freshness("open_meteo", 360) == "fresh" and data_agent.freshness("open_meteo", 721) == "stale"
    assert data_agent.freshness("mygov_forecast", 1000) == "aging"


@pytest.mark.parametrize("row, ok, part", [
    ({"level_m": 7.18, "change_1h_m": -0.03, "danger_m": 9.0}, True, "ok"),
    ({"level_m": "7,18"}, False, "not a number"),
    ({"level_m": None}, False, "not a number"),
    ({"level_m": 250.0}, False, "outside"),
    ({"level_m": 30.0, "danger_m": 9.0}, False, "above danger"),
    ({"level_m": 7.0, "change_1h_m": 4.2}, False, "in 1 h"),
])
def test_gauge_checks(row, ok, part):
    h = data_agent.check("jps_levels", row)
    assert h["ok"] is ok and part in (h["schema"] + h["plausible"])


def test_rain_and_forecast_checks():
    assert data_agent.check("open_meteo", {"rain_past_24h_mm": 2.0, "rain_next_24h_mm": 10.9})["ok"]
    assert not data_agent.check("open_meteo", {"rain_past_24h_mm": None, "rain_next_24h_mm": None})["ok"]
    assert not data_agent.check("open_meteo", {"rain_past_24h_mm": -1.0})["ok"]
    assert data_agent.check("mygov_forecast", {"forecast_today": "Ribut petir"})["ok"]
    assert not data_agent.check("mygov_forecast", {"forecast_today": ""})["ok"]


# -- Data & Reconciler: gather (replayed Zetaris) --------------------------------------------------------------------
def rp_plan(sources=("jps_levels", "open_meteo", "mygov_forecast")):
    return {"intent": "risk_check", "place": gazetteer.resolve("Rantau Panjang").place, "sources": list(sources)}


def test_gather_facts_carry_sql_hash_time_and_health(run):
    w = WorldModel()
    ev = data_agent.gather(rp_plan(), w)
    assert ev["usable"] is True and ev["context"]["found"]
    readings = [f for f in w.store.state["facts"].values() if f["predicate"] == "water_level_m"]
    assert readings
    for f in readings:                                     # B-13 acceptance: {sql, query_hash, ts, health}
        src = f["source"]
        assert src["sql"].startswith("SELECT") and src["query_hash"] and src["at"] and "ok" in src["health"]


def test_gather_catches_the_frozen_flood_warning_source(run):
    w = WorldModel()
    ev = data_agent.gather(rp_plan(), w)
    assert ev["cross_check"]["status"] == "stale" and "excluded" in ev["notes"][0]
    ctx = w.store.state["contexts"]["source:veda:mygov_flood"]
    assert ctx["attrs"]["status"] == "stale" and ctx["attrs"]["newest_reading"].startswith("2024-02-23")


def test_gather_keeps_only_what_the_plan_asked_for(run):
    ev = data_agent.gather(rp_plan(["jps_levels"]), WorldModel())
    assert ev["context"]["rain"] is None and ev["context"]["met_forecast"] is None
    assert ev["sources"]["open_meteo"]["status"] == "skipped"


def test_second_gather_adds_only_the_per_run_health_records(run):
    w = WorldModel()
    data_agent.gather(rp_plan(), w)
    again = data_agent.gather(rp_plan(), w)
    assert again["events_added"] == 0       # same replayed data + same clock -> health facts are identical too


def test_stale_controlling_gauge_is_not_usable(run):
    from datetime import timedelta
    w = WorldModel()
    first = data_agent.gather(rp_plan(), w)
    later = data_agent._utc(first["clock"].replace("T", " ").rstrip("Z")) + timedelta(hours=5)
    ev = data_agent.gather(rp_plan(), w, now=later)
    assert ev["usable"] is False and ev["sources"]["jps_levels"]["status"] == "degraded"
    assert any("cannot be confirmed" in n for n in ev["notes"])


def test_agent_may_refresh_only_veda_wx_tables():
    from app.adapters import zetaris
    assert zetaris.ddl_problem("UNCACHE TABLE veda_wx.om_rain") is None
    assert zetaris.ddl_problem("UNCACHE TABLE veda.river_status_latest")
    assert zetaris.ddl_problem("UNCACHE TABLE veda_pg.stations")


# -- Coordinator: plan ----------------------------------------------------------------------------------------
def test_plan_from_model_is_checked_and_place_comes_from_gazetteer(run):
    p = coordinator.plan("Is Rantau Panjang at risk?", llm=stub_llm(GOOD_PLAN))
    assert p["planned_by"] == "llm" and p["place"]["place_id"] == "rantau_panjang" and p["intent"] == "risk_check"


def test_plan_corrects_bad_model_output(run):
    bad = {"intent": "panic", "user_type": "alien", "place_text": "Atlantis", "sources": ["twitter"],
           "effort": "max", "language": "fr"}
    p = coordinator.plan("Will Kota Bharu flood tonight?", llm=stub_llm(bad))
    assert (p["intent"], p["user_type"], p["effort"], p["question_language"]) == ("risk_check", "unknown", "full", "en")
    assert p["sources"][0] == "jps_levels" and "twitter" not in p["sources"]
    assert p["place"]["place_id"] == "kota_bharu"                 # the model's 'Atlantis' was not trusted
    rec = [x for x in lines(trace.current_run().path) if x["action"] == "plan"][-1]
    assert "not allowed" in rec["decision"] and rec["details"]["fixes"]


def test_plan_falls_back_when_nightshift_fails(run):
    p = coordinator.plan("Is Tumpat safe?", llm=stub_llm(fail=True))
    assert p["planned_by"] == "fallback" and p["place"]["place_id"] == "tumpat" and p["sources"] == list(
        data_agent.SOURCES)
    assert [x for x in lines(trace.current_run().path) if x["action"] == "plan"][-1]["status"] == "fallback"


def test_plan_for_uncovered_place_says_so(run):
    p = coordinator.plan("Is Gua Musang flooding?", llm=stub_llm({**GOOD_PLAN, "place_text": "Gua Musang"}))
    assert p["place"] is None and p["place_status"] == "not_covered" and "not covered" in p["place_message"]


def test_plan_writes_intent_tags_not_the_question_to_the_world(run):
    w = WorldModel()
    coordinator.plan("My phone is 012-3456789, is Tumpat safe?", world=w, llm=stub_llm(GOOD_PLAN))
    ctx = [c for c in w.store.state["contexts"].values() if c["type"] == "run"][0]
    assert "012" not in json.dumps(ctx) and ctx["attrs"]["intent"] == "risk_check"


# -- Coordinator: draft ---------------------------------------------------------------------------------------
FACTS = {"place": "Rantau Panjang", "usable": True, "source_notes": [], "rain": None, "met_forecast_today": None,
         "gauges": [{"gauge": "Sg. Golok di Rantau Panjang", "role": "controlling", "level_m": 7.18, "band": "alert",
                     "read_at": "22 Oct 18:45 MYT", "age_minutes": 26, "thresholds_m": {"alert": 7.0}}]}


@pytest.mark.parametrize("text, problem", [
    ("The river is at 7.18 m (alert 7.0 m) at 18:45.", None),
    ("The river is at 7.5 m.", "not in the evidence"),
    ("Status: WATCH.", "verdict"),
    ("", "empty"),
])
def test_draft_check(text, problem):
    got = coordinator.draft_problem(text, FACTS)
    assert (got is None) if problem is None else (problem in got)


def test_draft_with_invented_number_falls_back_to_code_answer(run):
    ev = data_agent.gather(rp_plan(), WorldModel())
    p = coordinator.plan("Is Rantau Panjang at risk?", llm=stub_llm(GOOD_PLAN))
    a = coordinator.draft("Is Rantau Panjang at risk?", p, ev, llm=stub_llm(answer="It is 99.99 m!"))
    assert a["drafted_by"] == "fallback" and "99.99" not in a["text"] and "Rantau Panjang" in a["text"]
    assert a["safety_line"].startswith("Not an official warning")


# -- Loop -----------------------------------------------------------------------------------------------------
def test_loop_runs_every_state_offline(offline):
    llm = stub_llm(GOOD_PLAN)
    r = loop.run("Is Rantau Panjang at risk?", llm=llm, log_dir=offline, quiet=True)
    assert r["status"] == "success" and r["answer"]["drafted_by"] == "llm"
    assert r["forecast"]["verdict"] in r["answer"]["text"]
    states = [x["input_summary"] for x in lines(r["trace"]) if x["action"] == "state"]
    assert states == ["plan", "gather", "forecast", "draft", "critique"]
    assert r["answer"]["approved"] and r["reviews"][0]["checked_by"] == ["code", "zetaris", "model"]
    agents = {x["agent_name"] for x in lines(r["trace"]) if x["action"] in ("world.read", "world.write")}
    assert agents == {"Coordinator", "Data & Reconciler", "Forecast", "Critic"}          # B-57: all four agents
    assert [c["lane"] for c in llm.calls] == ["fast", "deep"]            # explanation + Critic; plan is code


def test_loop_without_any_model_still_answers_in_sample_mode(offline):
    r = loop.run("Is Tumpat safe tonight?", log_dir=offline, quiet=True)      # real Nightshift adapter: refuses
    assert r["status"] == "success" and r["answer"]["drafted_by"] == "fallback" and "Kok Majid" in r["answer"]["text"]


def test_loop_stops_after_plan_for_uncovered_place(offline):
    r = loop.run("Is Gua Musang flooding?", llm=stub_llm({**GOOD_PLAN, "place_text": "Gua Musang"}),
                 log_dir=offline, quiet=True)
    assert r["evidence"] is None and "not covered" in r["answer"]["text"]
    assert "gather" not in [x["input_summary"] for x in lines(r["trace"]) if x["action"] == "state"]


@pytest.mark.skipif(os.getenv("VEDA_LIVE") != "1", reason="live Nightshift + Zetaris: set VEDA_LIVE=1")
def test_live_two_questions_two_plans(tmp_path):
    from dotenv import load_dotenv
    load_dotenv(trace.ROOT / ".env")
    gazetteer.clear_cache()
    plans = []
    for q in ("Is Rantau Panjang at risk of flooding right now?",
              "Mak ayah saya tinggal di Tumpat, patutkah mereka pindah malam ini?"):
        trace.start_run(q, log_dir=tmp_path, quiet=True)
        try:
            plans.append(coordinator.plan(q))
        finally:
            trace.end_run()
    a, b = plans
    assert a["planned_by"] == b["planned_by"] == "llm"
    assert (a["place"]["place_id"], b["place"]["place_id"]) == ("rantau_panjang", "tumpat")
    assert b["question_language"] == "ms" and b["intent"] != a["intent"]


# -- Reconciliation (B-14: reliability first, then recency) ---------------------------------------------------
def _cand(source, value, at, rel):
    from datetime import datetime, timezone
    return {"source": source, "value": value, "reliability": rel,
            "at": datetime.fromisoformat(at).replace(tzinfo=timezone.utc) if at else None}


def test_reconcile_prefers_reliability_then_recency():
    r = data_agent.reconcile("level", [_cand("a", 7.0, "2026-10-22T10:00", 0.9), _cand("b", 8.0, "2026-10-22T11:00", 0.6)])
    assert (r["chosen"], r["rule"]) == ("a", "reliability")                   # reliability beats a newer reading
    r = data_agent.reconcile("level", [_cand("a", 7.0, "2024-02-23T06:45", 0.9), _cand("b", 5.2, "2026-10-22T10:00", 0.9)])
    assert (r["chosen"], r["rule"], r["value"]) == ("b", "recency", 5.2)


def test_reconcile_agreement_and_unresolved():
    r = data_agent.reconcile("level", [_cand("a", 7.00, "2026-10-22T10:00", 0.9), _cand("b", 7.04, None, 0.9)])
    assert r["rule"] == "agree" and r["chosen"] == "a"
    r = data_agent.reconcile("level", [_cand("a", 7.0, "2026-10-22T10:00", 0.9), _cand("b", 8.0, "2026-10-22T10:00", 0.9)])
    assert r["rule"] == "unresolved" and r["chosen"] is None and "not guessed" in r["reason"]
    r = data_agent.reconcile("level", [_cand("a", 7.0, None, 0.9), _cand("b", 8.0, "2026-10-22T10:00", 0.9)])
    assert r["rule"] == "unresolved"                                           # a missing time cannot win on recency


def test_gather_reconciles_jps_against_the_frozen_source(run):
    ev = data_agent.gather(rp_plan(), WorldModel())
    rec = ev["reconciliation"]
    assert rec and all(r["chosen"] == "jps_levels" for r in rec if r["rule"] != "agree")
    assert any(r["rule"] == "recency" for r in rec) and ev["conflicts_unresolved"] == []


def test_unresolved_conflicts_reach_the_answer():
    from app import card
    c = card.build({}, {"conflicts_unresolved": [{"quantity": "water level at X", "reason": "equal"}]}, None)
    assert "Sources disagree on water level at X" in card.render(c, "en")
    assert "Sumber tidak sepakat tentang water level at X" in card.render(c, "ms")


def test_reconcile_ignores_a_source_without_a_value():
    r = data_agent.reconcile("level", [_cand("a", 1.7, "2026-10-22T10:00", 0.9), _cand("b", None, "2024-02-23T06:45", 0.9)])
    assert (r["rule"], r["chosen"], r["value"]) == ("single", "a", 1.7)
    r = data_agent.reconcile("level", [_cand("a", None, None, 0.9), _cand("b", "n/a", None, 0.9)])
    assert r["rule"] == "single" and r["chosen"] is None
