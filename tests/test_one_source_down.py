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


def test_place_lookup_retries_the_known_names_next_time(down, monkeypatch):
    from app import trace
    trace.start_run("t", log_dir=down, quiet=True)
    assert gazetteer.resolve("Tumpat").status == "found"
    monkeypatch.setattr(gazetteer.zetaris, "run_sql", REAL)                   # data.gov.my is back
    assert gazetteer.resolve("Machang").known == "Machang"                    # not cached as "unknown"
    trace.end_run("success")
