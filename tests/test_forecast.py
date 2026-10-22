"""B-16 tests: Forecast agent verdict rules, projection ranges, confidence, history and World Model read/write.

Evidence is built by hand here (same shape as the Data & Reconciler agent's output), so every rule edge is explicit.
"""
import pytest

from app import trace
from app.agents import coordinator, forecast_agent
from app.engines.world_model import WorldModel

TH = {"normal_m": 5.0, "alert_m": 7.0, "warning_m": 8.0, "danger_m": 9.0}
PLAN = {"place": {"place_id": "rantau_panjang", "name": "Rantau Panjang"}, "effort": "full"}


def gauge(level, ch1=None, ch3=None, role="controlling", band=None, freshness="fresh", ok=True, tide=False,
          lag=None, name="Rantau Panjang", station="station:jps:_DPMS0003"):
    band = band or ("danger" if level >= 9 else "warning" if level >= 8 else "alert" if level >= 7 else
                    "normal" if level >= 5 else "below_normal")
    g = {"station": station, "name": name, "role": role, "level_m": level, "band": band, "thresholds": dict(TH),
         "observed_at": "2026-10-22T10:30:00Z", "age_minutes": 20, "freshness": freshness,
         "health": {"ok": ok}, "change_1h_m": ch1, "change_3h_m": ch3, "tide_influenced": tide}
    if lag:
        g["travel_time_h"] = {"min": lag[0], "max": lag[1], "status": "tentative"}
    return g


def evidence(main, sentinels=(), rain=None, usable=True, secondary=None):
    return {"place": {"name": "Rantau Panjang"}, "usable": usable, "clock": "2026-10-22T10:50:00Z",
            "context": {"gauges": [main] + ([secondary] if secondary else []), "sentinels": list(sentinels),
                        "rain": rain}}


@pytest.fixture(autouse=True)
def run(tmp_path):
    trace.start_run("forecast test", log_dir=tmp_path, quiet=True)
    yield
    trace.end_run()


def verdict(ev, plan=PLAN, world=None):
    return forecast_agent.forecast(plan, ev, world)


# -- level rules ----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("level, expected", [(4.0, "NORMAL"), (6.99, "NORMAL"), (7.0, "WATCH"), (8.0, "PREPARE"),
                                             (9.0, "ACT"), (11.0, "ACT")])
def test_level_thresholds(level, expected):
    assert verdict(evidence(gauge(level, 0.0, 0.0)))["verdict"] == expected


def test_jps_level_name_comes_with_the_verdict():
    fc = verdict(evidence(gauge(7.2, 0.0, 0.0)))
    assert fc["level_name"] == {"en": "Alert", "ms": "Waspada"}


# -- fail-safe (B-41) -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("ev", [
    evidence(gauge(4.0), usable=False),
    evidence({**gauge(4.0), "thresholds": {"normal_m": None, "alert_m": None, "warning_m": None, "danger_m": None}}),
    {"place": {"name": "X"}, "usable": True, "context": {"gauges": [], "sentinels": []}},
])
def test_missing_or_stale_data_is_never_normal(ev):
    fc = verdict(ev)
    assert fc["verdict"] == "INSUFFICIENT_DATA" and fc["confidence"]["label"] == "low"


# -- trend ----------------------------------------------------------------------------------------------------
def test_projection_is_a_range_from_two_rates():
    fc = verdict(evidence(gauge(6.0, 0.1, 0.6)))                 # 0.1 m/h and 0.2 m/h
    c = fc["controlling"][0]
    assert c["rate_m_per_h"] == {"min": 0.1, "max": 0.2}
    assert c["projection_m"]["6h"] == {"min": 6.6, "max": 7.2}
    assert c["hours_to"]["alert"] == {"earliest": 5.0, "latest": 10.0}


def test_reaching_alert_within_24h_is_watch_and_danger_within_12h_is_act():
    assert verdict(evidence(gauge(6.0, 0.1, 0.3)))["verdict"] == "WATCH"           # alert in 10 h
    assert verdict(evidence(gauge(8.5, 0.05, 0.15)))["verdict"] == "ACT"           # danger in 10 h (warning now)
    assert verdict(evidence(gauge(6.0, 0.15, 0.45)))["verdict"] == "PREPARE"       # danger in 20 h


def test_falling_river_has_no_time_to_threshold():
    c = verdict(evidence(gauge(6.0, -0.1, -0.3)))["controlling"][0]
    assert c["hours_to"] == {} and c["projection_m"]["24h"]["max"] < 6.0


def test_rising_fast_moves_up_one_level():
    g = {**gauge(5.0, 0.35, 0.3), "thresholds": {"normal_m": 4.0, "alert_m": 20.0, "warning_m": 22.0, "danger_m": 25.0}}
    fc = verdict(evidence(g))                                  # thresholds > 24 h away: only the fast rise fires
    assert fc["verdict"] == "WATCH" and [t["rule"] for t in fc["triggers"]] == ["rising-fast"]


def test_tide_influenced_gauge_is_judged_on_level_only():
    fc = verdict(evidence(gauge(6.0, 0.4, 0.9, tide=True)))
    c = fc["controlling"][0]
    assert fc["verdict"] == "NORMAL" and c["projection_m"] == {} and not c["rising_fast"]
    assert "tide" in c["trend_note"] and "tide" in " ".join(fc["confidence"]["reasons"])


