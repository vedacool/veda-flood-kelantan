"""Tests for B-08 Zetaris views: db/views/*.sql and scripts/setup_views.py (offline + live with VEDA_LIVE=1)."""
import importlib.util
import os

import pytest

from app import trace
from app.adapters import zetaris

ROOT = trace.ROOT
spec = importlib.util.spec_from_file_location("setup_views", ROOT / "scripts" / "setup_views.py")
setup_views = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup_views)

live = pytest.mark.skipif(os.getenv("VEDA_LIVE") != "1", reason="live Zetaris test: set VEDA_LIVE=1")


def test_every_view_file_is_created_and_in_dependency_order():
    files = {p.stem for p in (ROOT / "db" / "views").glob("*.sql")}
    assert files == set(setup_views.ORDER)
    assert setup_views.ORDER[-1] == "station_risk_inputs"          # depends on the other three


@pytest.mark.parametrize("name", setup_views.ORDER)
def test_view_is_one_read_only_select_and_allowed_ddl(name):
    body = setup_views.view_body(name)
    assert zetaris.read_only_problem(body) is None
    assert zetaris.ddl_problem(setup_views.view_sql(name), setup=True) is None
    assert zetaris.ddl_problem(setup_views.view_sql(name)) is not None   # agents may not replace views


def test_time_handling_is_explicit():
    rain = (ROOT / "db" / "views" / "rain_24h_by_point.sql").read_text(encoding="utf-8")
    assert "Asia/Kuala_Lumpur" in rain and "COALESCE(r.location_id, 0)" in rain


def expected_band(level, normal, alert, warning, danger):
    if level is None:
        return "no_reading"
    for name, threshold in (("danger", danger), ("warning", warning), ("alert", alert), ("normal", normal)):
        if threshold is not None and level >= threshold:
            return name
    return "below_normal" if normal is not None else "unknown"


@pytest.fixture
def live_run(tmp_path):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    trace.start_run("live B-08 test", log_dir=tmp_path, quiet=True)
    yield
    trace.end_run()


@live
def test_view_row_counts(live_run):
    counts = setup_views.smoke_check()
    assert counts["river_status_latest"] == 36
    assert counts["rain_24h_by_point"] == 7
    assert counts["station_risk_inputs"] == 5
    assert counts["forecast_kelantan"] > 0


@live
def test_band_matches_thresholds_for_every_gauge(live_run):
    rows = zetaris.run_sql("SELECT station_key, level_m, normal_m, alert_m, warning_m, danger_m, band, age_minutes "
                           "FROM veda.river_status_latest", agent="Test").rows
    for key, level, normal, alert, warning, danger, band, age in rows:
        assert band == expected_band(level, normal, alert, warning, danger), key
        assert level is None or age >= 0


@live
def test_forecast_has_rantau_panjang_town(live_run):
    rows = zetaris.run_sql("SELECT DISTINCT level FROM veda.forecast_kelantan WHERE place = 'Rantau Panjang'",
                           agent="Test").rows
    assert ["town"] in rows
