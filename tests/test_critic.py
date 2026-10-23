"""B-14 tests: Critic code checks, its own Zetaris re-queries, model review rules, and the reject -> revise loop.

Re-queries are faked by patching zetaris.run_sql; the loop tests replay the committed SAMPLE_MODE fixtures.
"""
import json
from types import SimpleNamespace

import pytest

from app import gazetteer, loop, trace
from app.adapters import nightshift, zetaris
from app.agents import coordinator, critic
from app.engines.world_model import WorldModel

FORECAST = {"verdict": "WATCH", "level_name": {"en": "Alert", "ms": "Waspada"}, "mode": "full",
            "confidence": {"score": 0.75, "label": "high", "reasons": []},
            "triggers": [{"level": "WATCH", "rule": "level>=alert", "reason": "at alert"}],
            "controlling": [], "upstream": [], "history": [], "bigger_than_2014": False}
GAUGE = {"station": "station:jps:_DPMS0003", "name": "Rantau Panjang", "role": "controlling", "level_m": 7.12,
         "band": "alert", "observed_at": "2026-10-22T11:45:00Z", "age_minutes": 20, "freshness": "fresh",
         "health": {"ok": True}, "thresholds": {"alert_m": 7.0}}
EVIDENCE = {"place": {"name": "Rantau Panjang"}, "usable": True, "clock": "2026-10-22T12:05:00Z",
            "context": {"gauges": [GAUGE], "sentinels": []}, "cross_check": {"status": "stale"},
            "conflicts_unresolved": [], "notes": []}
GOOD = "Rantau Panjang: WATCH (Alert / Waspada), 7.12 m at 19:45. Confidence high. data.gov.my is stale and excluded."
PLAN = {"place": {"place_id": "rantau_panjang", "name": "Rantau Panjang"}}


def facts(evidence=EVIDENCE):
    return coordinator.facts_for_model(evidence, FORECAST)


def kinds(found):
    return [f["type"] for f in found]


# -- code checks ----------------------------------------------------------------------------------------------
def test_good_draft_passes_code_checks():
    assert critic.code_checks(GOOD, facts(), EVIDENCE) == []


@pytest.mark.parametrize("extra, problem", [
    (" You can still drive through the water on the main road.", "unsafe"),
    (" Boleh redah air di jalan kampung.", "unsafe"),
    (" Wade across carefully if needed.", "unsafe"),
    # audit 23 Oct: a negation elsewhere in the sentence no longer clears it
    (" Don't worry, you can drive through the water to reach the PPS.", "unsafe"),
    (" Jangan risau, boleh redah air untuk ke PPS.", "unsafe"),
    (" Never mind the warning, walk through the flood to get home.", "unsafe"),
    (" You can still wade across the road; avoid the river bank.", "unsafe"),
    (" You can go through the flooded road on foot.", "unsafe"),
    (" It is safe to use the road by the river tonight.", "unsafe"),
    (" Boleh lalu jalan yang banjir dengan kereta.", "unsafe"),
    (" Drive through the water, it is not dangerous.", "unsafe"),
])
def test_unsafe_advice_is_caught_in_english_and_malay(extra, problem):
    assert problem in kinds(critic.code_checks(GOOD + extra, facts(), EVIDENCE))


@pytest.mark.parametrize("extra", [" Do not drive through floodwater.", " Jangan redah air banjir.",
                                   " Never walk through moving water.",
                                   " Do not, under any circumstances, drive through water.",
                                   " Driving through floodwater is deadly.", " It is not safe to drive through water.",
                                   " Tidak selamat untuk meredah air.", " Elakkan daripada meredah air banjir.",
                                   " Avoid crossing the flooded road."])
def test_warnings_against_going_into_water_are_fine(extra):
    assert critic.code_checks(GOOD + extra, facts(), EVIDENCE) == []


@pytest.mark.parametrize("text, problem", [
    ("Rantau Panjang: WATCH, 7.12 m. Confidence high. data.gov.my is stale.", "missing_level_name"),
    ("Rantau Panjang: WATCH (Waspada), 7.12 m. data.gov.my is stale.", "missing_confidence"),
    ("Rantau Panjang: WATCH (Alert), 7.12 m. Confidence high.", "missing_stale_note"),
    ("Rantau Panjang: ACT (Alert). Confidence high. data.gov.my is stale.", "wrong_verdict"),
    ("Rantau Panjang: WATCH (Alert), 9.99 m. Confidence high. data.gov.my is stale.", "unsupported"),
])
def test_each_missing_piece_is_a_problem(text, problem):
    assert problem in kinds(critic.code_checks(text, facts(), EVIDENCE))


def test_unresolved_conflict_must_be_mentioned():
    ev = dict(EVIDENCE, conflicts_unresolved=[{"quantity": "level", "reason": "equal reliability"}])
    assert "missing_conflict" in kinds(critic.code_checks(GOOD, facts(ev), ev))
    assert critic.code_checks(GOOD + " Two sources disagree on the level.", facts(ev), ev) == []


