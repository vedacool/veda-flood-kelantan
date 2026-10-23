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
    assert "stale but the evidence says current" in r["problems"][0]["detail"]      # a real disagreement


# -- the review: model + code ---------------------------------------------------------------------------------
def model(decision, problems=(), fail=False):
    def llm(lane, messages, agent, **kw):
        assert messages[0]["content"] in (critic.CRITIC_SYSTEM, critic.SMALL_SYSTEM)
        if fail:
            raise nightshift.NightshiftError(f"stub: {lane} lane down")
        data = {"decision": decision, "problems": list(problems), "fix": "say it plainly",
                "ok": decision == "approve", "reason": "say it plainly"}
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
        if messages[0]["content"] in (critic.CRITIC_SYSTEM, critic.SMALL_SYSTEM):
            d = reviews[min(calls["reviews"], len(reviews) - 1)]
            calls["reviews"] += 1
            return SimpleNamespace(data={"decision": d, "problems": [] if d == "approve" else
                                         [{"type": "unclear", "detail": "too technical"}], "fix": "simpler",
                                         "ok": d == "approve", "reason": "too technical"}, text="")
        calls["drafts"] += 1
        req = json.loads(messages[1]["content"])
        text = ["First explanation.", "Second explanation.", "Third explanation."][calls["drafts"] - 1]
        if calls["drafts"] > 1:
            assert req["critic_problems"] == ["unsupported: too technical"]     # the small call's reason
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


# -- B-85: the AI review on Super VL only; no Lightning fallback -------------------------------------------
def lanes_llm(deep_fails=True, fast_fails=False):
    calls = []

    def llm(lane, messages, agent, **kw):
        calls.append(lane)
        if (lane == "deep" and deep_fails) or (lane == "fast" and fast_fails):
            raise nightshift.NightshiftError(f"stub: {lane} lane provider_deadline")
        return SimpleNamespace(data={"decision": "approve", "problems": [], "fix": ""}, text="")
    llm.calls = calls
    return llm


def test_critic_reviews_on_super_vl_only(run, quiet_zetaris, monkeypatch):
    """B-85: the AI review runs on the deep lane (Super VL by name); VEDA_CRITIC_LANE no longer picks Lightning."""
    monkeypatch.setenv("VEDA_CRITIC_LANE", "fast")
    llm = lanes_llm(deep_fails=False)
    r = critic.review("q", PLAN, EVIDENCE, FORECAST, {"text": GOOD, "language": "en"}, llm=llm, budget_s=120)
    assert llm.calls == ["deep"] and r["critic_lane"] == "deep" and "model" in r["checked_by"]


def test_failed_review_means_code_and_zetaris_only_never_lightning(run, quiet_zetaris):
    llm = lanes_llm(deep_fails=True)
    r = critic.review("q", PLAN, EVIDENCE, FORECAST, {"text": GOOD, "language": "en"}, llm=llm, budget_s=120)
    assert llm.calls == ["deep"] and r["checked_by"] == ["code", "zetaris"] and r["critic_lane"] is None


def test_review_is_capped_at_45_s(run, quiet_zetaris):
    seen = []

    def llm(lane, messages, agent, **kw):
        seen.append(kw.get("budget_s"))
        return SimpleNamespace(data={"decision": "approve", "problems": [], "fix": ""}, text="")
    critic.review("q", PLAN, EVIDENCE, FORECAST, {"text": GOOD, "language": "en"}, llm=llm, budget_s=120)
    assert seen and seen[0] <= critic.REVIEW_CAP_S == 45


# -- the small facts-only AI review (Husaini 23 Oct) -----------------------------------------------------------
from app import card as card_mod                                   # noqa: E402

EXPL = "The river is just above the Alert level."


@pytest.fixture
def traced(tmp_path):
    trace.start_run("small review test", log_dir=tmp_path, quiet=True)
    yield
    trace.end_run()


def small_answer(explanation=EXPL):
    c = card_mod.build({"place": {"name": "Rantau Panjang"}}, EVIDENCE, FORECAST)
    return {"text": card_mod.render(c, "en", explanation), "language": "en", "card": c,
            "explanation": explanation, "drafted_by": "llm"}


def small_llm(replies):
    """replies: list of 'ok' / 'no' / 'fail'; records every request."""
    seen = []

    def llm(lane, messages, agent, **kw):
        seen.append({"system": messages[0]["content"], "user": messages[1]["content"], "kw": kw})
        r = replies[min(len(seen) - 1, len(replies) - 1)]
        if r == "fail":
            raise nightshift.NightshiftError("empty response")
        return SimpleNamespace(data={"ok": r == "ok", "reason": "says falling, facts say rising"}, text="")
    llm.seen = seen
    return llm


def test_small_review_sends_only_key_facts_and_the_explanation():
    llm = small_llm(["ok"])
    assert critic._small_review(small_answer(), FORECAST, llm, 60, "fast") == ("approve", [], "")
    req = llm.seen[0]
    assert req["system"] == critic.SMALL_SYSTEM and req["kw"]["max_tokens"] == 4096 and not req["kw"]["thinking"]
    body = json.loads(req["user"])
    assert set(body) == {"FACTS", "EXPLANATION"} and body["EXPLANATION"] == EXPL
    assert body["FACTS"]["verdict"] == "WATCH" and "question" not in req["user"]


def test_small_review_rejection_carries_the_reason():
    decision, problems, fix = critic._small_review(small_answer(), FORECAST, small_llm(["no"]), 60, "fast")
    assert decision == "reject" and fix == "says falling, facts say rising"
    assert problems == [{"type": "unsupported", "detail": "says falling, facts say rising", "by": "model"}]


def test_fast_failures_are_retried_twice_then_given_up(traced):
    llm = small_llm(["fail", "fail", "ok"])
    assert critic._small_review(small_answer(), FORECAST, llm, 60, "fast")[0] == "approve" and len(llm.seen) == 3
    llm = small_llm(["fail"])
    with pytest.raises(nightshift.NightshiftError):
        critic._small_review(small_answer(), FORECAST, llm, 60, "fast")
    assert len(llm.seen) == 3                                          # 1 try + 2 retries


def test_a_slow_failure_is_not_retried(monkeypatch, traced):
    monkeypatch.setattr(critic, "FAST_FAIL_S", -1)                     # every failure counts as slow (a 45 s cut-off)
    llm = small_llm(["fail", "ok"])
    with pytest.raises(nightshift.NightshiftError):
        critic._small_review(small_answer(), FORECAST, llm, 60, "fast")
    assert len(llm.seen) == 1


def test_no_retry_without_budget_left(traced):
    llm = small_llm(["fail", "ok"])
    with pytest.raises(nightshift.NightshiftError):
        critic._small_review(small_answer(), FORECAST, llm, 5, "fast")   # less than FAST_FAIL_S left
    assert len(llm.seen) == 1


def test_card_without_explanation_skips_the_ai_review(tmp_path):
    trace.start_run("t", log_dir=tmp_path, quiet=True)
    try:
        r = critic.review("q", {}, EVIDENCE, FORECAST, small_answer(None), llm=small_llm(["ok"]),
                          recheck_data=False)
    finally:
        trace.end_run()
    assert "model" not in r["checked_by"]
