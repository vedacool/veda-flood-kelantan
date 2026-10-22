"""B-10 feature tests: ContextBuilder on a synthetic world (offline) and the real world from Zetaris (live)."""
import os
from datetime import datetime, timezone

import pytest

from app import trace
from app.engines.world_model import WorldModel
from app.engines.world_model.context import ContextBuilder

MAP = {"kind": "zetaris", "at": "2026-10-22T00:00:00Z", "query_hash": "map", "agent": "Data", "run_id": "r1"}
NOW = datetime(2026, 10, 22, 10, 0, tzinfo=timezone.utc)


def reading(at):
    return {**MAP, "at": at, "query_hash": "readings", "view": "veda.place_gauge_status"}


@pytest.fixture
def world():
    w = WorldModel()
    w.upsert_entity("place", external_key={"system": "veda", "id": "kb"}, attrs={"name": "Kota Bharu"}, source=MAP)
    for key, name in (("TD", "Tambatan Diraja"), ("KK", "Kuala Krai"), ("SAL", "Kg Salor")):
        w.upsert_entity("station", external_key={"system": "jps", "id": key}, source=MAP,
                        attrs={"name": name, "alert_m": 3.0, "danger_m": 5.0})
    w.relate("place:veda:kb", "controlled_by", "station:jps:TD", source=MAP)
    w.relate("station:jps:SAL", "sentinel_for", "place:veda:kb", context="kb", attrs={"sort_order": 10}, source=MAP)
    w.relate("station:jps:KK", "sentinel_for", "place:veda:kb", context="kb", attrs={"sort_order": 11}, source=MAP)
    w.relate("station:jps:KK", "travel_time", "station:jps:TD", context="TD",
             attrs={"lag_min_h": 9, "lag_max_h": 17, "lag_source": "Dec 2014", "status": "tentative"}, source=MAP)
    w.assert_fact("station:jps:TD", "water_level_m", 0.56, source=reading("2026-10-22T09:30:00Z"))
    w.assert_fact("station:jps:TD", "band", "below_normal", source=reading("2026-10-22T09:30:00Z"))
    w.assert_fact("station:jps:KK", "water_level_m", 18.07, source=reading("2026-10-21T18:00:00Z"))
    return w


def test_context_is_structured_with_provenance(world):
    ctx = ContextBuilder(world).build("risk_check", "place:veda:kb", now=NOW)
    assert ctx["found"] and ctx["place"]["name"] == "Kota Bharu"
    td = ctx["gauges"][0]
    assert td["station"] == "station:jps:TD" and td["level_m"] == 0.56 and td["age_minutes"] == 30
    assert td["provenance"]["query_hash"] == "readings" and td["selection_reason"]
    assert [s["name"] for s in ctx["sentinels"]] == ["Kg Salor", "Kuala Krai"]       # sort_order respected


def test_sentinel_travel_time_and_age_are_reported(world):
    ctx = ContextBuilder(world).build("risk_check", "place:veda:kb", now=NOW)
    kk = ctx["sentinels"][1]
    assert kk["travel_time_h"] == {"min": 9, "max": 17, "source": "Dec 2014", "status": "tentative"}
    assert kk["age_minutes"] == 16 * 60                       # an old reading is reported with its real age
    assert "station:jps:SAL" in ctx["trace"]["missing"]       # no reading at all -> listed as missing, not invented
    assert "rain" in ctx["trace"]["missing"]


def test_unknown_place_is_not_found(world):
    ctx = ContextBuilder(world).build("risk_check", "place:veda:nowhere", now=NOW)
    assert ctx["found"] is False and ctx["items"] == 0


@pytest.mark.skipif(os.getenv("VEDA_LIVE") != "1", reason="live Zetaris test: set VEDA_LIVE=1")
def test_live_world_from_zetaris_is_idempotent_and_builds_context(tmp_path):
    from dotenv import load_dotenv

    from app.engines.world_model.veda_ingest import build_network, ingest_readings
    load_dotenv(trace.ROOT / ".env")
    trace.start_run("live B-10 test", log_dir=tmp_path, quiet=True)
    try:
        w = WorldModel(storage=tmp_path / "world.sqlite", audit_jsonl=tmp_path / "worldmodel-audit.jsonl")
        net = build_network(w, "Data", "r-live")
        ingest_readings(w, "Data", "r-live")
        shape, events = w.state_shape_canonical(), len(w.store.events)
        build_network(w, "Data", "r-live")
        ingest_readings(w, "Data", "r-live")
        ctx = ContextBuilder(w).build("risk_check", "place:veda:rantau_panjang")
    finally:
        trace.end_run()
    assert net["stations"] == 16 and net["sources"] == 5
    assert w.state_shape_canonical() == shape and len(w.store.events) == events      # zero new events on re-run
    assert ctx["found"] and ctx["gauges"][0]["station"] == "station:jps:_DPMS0003"
    assert ctx["gauges"][0]["provenance"]["kind"] == "zetaris"
    assert any(s["station"] == "station:jps:_DTMH0008" for s in ctx["sentinels"])      # Kg Jenob upstream