# -- Zetaris re-queries ---------------------------------------------------------------------------------------
@pytest.fixture
def run(tmp_path):
    trace.start_run("critic test", log_dir=tmp_path, quiet=True)
    yield tmp_path
    trace.end_run()


def fake_sql(raw_level, raw_at="2026-10-22 11:45:00.0", newest="2024-02-23 14:45:00"):
    def run_sql(sql, agent, purpose=None, limit=1000, budget_s=None):
        if "river_levels" in sql:
            assert "'_DPMS0003'" in sql and limit == 1
            recs = [{"station_key": "_DPMS0003", "level_m": raw_level, "observed_at": raw_at}]
        else:
            recs = [{"newest": newest}]
        return SimpleNamespace(records=recs, rows=[list(r.values()) for r in recs], query_hash="h", sql=sql)
    return run_sql


def test_requery_confirms_matching_reading_and_stale_source(run, monkeypatch):
    monkeypatch.setattr(zetaris, "run_sql", fake_sql(7.12))
    w = WorldModel()
    r = critic.requery(EVIDENCE, w, "r1")
    assert r["gauge"]["status"] == "confirmed" and r["problems"] == []
    assert r["flood_warning"]["stale"] is True and r["flood_warning"]["age_days"] > 900
    assert w.facts_about("source:veda:mygov_flood", "stale_confirmed")[0]["source"]["agent"] == "Critic"


def test_requery_mismatch_at_same_time_is_a_conflict(run, monkeypatch):
    monkeypatch.setattr(zetaris, "run_sql", fake_sql(7.60))
    r = critic.requery(EVIDENCE, None, "r1")
    assert r["gauge"]["status"] == "conflict" and kinds(r["problems"]) == ["conflict"]


def test_newer_raw_reading_is_noted_not_a_conflict(run, monkeypatch):
    monkeypatch.setattr(zetaris, "run_sql", fake_sql(7.30, raw_at="2026-10-22 12:00:00.0"))
    r = critic.requery(EVIDENCE, None, "r1")
    assert r["gauge"]["status"] == "newer" and r["problems"] == []


def test_stale_source_not_excluded_by_evidence_is_caught(run, monkeypatch):
    monkeypatch.setattr(zetaris, "run_sql", fake_sql(7.12))
    r = critic.requery(dict(EVIDENCE, cross_check={"status": "ok"}), None, "r1")
    assert "did not exclude" in r["problems"][0]["detail"]


# -- the review: model + code ---------------------------------------------------------------------------------
def model(decision, problems=(), fail=False):
    def llm(lane, messages, agent, **kw):
        assert messages[0]["content"] == critic.CRITIC_SYSTEM
        if fail:
            raise nightshift.NightshiftError(f"stub: {lane} lane down")
        data = {"decision": decision, "problems": list(problems), "fix": "say it plainly"}
        return SimpleNamespace(data=data, text=json.dumps(data))
    return llm


@pytest.fixture
def quiet_zetaris(monkeypatch):
    monkeypatch.setattr(zetaris, "run_sql", fake_sql(7.12))


def review(text, llm, world=None):
    return critic.review("Is Rantau Panjang at risk?", PLAN, EVIDENCE, FORECAST, {"text": text, "language": "en"},
                         world, llm=llm)


def test_code_problems_overrule_a_model_approval(run, quiet_zetaris):
    r = review("Rantau Panjang: WATCH. Drive through the water if you must.", model("approve"))
    assert r["decision"] == "reject" and "unsafe" in kinds(r["problems"])
    rec = [json.loads(x) for x in open(trace.current_run().path, encoding="utf-8")
           if '"critic.review"' in x][-1]
    assert rec["status"] == "needs_revision" and "code checks found problems" in rec["decision"]


def test_model_may_reject_a_draft_the_code_accepts(run, quiet_zetaris):
    r = review(GOOD, model("reject", [{"type": "unclear", "detail": "contradicts itself"}]))
    assert r["decision"] == "reject" and r["problems"][0]["by"] == "model" and r["fix"] == "say it plainly"


def test_without_nightshift_the_review_is_code_and_zetaris_only(run, quiet_zetaris):
    r = review(GOOD, model("approve", fail=True))
    assert r["decision"] == "approve" and r["checked_by"] == ["code", "zetaris"]


def test_review_is_written_to_the_world_model(run, quiet_zetaris):
    w = WorldModel()
    review(GOOD, model("approve"), world=w)
    stored = w.facts_about("place:veda:rantau_panjang", "critic_review")[-1]
    assert stored["value"] == {"round": 1, "decision": "approve", "problems": []}


# -- the loop: reject -> revise -> critique -------------------------------------------------------------------
GOOD_PLAN = {"intent": "risk_check", "user_type": "resident", "place_text": "Rantau Panjang",
             "sources": ["jps_levels", "open_meteo", "mygov_forecast"], "effort": "full", "language": "en"}


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    yield tmp_path
    gazetteer.clear_cache()


