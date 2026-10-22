"""B-15 tests: the self-healing ladder (backup gauge, last reading, INSUFFICIENT DATA) and the circuit breaker
(3 failures -> open 15 min -> half-open -> closed / reopened), plus 'rain fails, the gauges still answer'."""
from datetime import datetime, timedelta, timezone

import pytest

from app import card, gazetteer, trace
from app.agents import data_agent, forecast_agent
from app.engines.world_model import WorldModel
from app.engines.world_model.context import ContextBuilder

NOW = datetime(2026, 10, 23, 1, 0, tzinfo=timezone.utc)
MAP = {"kind": "zetaris", "at": "2026-10-22T00:00:00Z", "query_hash": "m", "agent": "Data & Reconciler", "run_id": "r"}
TH = {"normal_m": 0.4, "alert_m": 1.2, "warning_m": 1.6, "danger_m": 1.8}


@pytest.fixture(autouse=True)
def run(tmp_path):
    trace.start_run("healing test", log_dir=tmp_path, quiet=True)
    yield
    trace.end_run()


def reading(at):
    return {**MAP, "at": at, "query_hash": "r"}


def world(main_age_h=5, second_age_h=0.3, sentinel_age_h=0.3, backup_age_h=0.2):
    """Tumpat-like place: primary + secondary controlling gauges, one sentinel (Kusial) with a backup (Kusial Baru)."""
    w = WorldModel()
    w.upsert_entity("place", external_key={"system": "veda", "id": "tumpat"}, attrs={"name": "Tumpat"}, source=MAP)
    for key, name, extra in (("KM", "Kok Majid", {}), ("KJ", "Kuala Jambu", {}), ("KU", "Kusial", {}),
                             ("KB", "Kusial Baru", {"backup_of": "KU"})):
        w.upsert_entity("station", external_key={"system": "jps", "id": key}, source=MAP,
                        attrs={"name": name, **TH, **extra})
    w.relate("place:veda:tumpat", "controlled_by", "station:jps:KM", source=MAP)
    w.relate("place:veda:tumpat", "also_controlled_by", "station:jps:KJ", context="KJ", source=MAP)
    w.relate("station:jps:KU", "sentinel_for", "place:veda:tumpat", context="tumpat", attrs={"sort_order": 1}, source=MAP)
    for key, level, age in (("KM", 0.35, main_age_h), ("KJ", 1.1, second_age_h), ("KU", 5.0, sentinel_age_h),
                            ("KB", 5.1, backup_age_h)):
        at = (NOW - timedelta(hours=age)).isoformat().replace("+00:00", "Z")
        w.assert_fact(f"station:jps:{key}", "water_level_m", level, source=reading(at))
        w.assert_fact(f"station:jps:{key}", "band", "normal", source=reading(at))
    return w


def context(w):
    ctx = ContextBuilder(w).build("risk_check", "place:veda:tumpat", now=NOW)
    for g in ctx["gauges"] + ctx["sentinels"]:
        g["freshness"] = data_agent.freshness("jps_levels", g["age_minutes"])
    return ctx


def test_silent_primary_is_replaced_by_the_second_controlling_gauge():
    w = world(main_age_h=5)
    ctx = context(w)
    decisions = data_agent.heal(ctx, w, NOW)
    main = ctx["gauges"][0]
    assert main["name"] == "Kuala Jambu" and main["role"] == "controlling" and main["backup_for"] == "Kok Majid"
    assert decisions[0]["step"] == 2 and "Kok Majid silent since" in decisions[0]["note"]
    assert ctx["silent"][0]["name"] == "Kok Majid"


def test_silent_upstream_gauge_uses_its_mapping_backup():
    w = world(main_age_h=0.2, sentinel_age_h=6)
    ctx = context(w)
    decisions = data_agent.heal(ctx, w, NOW)
    s = ctx["sentinels"][0]
    assert s["name"] == "Kusial Baru" and s["backup_for"] == "Kusial" and s["travel_time_h"] is None
    assert [d["step"] for d in decisions] == [2]


def test_no_fresh_backup_keeps_the_last_reading_for_context_only():
    w = world(main_age_h=5, second_age_h=5)
    ctx = context(w)
    decisions = data_agent.heal(ctx, w, NOW)
    assert decisions[0]["step"] == 3 and "INSUFFICIENT DATA" in decisions[0]["note"]
    assert ctx["last_reading"]["level_m"] == 0.35 and ctx["gauges"][0]["name"] == "Kok Majid"   # not swapped


def test_fresh_gauges_are_left_alone():
    w = world(main_age_h=0.2)
    ctx = context(w)
    assert data_agent.heal(ctx, w, NOW) == [] and ctx["gauges"][0]["name"] == "Kok Majid"