def test_quick_mode_uses_current_levels_only():
    fc = verdict(evidence(gauge(6.0, 0.1, 0.3)), plan={**PLAN, "effort": "quick"})
    assert fc["mode"] == "now" and fc["verdict"] == "NORMAL" and fc["controlling"][0]["projection_m"] == {}


# -- upstream and rain ----------------------------------------------------------------------------------------
def test_upstream_sentinel_at_danger_is_prepare_with_travel_time():
    up = gauge(26.0, 0.2, 0.6, role="sentinel", band="danger", lag=(9, 17), name="Kuala Krai", station="s:kk")
    fc = verdict(evidence(gauge(4.0, 0.0, 0.0), sentinels=[up]))
    assert fc["verdict"] == "PREPARE" and "9-17 h" in fc["triggers"][0]["reason"]
    assert fc["upstream"][0]["rising"] is True and "tentative" in " ".join(fc["confidence"]["reasons"])


def test_stale_sentinel_is_ignored_not_trusted():
    up = gauge(26.0, role="sentinel", band="danger", freshness="stale", name="Kuala Krai", station="s:kk")
    fc = verdict(evidence(gauge(4.0, 0.0, 0.0), sentinels=[up]))
    assert fc["verdict"] == "NORMAL" and fc["upstream"][0]["status"] == "no fresh reading"


@pytest.mark.parametrize("rain, expected", [
    ({"rain_next_24h_mm": 20, "rain_next_72h_mm": 120, "rain_past_7d_mm": 160, "freshness": "fresh"}, "WATCH"),
    ({"rain_next_24h_mm": 20, "rain_next_72h_mm": 120, "rain_past_7d_mm": 50, "freshness": "fresh"}, "NORMAL"),
    ({"rain_next_24h_mm": 160, "rain_next_72h_mm": 170, "rain_past_7d_mm": 0, "freshness": "fresh"}, "PREPARE"),
    ({"rain_next_24h_mm": 50, "rain_next_72h_mm": 210, "rain_past_7d_mm": 0, "freshness": "fresh"}, "PREPARE"),
])
def test_rain_triggers(rain, expected):
    assert verdict(evidence(gauge(4.0, 0.0, 0.0), rain=rain))["verdict"] == expected


# -- confidence -----------------------------------------------------------------------------------------------
def test_confidence_drops_for_aging_data_and_disagreeing_trends():
    good = verdict(evidence(gauge(4.0, 0.0, 0.0)))["confidence"]
    worse = verdict(evidence(gauge(4.0, 0.2, -0.6, freshness="aging")))["confidence"]
    assert good["label"] == "high" and worse["score"] < good["score"] and len(worse["reasons"]) == 2


def test_unusable_second_controlling_gauge_lowers_confidence():
    second = gauge(1.0, freshness="stale", name="Kuala Jambu", role="controlling_secondary", station="s:kj")
    fc = verdict(evidence(gauge(4.0, 0.0, 0.0), secondary=second))
    assert "second controlling gauge" in " ".join(fc["confidence"]["reasons"])


# -- World Model ----------------------------------------------------------------------------------------------
def test_reads_historic_peaks_and_writes_forecast_to_the_world():
    w = WorldModel()
    src = {"kind": "zetaris", "at": "2026-10-22T00:00:00Z", "agent": "Data & Reconciler", "run_id": "r"}
    w.assert_fact("station:jps:_DPMS0003", "historic_peaks", [
        {"event": "Nov 2024", "peak_m": 11.43, "source_type": "news", "reconstructed": False},
        {"event": "Dec 2014", "peak_m": 10.84, "source_type": "official", "reconstructed": False}], source=src)
    fc = verdict(evidence(gauge(7.2, 0.1, 0.3)), world=w)
    assert fc["history"][0] == {"event": "Nov 2024", "peak_m": 11.43, "above_now_m": 4.23, "source": "news",
                                "reconstructed": False}
    assert fc["bigger_than_2014"] is False
    stored = w.facts_about("place:veda:rantau_panjang", "forecast")[-1]
    assert stored["value"]["verdict"] == fc["verdict"] and stored["source"]["agent"] == "Forecast"


# -- Coordinator uses the verdict -----------------------------------------------------------------------------
def test_draft_must_state_the_forecast_verdict_and_no_other():
    fc = verdict(evidence(gauge(7.2, 0.0, 0.0)))
    facts = coordinator.facts_for_model(evidence(gauge(7.2, 0.0, 0.0)), fc)
    assert coordinator.draft_problem("Rantau Panjang: WATCH (Waspada), 7.2 m.", facts) is None
    assert "not the Forecast agent's" in coordinator.draft_problem("Status ACT now.", facts)
    assert "does not state" in coordinator.draft_problem("The river is 7.2 m.", facts)


def test_fallback_answer_leads_with_the_verdict():
    ev = evidence(gauge(7.2, 0.01, 0.03))
    text = coordinator.fallback_answer(coordinator.facts_for_model(ev, verdict(ev)))
    assert text.startswith("Rantau Panjang: WATCH (JPS level: Alert), confidence")
    assert "Projected level in 24 h" in text
