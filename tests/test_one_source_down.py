"""Husaini 23 Oct: one source failing never blocks the river answer. Found live 23 Oct: data.gov.my answered HTTP 429
and the place lookup (known Kelantan names come from the MetMalaysia list) stopped the whole run with "cannot reach
data". Now: data.gov.my 429 -> the place is still found, the river answer is still produced, Open-Meteo rain still
arrives on its own, and the MetMalaysia sources are marked "not checked" on the card and in the trace."""
import json
from types import SimpleNamespace

import pytest

from app import gazetteer, loop
from app.adapters import nightshift, zetaris
from app.agents import data_agent
from app.engines.world_model import WorldModel
from app.engines.world_model import veda_ingest

MYGOV = ("forecast_kelantan", "mygov_", "place_risk_inputs", "station_risk_inputs")
REAL = zetaris.run_sql


def mygov_429(sql, agent, purpose=None, **kw):
    if any(t in sql for t in MYGOV):
        raise zetaris.ZetarisError("source_unavailable", "REST API call failed: Server returned HTTP response code: "
                                                         "429 for URL: https://api.data.gov.my/weather/forecast/")
    if sql == veda_ingest.PLACE_RAIN_SQL:            # no recording of the rain-only query: stand in with one row
        return SimpleNamespace(sql=sql, query_hash="rainonly", records=[
            {"place_id": "tumpat", "rain_point": "tumpat", "rain_past_24h_mm": 3.0, "rain_past_7d_mm": 20.0,
             "rain_next_24h_mm": 12.5, "rain_next_72h_mm": 30.0, "max_prob_next_24h_pct": 60}])
    return REAL(sql, agent, purpose, **kw)


@pytest.fixture
def down(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    monkeypatch.setattr(zetaris, "run_sql", mygov_429)
    for mod in (gazetteer, data_agent, veda_ingest):
        if hasattr(mod, "zetaris"):
            monkeypatch.setattr(mod.zetaris, "run_sql", mygov_429)
    gazetteer.clear_cache()
    yield tmp_path
    gazetteer.clear_cache()


def llm(lane, messages, agent, **kw):
    raise nightshift.NightshiftError("no model in this test")


@pytest.mark.parametrize("question, lang", [("Is Tumpat safe tomorrow?", "en"), ("Tumpat banjir tak esok?", "ms")])
def test_data_gov_my_429_still_gives_the_river_answer(down, question, lang):
    r = loop.run(question, llm=llm, world=WorldModel(), log_dir=down, quiet=True)
    text = r["answer"]["text"]
    assert r["forecast"] is not None and r["forecast"]["verdict"] != "INSUFFICIENT_DATA"
    assert not text.startswith(("VEDA cannot reach", "VEDA tidak dapat mencapai"))
    assert {"en": "Not checked: MetMalaysia warnings and forecast (data.gov.my could not be read).",
            "ms": "Tidak disemak: amaran dan ramalan MetMalaysia (data.gov.my tidak dapat dibaca)."}[lang] in text
    ev = r["evidence"]
    assert ev["sources"]["mygov_forecast"]["status"] == "not_checked"
    assert ev["sources"]["mygov_warning"]["status"] == "not_checked"
    assert ev["context"]["rain"]["rain_next_24h_mm"] == 12.5                  # rain read on its own
    steps = [json.loads(x) for x in open(r["trace"], encoding="utf-8")]
    assert any(s["action"] == "gazetteer.known" and s["output_summary"].startswith("not checked") for s in steps)
    assert not any(s["action"] == "data.unavailable" for s in steps)


def test_place_lookup_retries_the_known_names_after_15_minutes(down, monkeypatch):
    from app import trace
    trace.start_run("t", log_dir=down, quiet=True)
    assert gazetteer.resolve("Tumpat").status == "found"
    monkeypatch.setattr(gazetteer.zetaris, "run_sql", REAL)                   # data.gov.my is back
    assert gazetteer.resolve("Machang").known is None                         # < 15 min: not asked again yet
    later = gazetteer.time.monotonic() + gazetteer.KNOWN_RETRY_S + 1
    monkeypatch.setattr(gazetteer.time, "monotonic", lambda: later)
    assert gazetteer.resolve("Machang").known == "Machang"                    # retried: not cached as "unknown"
    trace.end_run("success")


# -- Husaini 23 Oct: one breaker per SOURCE - a long data.gov.my outage never trips Open-Meteo ---------------------
def test_long_data_gov_my_outage_keeps_rain_and_recovers(down, monkeypatch):
    """10 questions over 30 min while data.gov.my answers 429: rain keeps arriving, MetMalaysia says 'not checked',
    the data.gov.my breaker opens (so data.gov.my is not hammered) and Open-Meteo's never counts a failure; when
    data.gov.my is back, the half-open trial closes its breaker."""
    from datetime import datetime, timedelta, timezone
    from app import trace
    t0 = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    clock = {"now": t0}

    class Wall(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]
    monkeypatch.setattr(data_agent, "datetime", Wall)
    asked = []

    def counting(sql, agent, purpose=None, **kw):
        if any(t in sql for t in MYGOV):
            asked.append(clock["now"])
        return mygov_429(sql, agent, purpose, **kw)
    monkeypatch.setattr(zetaris, "run_sql", counting)
    w = WorldModel()
    trace.start_run("long outage", log_dir=down, quiet=True)
    try:
        plan = {"intent": "risk_check", "effort": "full", "place": gazetteer.resolve("Tumpat").place,
                "sources": ["jps_levels", "open_meteo", "mygov_forecast", "mygov_warning"]}
        for i in range(10):                                            # every 3 min for 30 min
            clock["now"] = t0 + timedelta(minutes=3 * i)
            ev = data_agent.gather(plan, w, pre=data_agent.prefetch(w))
            assert ev["usable"] and ev["context"]["rain"]["rain_next_24h_mm"] == 12.5, i
            assert ev["sources"]["mygov_forecast"]["status"] == "not_checked", i
            assert ev["sources"]["mygov_warning"]["status"] == "not_checked", i
            assert data_agent._breaker_state(w, "open_meteo") == (0, None), i
        fails, until = data_agent._breaker_state(w, "data_gov_my")
        assert until is not None and fails >= 3                        # open: data.gov.my left alone
        assert sorted({(a - t0).seconds // 60 for a in asked}) == [0, 3, 6, 21]   # 3 fails, open; one trial at 21 min
        monkeypatch.setattr(zetaris, "run_sql", REAL)                  # data.gov.my is back
        clock["now"] = until + timedelta(minutes=1)                    # half-open: one trial call
        ev = data_agent.gather(plan, w, pre=data_agent.prefetch(w))
        assert data_agent._breaker_state(w, "data_gov_my") == (0, None)
        assert ev["sources"]["mygov_warning"]["status"] != "not_checked"
    finally:
        trace.end_run("success")