def evidence_for(ctx, usable=True):
    return {"place": {"name": "Tumpat"}, "usable": usable, "clock": NOW.isoformat(), "context": ctx}


def test_backup_lowers_confidence_and_the_card_says_so_in_both_languages():
    w = world(main_age_h=5)
    ctx = context(w)
    data_agent.heal(ctx, w, NOW)
    plan = {"place": {"place_id": "tumpat", "name": "Tumpat"}, "effort": "full"}
    fc = forecast_agent.forecast(plan, evidence_for(ctx), None)
    assert fc["confidence"]["label"] == "medium" and "backup gauge in use (Kok Majid silent)" in fc["confidence"]["reasons"]
    c = card.build(plan, evidence_for(ctx), fc)
    assert "Note: Kok Majid has no reading since" in card.render(c, "en")
    assert "- using the backup gauge Kuala Jambu" in card.render(c, "en")
    assert "menggunakan stesen ganti Kuala Jambu" in card.render(c, "ms")


def test_insufficient_card_shows_the_last_reading_as_too_old():
    w = world(main_age_h=5, second_age_h=5)
    ctx = context(w)
    data_agent.heal(ctx, w, NOW)
    plan = {"place": {"place_id": "tumpat", "name": "Tumpat"}, "effort": "full"}
    fc = forecast_agent.forecast(plan, evidence_for(ctx, usable=False), None)
    c = card.build(plan, evidence_for(ctx, usable=False), fc)
    assert fc["verdict"] == "INSUFFICIENT_DATA"
    assert "Last reading: 0.35 m at" in card.render(c, "en") and "too old to use" in card.render(c, "en")
    assert "Bacaan terakhir: 0.35 m pada" in card.render(c, "ms")


# -- circuit breaker --------------------------------------------------------------------------------------------
def test_three_failures_open_the_circuit_for_15_minutes_then_half_open():
    w = WorldModel()
    for i in range(2):
        data_agent.record_call(w, "rain_and_forecast", False, NOW, "r")
        assert not data_agent.circuit_open(w, "rain_and_forecast", NOW)
    data_agent.record_call(w, "rain_and_forecast", False, NOW, "r")
    assert data_agent.circuit_open(w, "rain_and_forecast", NOW + timedelta(minutes=14))
    assert not data_agent.circuit_open(w, "rain_and_forecast", NOW + timedelta(minutes=16))      # half-open trial
    data_agent.record_call(w, "rain_and_forecast", False, NOW + timedelta(minutes=16), "r")      # trial fails
    assert data_agent.circuit_open(w, "rain_and_forecast", NOW + timedelta(minutes=20))          # open again
    data_agent.record_call(w, "rain_and_forecast", True, NOW + timedelta(minutes=40), "r")       # trial succeeds
    assert data_agent._breaker_state(w, "rain_and_forecast") == (0, None)


def test_a_success_resets_the_count():
    w = WorldModel()
    data_agent.record_call(w, "mygov_flood", False, NOW, "r")
    data_agent.record_call(w, "mygov_flood", False, NOW, "r")
    data_agent.record_call(w, "mygov_flood", True, NOW, "r")
    data_agent.record_call(w, "mygov_flood", False, NOW, "r")
    assert not data_agent.circuit_open(w, "mygov_flood", NOW)


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    yield
    gazetteer.clear_cache()


def test_open_jps_circuit_skips_the_queries_and_says_so(offline, monkeypatch):
    w = WorldModel()
    for _ in range(3):
        data_agent.record_call(w, "jps_levels", False, datetime.now(timezone.utc), "r")
    monkeypatch.setattr(data_agent, "fetch_all", lambda *a, **k: pytest.fail("JPS queries must be skipped"))
    pre = data_agent.prefetch(w)
    assert pre["error"].kind == "source_unavailable" and "circuit open" in str(pre["error"])


def test_rain_failure_does_not_take_the_gauges_down(offline, monkeypatch):
    real = data_agent.fetch_all

    def rain_fails(sqls, agent, workers=10, optional=()):
        out = real(sqls, agent, workers, optional)
        out[data_agent.READINGS_SQL[3]] = None                 # the rain + MET forecast view failed
        return out
    monkeypatch.setattr(data_agent, "fetch_all", rain_fails)
    w = WorldModel()
    plan = {"intent": "risk_check", "effort": "full", "place": gazetteer.resolve("Tumpat").place,
            "sources": ["jps_levels", "open_meteo", "mygov_forecast"]}
    ev = data_agent.gather(plan, w)
    assert ev["usable"] and ev["context"]["rain"] is None and ev["sources"]["open_meteo"]["status"] == "failed"
    assert data_agent._breaker_state(w, "rain_and_forecast")[0] == 1
