"""B-71(b): the Critic finds a gap (stale controlling gauge, upstream gauge without a fresh reading), asks the Data &
Reconciler, which re-reads / finds an alternative further UP the same river; the verdict is recomputed and the trace
says "verdict recomputed after the Critic's request: OLD → NEW"; with nothing found the card says what is missing."""
import json
from datetime import datetime

import pytest

from app import card, config, gazetteer, loop, progress, router, trace
from app.agents import data_agent
from app.engines.world_model import WorldModel

AT = datetime(2024, 6, 15, 10, 0, tzinfo=config.MYT)


@pytest.fixture
def sample(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    gazetteer.clear_cache()
    yield tmp_path
    gazetteer.clear_cache()


def _steps(r):
    return [json.loads(x) for x in open(r["trace"], encoding="utf-8")]


def _evidence(place, tmp):
    trace.start_run("t", log_dir=tmp, quiet=True)
    w = WorldModel()
    pre = data_agent.prefetch(w, now=AT, replay="synthetic_silent_upstream")
    plan = {"intent": "risk_check", "effort": "full", "place": gazetteer.resolve(place).place,
            "sources": ["jps_levels", "open_meteo"]}
    return w, data_agent.gather(plan, w, now=AT, pre=pre)


def test_gaps_are_the_stale_or_silent_controlling_and_upstream_gauges(sample):
    w, ev = _evidence("Pasir Mas", sample)
    try:
        gaps = data_agent.find_gaps(ev)
        assert [(g["kind"], g["gauge"]) for g in gaps] == [("upstream", "Sg. Kelantan di Air Mulih (F1)"),
                                                           ("upstream", "Sg. Kelantan di Kuala Krai (F1)")]
        assert all(g["why"] == "reading too old (360 min)" for g in gaps)
    finally:
        trace.end_run()


def test_data_agent_finds_fresh_gauges_further_up_the_same_river(sample):
    w, ev = _evidence("Pasir Mas", sample)
    try:
        got = data_agent.answer_request(data_agent.find_gaps(ev), ev, w)
        assert [(f["gauge"], f["for"]) for f in got["found"]] == [
            ("Sg. Kelantan di Kusial Baru (F1)", "Sg. Kelantan di Air Mulih (F1)"),
            ("Sg. Kelantan di Kg. Temangan (F1)", "Sg. Kelantan di Kuala Krai (F1)")]
        added = [s for s in ev["context"]["sentinels"] if s.get("requested_for")]
        assert {s["name"] for s in added} == {f["gauge"] for f in got["found"]} and not got["missing"]
        assert all(s["role"] == "sentinel" for s in added)          # never a new controlling gauge (flood logic)
    finally:
        trace.end_run()


def test_nothing_further_up_means_missing(sample):
    w, ev = _evidence("Rantau Panjang", sample)                  # Jenob is the top of the Golok chain
    try:
        got = data_agent.answer_request(data_agent.find_gaps(ev), ev, w)
        assert not got["found"] and got["missing"] == [
            {"gauge": "Sg. Golok di Kg. Jenob (F1)", "role": "upstream", "why": "reading too old (360 min)"}]
    finally:
        trace.end_run()


def test_loop_recomputes_the_verdict_once_and_says_so_live(sample):
    r = loop.run("Pasir Mas banjir tak esok?", log_dir=sample, quiet=True, replay="synthetic_silent_upstream", at=AT)
    steps = _steps(r)
    assert [s["action"] for s in steps].count("critic.request") == 1             # one request per run
    rec = next(s for s in steps if s["action"] == "verdict.recomputed")
    assert rec["output_summary"] == "verdict recomputed after the Critic's request: NORMAL → WATCH"
    assert progress.describe(rec) == "  verdict recomputed after the Critic's request: NORMAL → WATCH"
    ask = next(s for s in steps if s["action"] == "critic.request")
    assert ask["agent_name"] == "Critic" and ask["target_agent"] == "Data & Reconciler"
    assert progress.describe(ask).startswith("  Critic -> Data & Reconciler: need: fresh upstream reading")
    assert r["forecast"]["verdict"] == "WATCH"


def test_nothing_found_puts_the_gap_on_the_card(sample):
    r = loop.run("Rantau Panjang bahaya ke esok?", log_dir=sample, quiet=True, replay="synthetic_silent_upstream",
                 at=AT)
    assert "Tiada bacaan terkini dari Sg. Golok di Kg. Jenob (F1); VEDA mencari stesen hulu lain di sungai yang sama, " \
           "tiada ditemui." in r["answer"]["text"]
    assert not [s for s in _steps(r) if s["action"] == "verdict.recomputed"]


def test_quick_path_never_asks(sample, monkeypatch):
    monkeypatch.setattr(router, "data_triggers", lambda *a, **k: [])
    r = loop.run("Pasir Mas ok?", log_dir=sample, quiet=True, replay="synthetic_silent_upstream", at=AT)
    assert r["plan"]["effort"] == "quick"
    assert not [s for s in _steps(r) if s["action"] in ("critic.request", "data.request")]


def test_missing_line_is_never_trimmed():
    from tests.test_card import EVIDENCE, forecast
    c = card.build({}, EVIDENCE, forecast())
    c["missing"] = [{"gauge": "Sg. Contoh di Hulu (F1)", "role": "upstream", "why": "no reading"}]
    c["upstream"] = [{"gauge": f"Sg. Contoh {i}", "band": "danger", "rising": True, "arrives_in_h": None}
                     for i in range(6)]
    assert "Missing: no fresh reading from Sg. Contoh di Hulu (F1)" in card.render(c, "en")
