"""Part 7 (B-14): Nemotron's own level in the Critic's review - code decides; the AI can only raise."""
from app import view
from app.agents import critic

META = {"vs_alert": {"raise": True, "level": "WATCH", "text": {"en": "G: 0.6 m above Alert", "ms": "G: 0.6 m di atas"}},
        "upstream.1": {"raise": True, "level": None, "text": {"en": "Kg. Jenob (Normal, rising)", "ms": "Kg. Jenob (Normal, naik)"}},
        "next_24h": {"raise": True, "level": "ACT", "text": {"en": "G: may pass Danger", "ms": "G: mungkin melepasi Bahaya"}},
        "excluded.1": {"raise": False, "level": None, "text": {"en": "left out", "ms": "diketepikan"}}}


def j(ai, reasons, conf="high", code="WATCH"):
    return critic.judge({"ai_level": ai, "reasons": reasons, "confidence": conf}, code, META)


def test_a_valid_raise_goes_one_level_up():
    out = j("PREPARE", ["upstream.1"])
    assert out["status"] == "raised" and out["final"] == "PREPARE" and not out["capped"]
    assert out["reasons"][0]["text"]["ms"] == "Kg. Jenob (Normal, naik)"


def test_a_raise_is_capped_at_one_level_unless_a_cited_fact_stands_higher():
    assert j("ACT", ["upstream.1"], code="NORMAL")["final"] == "WATCH"                    # +1 only
    capped = j("ACT", ["upstream.1"], code="NORMAL")
    assert capped["capped"] and capped["ai_level"] == "ACT"
    assert j("ACT", ["next_24h"], code="NORMAL")["final"] == "ACT"                          # the fact stands at ACT


def test_never_lower_and_never_changes_cant_confirm():
    low =j("NORMAL", ["vs_alert"])
    assert low["status"] == "lower" and low["final"] == "WATCH" and "keeps the safer level" in low["why"]
    assert j("INSUFFICIENT_DATA", [])["status"] == "lower" and j("INSUFFICIENT_DATA", [])["final"] == "WATCH"
    for ai in ("NORMAL", "ACT"):
        out = j(ai, ["next_24h"], code="INSUFFICIENT_DATA")
        assert out["status"] == "ignored" and out["final"] == "INSUFFICIENT_DATA"


def test_a_raise_must_cite_real_facts_that_can_support_it_with_enough_confidence():
    assert "not given: upstream.7" in j("PREPARE", ["upstream.7"])["why"]
    assert "cannot support a raise: excluded.1" in j("PREPARE", ["excluded.1"])["why"]
    assert j("PREPARE", [])["status"] == "ignored"
    assert j("PREPARE", ["upstream.1", "vs_alert", "next_24h"])["status"] == "ignored"         # at most 2
    assert j("PREPARE", ["upstream.1"], conf="low")["status"] == "ignored"
    assert j("PREPARE", ["upstream.1"], conf=None)["status"] == "ignored"
    for bad in ({}, {"ai_level": "DANGER"}, None, "PREPARE"):
        out = critic.judge(bad, "WATCH", META)
        assert out["status"] == "ignored" and out["final"] == "WATCH"


def test_agreement_is_recorded():
    out = j("WATCH", ["vs_alert"])
    assert out["status"] == "agreed" and out["final"] == "WATCH"


def test_judge_facts_ids_and_raise_rules():
    card = {"place": "Kota Bharu", "verdict": "WATCH", "level_name": {"en": "Alert", "ms": "Waspada"},
            "confidence": "high", "gauge": {"name": "Sg. Kelantan di Jambatan Guillemard", "level_m": 3.65,
                                             "read_at": "18:00"},
            "comparison": {"alert": 0.65}, "thresholds": {"alert": 3.0}, "trend": "falling",
            "upstream": [{"gauge": "Kuala Krai", "band": "warning", "rising": True}],
            "warnings": [], "excluded": "2024-10-01", "conflicts": [], "rain_up": None}
    facts, meta = critic.judge_facts(card, None, "en")
    assert {"verdict", "vs_alert", "upstream.1", "trend", "excluded.1"} <= set(facts)
    assert meta["vs_alert"]["raise"] and meta["vs_alert"]["level"] == "WATCH"
    assert not meta["trend"]["raise"]                                  # falling cannot support a raise
    assert meta["upstream.1"]["raise"] and not meta["excluded.1"]["raise"]
    assert meta["vs_alert"]["text"]["en"].startswith("Sg. Kelantan di Jambatan Guillemard: ")


def test_the_line_under_the_verdict_uses_the_code_written_fact_text():
    fc = {"verdict": "PREPARE", "triggers": [
        {"level": "WATCH", "rule": "level>=alert", "reason": "x"},
        {"level": "PREPARE", "rule": "ai-judgement", "reason": "y",
         "texts": {"en": "Kg. Jenob (Normal, rising)", "ms": "Kg. Jenob (Normal, naik)"}}]}
    card = {"verdict": "PREPARE", "gauge": {"name": "g"}}
    assert view._line(card, fc, "en") == ("Nemotron weighed all sources and raised this to Get ready: "
                                          "Kg. Jenob (Normal, rising).")
    assert view._line(card, fc, "ms").startswith("Nemotron menimbang semua sumber dan menaikkan tahap ini ke Bersedia")


def test_offline_details_say_live_mode_only_never_a_stand_in_result():
    stand_in = {"status": "raised", "ai_level": "PREPARE", "code_level": "WATCH", "final": "PREPARE"}
    row = view.judgement_row({"sample_mode": True, "ai_judgement": stand_in})
    assert row == {"status": "live_only", "text": view.JUDGE["live_only"]}
    live = view.judgement_row({"sample_mode": False, "ai_judgement": stand_in})
    assert live["final"]["en"] == "Final: Get ready" and live["rules"]["ms"] == "Peraturan: Terus berjaga-jaga"


def test_the_page_shows_the_judgement_row_and_the_critics_checks():
    from app import config
    page = (config.ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="a-judge"' in page and "const jg = v.judgement;" in page and 'details class="checks"' in page
    live = (config.ROOT / "app" / "web" / "live.html").read_text(encoding="utf-8")
    assert '"critic.ai_judgement"' in live


def test_offline_api_says_live_only(tmp_path, monkeypatch):
    from app import gazetteer, loop, main
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    r = loop.run("Is Kota Bharu at risk in the next two days?", quiet=True, log_dir=tmp_path, default_scene=True)
    out = main.result_json(r)
    assert r["plan"]["effort"] == "full" and out["ai_judgement"] == {"status": "live_only"}
    assert out["view"]["judgement"]["status"] == "live_only"
    how = [row for row in out["how"]["rows"] if row.get("checks")]
    assert how and "never 'go into the water'" in how[0]["checks"]