def scripted(reviews):
    """Plan, then drafts that copy the Forecast verdict, and the given sequence of Critic decisions."""
    calls = {"drafts": 0, "reviews": 0}

    def llm(lane, messages, agent, **kw):
        if messages[0]["content"] == coordinator.PLAN_SYSTEM:
            return SimpleNamespace(data=GOOD_PLAN, text="")
        if messages[0]["content"] == critic.CRITIC_SYSTEM:
            d = reviews[min(calls["reviews"], len(reviews) - 1)]
            calls["reviews"] += 1
            return SimpleNamespace(data={"decision": d, "problems": [] if d == "approve" else
                                         [{"type": "unclear", "detail": "too technical"}], "fix": "simpler"}, text="")
        calls["drafts"] += 1
        req = json.loads(messages[1]["content"])
        text = ["First explanation.", "Second explanation.", "Third explanation."][calls["drafts"] - 1]
        if calls["drafts"] > 1:
            assert req["critic_problems"] == ["unclear: too technical"]
            assert req["previous_explanation"].endswith("explanation.")
        return SimpleNamespace(data={"explanation": text}, text=text)
    llm.calls = calls
    return llm


def states(r):
    return [json.loads(x)["input_summary"] for x in open(r["trace"], encoding="utf-8") if '"action": "state"' in x]


def test_reject_then_revise_then_approve(offline):
    llm = scripted(["reject", "approve"])
    r = loop.run("Is Rantau Panjang at risk?", llm=llm, log_dir=offline, quiet=True)
    assert states(r) == ["plan", "gather", "forecast", "draft", "critique", "revise", "critique"]
    assert r["answer"]["explanation"] == "Second explanation." and r["answer"]["approved"]
    assert "Second explanation." in r["answer"]["text"] and r["answer"]["text"].startswith("WHAT TO DO NOW")
    assert [v["decision"] for v in r["reviews"]] == ["reject", "approve"]


def test_two_rejections_give_the_low_confidence_code_answer(offline):
    llm = scripted(["reject", "reject", "reject"])
    r = loop.run("Is Rantau Panjang at risk?", llm=llm, log_dir=offline, quiet=True)
    assert llm.calls["reviews"] == critic.MAX_REJECTIONS and len(r["reviews"]) == 2
    assert r["answer"]["low_confidence"] and r["answer"]["text"].startswith("Low confidence:")
    assert "approved" not in r["answer"]


# -- fast-lane fallback (decided 22 Oct night, added 23 Oct after the deep lane failed 0/3 twice) ---------------
def lanes_llm(deep_fails=True, fast_fails=False):
    calls = []

    def llm(lane, messages, agent, **kw):
        calls.append(lane)
        if (lane == "deep" and deep_fails) or (lane == "fast" and fast_fails):
            raise nightshift.NightshiftError(f"stub: {lane} lane provider_deadline")
        return SimpleNamespace(data={"decision": "approve", "problems": [], "fix": ""}, text="")
    llm.calls = calls
    return llm


@pytest.fixture
def deep_first(monkeypatch):
    monkeypatch.setenv("VEDA_CRITIC_LANE", "deep")


def test_fast_lane_is_the_default_critic_lane(run, quiet_zetaris, monkeypatch):
    monkeypatch.delenv("VEDA_CRITIC_LANE", raising=False)
    llm = lanes_llm(deep_fails=True)
    r = critic.review("q", PLAN, EVIDENCE, FORECAST, {"text": GOOD, "language": "en"}, llm=llm, budget_s=120)
    assert llm.calls == ["fast"] and r["critic_lane"] == "fast" and "model" in r["checked_by"]


@pytest.mark.parametrize("value, lane", [("deep", "deep"), ("FAST", "fast"), ("nonsense", "fast"), ("", "fast")])
def test_critic_lane_setting(monkeypatch, value, lane):
    monkeypatch.setenv("VEDA_CRITIC_LANE", value)
    assert critic.critic_lane() == lane


def test_deep_failure_falls_back_to_one_fast_lane_review(run, quiet_zetaris, deep_first):
    llm = lanes_llm()
    r = critic.review("q", PLAN, EVIDENCE, FORECAST, {"text": GOOD, "language": "en"}, llm=llm, budget_s=120)
    assert llm.calls == ["deep", "fast"] and r["critic_lane"] == "fast" and "model" in r["checked_by"]
    assert r["decision"] == "approve"


def test_no_fast_fallback_without_enough_time(run, quiet_zetaris, deep_first):
    llm = lanes_llm()
    r = critic.review("q", PLAN, EVIDENCE, FORECAST, {"text": GOOD, "language": "en"}, llm=llm, budget_s=5)
    assert llm.calls == ["deep"] and r["critic_lane"] is None and "model" not in r["checked_by"]


def test_both_lanes_down_means_code_and_zetaris_only(run, quiet_zetaris, deep_first):
    llm = lanes_llm(fast_fails=True)
    r = critic.review("q", PLAN, EVIDENCE, FORECAST, {"text": GOOD, "language": "en"}, llm=llm, budget_s=120)
    assert llm.calls == ["deep", "fast"] and r["checked_by"] == ["code", "zetaris"]
