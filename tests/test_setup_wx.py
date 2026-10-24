"""Tests for B-07: scripts/setup_wx.py rain points, Open-Meteo URL and REST DDL guards."""
import importlib.util

import pytest

from app import trace
from app.adapters import zetaris

ROOT = trace.ROOT
spec = importlib.util.spec_from_file_location("setup_wx", ROOT / "scripts" / "setup_wx.py")
setup_wx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup_wx)


def make_point(i, **overrides):
    row = {
        "location_id": str(i),
        "point_key": f"p{i}",
        "lat": "5.5",
        "lon": "102.0",
        "coords_source": "test",
        "status": "ok",
    }
    row.update(overrides)
    return {k: "" if v is None else str(v) for k, v in row.items()}


def test_committed_rain_points_load_and_validate():
    points = setup_wx.load_points(ROOT / "data" / "rain_points.csv")
    assert setup_wx.validate_points(points) == []
    assert len(points) == 9                                  # + 2 Thai-side Golok points (B-88, 24 Oct)
    assert [p["location_id"] for p in points] == [str(i) for i in range(9)]
    thai = [p for p in points if "Thailand" in p["name"]]
    assert [p["point_key"] for p in thai] == ["golok_buketa", "sukhirin"]
    assert all(p["status"].startswith("tentative") and "OpenStreetMap" in p["coords_source"] for p in thai)
    assert all(p["coords_source"] and p["status"] for p in points)
    keys = [p["point_key"] for p in points]
    assert len(keys) == len(set(keys))


def test_open_meteo_url_for_committed_points():
    points = setup_wx.load_points(ROOT / "data" / "rain_points.csv")
    url = setup_wx.open_meteo_url(points)
    assert url.startswith("https://api.open-meteo.com/v1/forecast?")
    lats = ",".join(p["lat"] for p in points)
    lons = ",".join(p["lon"] for p in points)
    assert f"latitude={lats}" in url
    assert f"longitude={lons}" in url
    assert "%2C" not in url.split("latitude=")[1].split("&")[0]
    assert "%2C" not in url.split("longitude=")[1].split("&")[0]
    assert "hourly=precipitation,precipitation_probability" in url
    assert "daily=precipitation_sum" in url
    assert "past_days=7" in url
    assert "forecast_days=7" in url
    assert "timezone=Asia%2FKuala_Lumpur" in url


def test_create_sql_endpoints_pass_ddl_problem():
    points = setup_wx.load_points(ROOT / "data" / "rain_points.csv")
    for name, url in setup_wx.all_tables(points).items():
        assert zetaris.ddl_problem(setup_wx.create_sql(name, url)) is None
    bad = setup_wx.create_sql("evil", "http://169.254.169.254/")
    assert zetaris.ddl_problem(bad) is not None


def test_smoke_queries_are_read_only():
    for sql in setup_wx.SMOKE.values():
        assert zetaris.read_only_problem(sql) is None


@pytest.mark.parametrize("points,needle", [
    ([make_point(1)], "location_id"),
    ([make_point(0, point_key="a"), make_point(1, point_key="a")], "point_key"),
    ([make_point(0, point_key="")], "point_key"),
    ([make_point(0, lat="3.14", lon="101.69")], "not in or next to Kelantan"),
    ([make_point(0, lat="x")], "lat/lon"),
    ([make_point(0, coords_source="")], "coords_source"),
    ([make_point(0, status="")], "status"),
    ([], "no rain points"),
])
def test_validate_points_reports_problem(points, needle):
    problems = setup_wx.validate_points(points)
    assert problems
    assert any(needle in p for p in problems)


def test_load_points_sorts_by_location_id(tmp_path):
    csv = tmp_path / "points.csv"
    csv.write_text(
        "location_id,point_key,lat,lon,coords_source,status\n"
        "2,c,5.5,102.0,src,ok\n"
        "0,a,5.5,102.0,src,ok\n"
        "1,b,5.5,102.0,src,ok\n",
        encoding="utf-8",
    )
    points = setup_wx.load_points(csv)
    assert [p["location_id"] for p in points] == ["0", "1", "2"]
    assert [p["point_key"] for p in points] == ["a", "b", "c"]
