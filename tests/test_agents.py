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
from app.agents import coordinator, critic, data_agent
from app.engines.world_model import WorldModel

GOOD_PLAN = {"intent": "risk_check", "user_type": "resident", "place_text": "Rantau Panjang",
             "sources": ["jps_levels", "open_meteo", "mygov_forecast"], "effort": "full", "language": "en",
             "reason": "River status and rain for Rantau Panjang."}


def stub_llm(plan=None, answer=None, fail=False, review=None):
    """A stand-in for nightshift.chat: the explanation for the draft, a review for the Critic (`plan` is unused)."""
    calls = []

    def llm(lane, messages, agent, json_mode=False, **kw):
        calls.append({"lane": lane, "system": messages[0]["content"][:40]})
        if fail:
            raise nightshift.NightshiftError("stub: Nightshift down")
        if messages[0]["content"] in (critic.CRITIC_SYSTEM, critic.SMALL_SYSTEM):   # Critic (any lane): approve unless told otherwise
            d = review or "approve"
            data = {"decision": d, "problems": [], "fix": "", "ok": d == "approve", "reason": "stub"}
        else:                                   # draft: only the explanation (B-21) - the card is code
            data = {"explanation": answer if answer is not None else "VEDA checked the river readings for this place."}
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


# -- Coordinator: the question radar -------------------------------------------------------------------------
def test_remember_writes_intent_tags_not_the_question_to_the_world(run):
    w = WorldModel()
    p = {"intent": "risk_check", "user_type": "resident", "effort": "quick", "planned_by": "code",
         "place": {"place_id": "tumpat"}, "place_status": "covered",
         "question": "My phone is 019-8765432, is Tumpat safe?"}
    coordinator.remember(w, p)
    ctx = [c for c in w.store.state["contexts"].values() if c["type"] == "run"][0]
    assert "8765432" not in json.dumps(ctx) and ctx["attrs"]["intent"] == "risk_check"


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


def test_invented_number_is_caught_by_the_critic_not_the_coordinator(offline):
    """B-14 (Husaini 23 Oct): the Coordinator only drafts; the Critic rejects -> rewrite -> re-check, then the
    explanation never reaches the user."""
    r = loop.run("Is Rantau Panjang at risk in the next two days?", llm=stub_llm(GOOD_PLAN, answer="It is 99.99 m!"),
                 log_dir=offline, quiet=True)
    assert "99.99" not in r["answer"]["text"] and r["answer"]["safety_line"].startswith("Not an official warning")
    assert r["reviews"][0]["decision"] == "reject" and "99.99" in r["reviews"][0]["problems"][0]["detail"]
    steps = [(x["agent_name"], x["action"]) for x in lines(r["trace"])]
    review_at = [i for i, s in enumerate(steps) if s == ("Critic", "critic.review")]
    revise_at = [i for i, s in enumerate(steps) if s == ("Coordinator", "revise")]
    assert len(review_at) >= 2 and revise_at and review_at[0] < revise_at[0] < review_at[1]   # reject -> rewrite -> re-check


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
    assert [c["lane"] for c in llm.calls] == ["deep", "deep"]    # B-85: explanation + Critic, Super VL by name


def test_loop_without_any_model_still_answers_in_sample_mode(offline):
    r = loop.run("Is Tumpat safe tonight?", log_dir=offline, quiet=True)      # real Nightshift adapter: refuses
    assert r["status"] == "success" and r["answer"]["drafted_by"] == "fallback" and "Kok Majid" in r["answer"]["text"]


def test_loop_stops_after_plan_for_uncovered_place(offline):
    r = loop.run("Is Gua Musang flooding?", llm=stub_llm({**GOOD_PLAN, "place_text": "Gua Musang"}),
                 log_dir=offline, quiet=True)
    assert r["evidence"] is None and "not covered" in r["answer"]["text"]
    assert "gather" not in [x["input_summary"] for x in lines(r["trace"]) if x["action"] == "state"]


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


# -- draft retries (B-85, Husaini 23 Oct): Super VL on the deep lane, <= 90 s in all ----------------------------
class _Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


def _scripted(clock, steps):
    """A stand-in model: each step = (seconds it takes, error text or None for an answer)."""
    calls = []

    def llm(lane, messages, agent, **kw):
        took, err = steps[len(calls)]
        calls.append({"lane": lane, "budget_s": kw.get("budget_s"), "max_tokens": kw.get("max_tokens")})
        clock.t += took
        if err:
            raise nightshift.NightshiftError(err)
        return SimpleNamespace(data={"explanation": "ok"}, text="")
    llm.calls = calls
    return llm


@pytest.fixture
def clock(monkeypatch, tmp_path):
    from app import trace
    c = _Clock()
    monkeypatch.setattr(coordinator.time, "monotonic", c.monotonic)
    trace.start_run("t", log_dir=tmp_path, quiet=True)
    yield c
    trace.end_run()


CUT = "Nightshift failed after 1 attempts: HTTP 200: ttfb_timeout:nvidia/nemotron-3.5-super-vl-120b-a12b"
E500 = "Nightshift failed after 1 attempts: HTTP 200: nvidia_500: Failed to generate completions"


def test_draft_uses_super_vl_lane_tokens_and_a_90_s_cap(clock, monkeypatch):
    monkeypatch.delenv("METERLESS_MODEL_DEEP", raising=False)            # the code default, not a developer .env
    llm = _scripted(clock, [(20, None)])
    assert coordinator._draft_call(llm, {}, None, 150).data == {"explanation": "ok"}
    assert llm.calls == [{"lane": "deep", "budget_s": 90, "max_tokens": 4096}]
    assert nightshift.lane_model("deep") == "nvidia/nemotron-3.5-super-vl-120b-a12b"


