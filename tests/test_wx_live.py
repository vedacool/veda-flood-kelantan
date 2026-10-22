"""Live checks for B-07 REST tables (run with VEDA_LIVE=1; needs Zetaris and scripts/setup_wx.py run once)."""
import os

import pytest

from app import trace
from app.adapters import zetaris

pytestmark = pytest.mark.skipif(os.getenv("VEDA_LIVE") != "1", reason="live Zetaris test: set VEDA_LIVE=1")


@pytest.fixture(autouse=True)
def live_run(tmp_path):
    from dotenv import load_dotenv
    load_dotenv(trace.ROOT / ".env")
    trace.start_run("live B-07 test", log_dir=tmp_path, quiet=True)
    yield
    trace.end_run()


def test_rain_has_every_point_with_14_days():
    rows = zetaris.run_sql("SELECT COALESCE(location_id, 0) AS id, size(daily.time) AS days FROM veda_wx.om_rain "
                           "ORDER BY 1", agent="Test").rows
    assert [r[0] for r in rows] == list(range(7))
    assert all(r[1] == 14 for r in rows)


def test_kelantan_forecast_present():
    rows = zetaris.run_sql("SELECT DISTINCT f.location.location_name FROM veda_wx.mygov_forecast "
                           "LATERAL VIEW explode(data) AS f WHERE f.location.location_name IN ('Kota Bharu', 'Pasir Mas')",
                           agent="Test").rows
    assert {r[0] for r in rows} == {"Kota Bharu", "Pasir Mas"}


def test_flood_warning_source_is_still_frozen():
    # The Critic must catch this stale source; if data.gov.my ever revives it, this test tells us to update the story.
    newest = zetaris.run_sql("SELECT MAX(s.water_level_update_datetime) FROM veda_wx.mygov_flood "
                             "LATERAL VIEW explode(data) AS s", agent="Test").rows[0][0]
    assert str(newest).startswith("2024-02")