def test_fast_nvidia_500_is_retried_once(clock):
    llm = _scripted(clock, [(2.5, E500), (20, None)])
    assert coordinator._draft_call(llm, {}, None, 150).data == {"explanation": "ok"}
    assert len(llm.calls) == 2 and llm.calls[1]["budget_s"] == 87.5            # still inside the 90 s cap
    llm = _scripted(clock, [(2.5, E500), (2.5, E500), (20, None)])
    with pytest.raises(nightshift.NightshiftError):
        coordinator._draft_call(llm, {}, None, 150)
    assert len(llm.calls) == 2                                                # once only


def test_45_s_cut_is_retried_only_with_45_s_of_the_90_s_left(clock):
    llm = _scripted(clock, [(45, CUT), (30, None)])                           # 45 s used, 45 s left -> retry
    assert coordinator._draft_call(llm, {}, None, 150).data == {"explanation": "ok"}
    assert len(llm.calls) == 2 and llm.calls[1]["budget_s"] == 45             # the retry cannot pass 90 s
    llm = _scripted(clock, [(46, CUT), (30, None)])                           # 44 s left -> no retry
    with pytest.raises(nightshift.NightshiftError):
        coordinator._draft_call(llm, {}, None, 150)
    assert len(llm.calls) == 1
    llm = _scripted(clock, [(45, CUT), (30, None)])                           # the run gave only 60 s
    with pytest.raises(nightshift.NightshiftError):
        coordinator._draft_call(llm, {}, None, 60)
    assert len(llm.calls) == 1 and llm.calls[0]["budget_s"] == 60
    llm = _scripted(clock, [(45, CUT), (45, CUT), (30, None)])                # a second cut: never a third try
    with pytest.raises(nightshift.NightshiftError):
        coordinator._draft_call(llm, {}, None, 150)
    assert len(llm.calls) == 2


def test_fast_500_then_cut_stays_inside_90_s(clock):
    llm = _scripted(clock, [(2.5, E500), (45, CUT), (30, None)])              # 47.5 s used, 42.5 left < 45
    with pytest.raises(nightshift.NightshiftError):
        coordinator._draft_call(llm, {}, None, 150)
    assert len(llm.calls) == 2


def test_slow_other_failure_is_not_retried(clock):
    llm = _scripted(clock, [(30, "Nightshift failed after 1 attempts: network error: ConnectionError"), (20, None)])
    with pytest.raises(nightshift.NightshiftError):
        coordinator._draft_call(llm, {}, None, 150)
    assert len(llm.calls) == 1


# -- B-85 + Cowork 24 Oct: one draft retry after an empty response, same rule as the ttfb cut -------------------
class _Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


def _draft_stub(clock, script):
    """script: [(seconds the call takes, error message or None for success)]; records the budget each call got."""
    calls = []

    def llm(lane, messages, agent, budget_s=None, **kw):
        took, err = script[len(calls)]
        calls.append(budget_s)
        clock.t += took
        if err:
            raise nightshift.NightshiftError(err)
        return SimpleNamespace(data={"explanation": "ok"}, text="ok")
    llm.calls = calls
    return llm


EMPTY = "Nightshift failed after 1 attempts: empty response -> retry with max_tokens=8192"


@pytest.mark.parametrize("first_took,retried", [(26, True), (46, False)])     # 90-26 = 64 s left; 90-46 = 44 s left
def test_draft_retries_once_after_an_empty_response_only_with_45_s_left(run, monkeypatch, first_took, retried):
    clock = _Clock()
    monkeypatch.setattr(coordinator.time, "monotonic", clock.monotonic)
    llm = _draft_stub(clock, [(first_took, EMPTY), (12, None)])
    if retried:
        assert coordinator._draft_call(llm, {}, None, None).data == {"explanation": "ok"}
        assert len(llm.calls) == 2 and llm.calls[1] == pytest.approx(90 - first_took)     # never past the 90 s cap
        rec = [x for x in lines(trace.current_run().path) if x["action"] == "draft.retry"][-1]
        assert "draft retry after empty response" in rec["decision"]
    else:
        with pytest.raises(nightshift.NightshiftError):
            coordinator._draft_call(llm, {}, None, None)
        assert len(llm.calls) == 1


def test_draft_empty_response_retry_happens_once_and_respects_the_run_budget(run, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(coordinator.time, "monotonic", clock.monotonic)
    llm = _draft_stub(clock, [(15, EMPTY), (15, EMPTY), (5, None)])
    with pytest.raises(nightshift.NightshiftError):
        coordinator._draft_call(llm, {}, None, None)
    assert len(llm.calls) == 2                                           # one retry only
    clock2 = _Clock()
    monkeypatch.setattr(coordinator.time, "monotonic", clock2.monotonic)
    llm2 = _draft_stub(clock2, [(15, EMPTY), (5, None)])
    with pytest.raises(nightshift.NightshiftError):                       # run budget 50 s: 35 s left < 45 s
        coordinator._draft_call(llm2, {}, None, 50)
    assert llm2.calls == [50]


def test_is_empty_response():
    assert nightshift.is_empty_response(EMPTY) and not nightshift.is_empty_response("HTTP 200: ttfb_timeout:nvidia/x")
