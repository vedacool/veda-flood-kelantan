"""Tests for app/ingest/jps.py (B-06). Offline tests parse the committed 10:40 snapshot.

Live tests (VEDA_LIVE=1) write to veda-pg and read back through Zetaris.
"""
import json
import os
import time
from datetime import datetime, timezone

import pytest

from app import trace
from app.ingest import jps

SNAPSHOT = trace.ROOT / "data" / "snapshots" / "jps" / "kel-20261022-1040.html"


@pytest.fixture(scope="module")
def readings():
    return jps.parse(SNAPSHOT.read_text(encoding="utf-8"))


def test_all_36_stations_with_unique_graph_ids(readings):
    assert len(readings) == 36
    assert len({r.station_key for r in readings}) == 36
    assert all(r.station_key for r in readings)
    assert sum(r.jps_id is None for r in readings) == 8  # blank visible ids still get a key


def test_dabong_row(readings):
    d = next(r for r in readings if r.station_key == "5320038_DKKI0003")
    assert d.name == "Sg. Galas di Dabong (F1)" and d.name_norm == "sg galas di dabong"
    assert d.jps_id is None and d.district == "Kuala Krai" and d.river == "Sg. Galas"
    assert d.level_m == 29.57 and d.danger_m == 38.0
    assert None not in (d.normal_m, d.alert_m, d.warning_m)
    assert d.observed_at == datetime(2026, 10, 22, 1, 15, tzinfo=timezone.utc)  # 09:15 MYT


def test_core_station_keys_present(readings):
    keys = {r.station_key for r in readings}
    assert {"_DPMS0003", "_DKBR0007", "5521044_DKKI0014", "5320038_DKKI0003"} <= keys


@pytest.mark.parametrize("raw, expected", [("7.47", 7.47), ("-", None), ("", None), ("N/A", None),
                                           ("-9999", None), ("-0.5", -0.5), ("1,234.5", 1234.5)])
def test_to_number(raw, expected):
    assert jps.to_number(raw) == expected


def test_to_utc():
    assert jps.to_utc("22/10/2026 10:30") == datetime(2026, 10, 22, 2, 30, tzinfo=timezone.utc)
    assert jps.to_utc("-") is None


def test_missing_column_raises():
    html = SNAPSHOT.read_text(encoding="utf-8").replace("data-th='Danger'", "data-th='Bahaya'")
    with pytest.raises(jps.JpsParseError, match="Danger"):
        jps.parse(html)


def test_empty_page_raises():
    with pytest.raises(jps.JpsParseError):
        jps.parse("<html><body>Maintenance</body></html>")


def test_recent_snapshot_is_reused_without_http(tmp_path, monkeypatch):
    monkeypatch.setattr(jps, "CACHE_DIR", tmp_path)
    snap = tmp_path / "kel-20261022-114500.html"
    snap.write_text("<html>cached</html>", encoding="utf-8")
    monkeypatch.setattr(jps, "_now", lambda: snap.stat().st_mtime + 5 * 60)

    def no_http(*a, **k):
        raise AssertionError("JPS must not be called within 15 minutes")

    monkeypatch.setattr(jps.requests, "get", no_http)
    trace.start_run("t", log_dir=tmp_path, quiet=True)
    try:
        html, source, path = jps.fetch()
    finally:
        trace.end_run()
    assert html == "<html>cached</html>" and source == "jps-cache" and path == snap


def test_old_snapshot_triggers_one_live_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr(jps, "CACHE_DIR", tmp_path)
    old = tmp_path / "kel-20261022-100000.html"
    old.write_text("old", encoding="utf-8")
    monkeypatch.setattr(jps, "_now", lambda: time.time() + 16 * 60)
    calls = []

    class Resp:
        status_code, text, content = 200, "<html>new</html>", b"<html>new</html>"

        def raise_for_status(self):
            pass

    def fake_get(url, headers=None, timeout=None):
        calls.append(headers)
        return Resp()

    monkeypatch.setattr(jps.requests, "get", fake_get)
    trace.start_run("t", log_dir=tmp_path / "logs", quiet=True)
    try:
        html, source, path = jps.fetch()
    finally:
        trace.end_run()
    assert source == "jps-live" and html == "<html>new</html>" and path.exists()
    assert "contact" in calls[0]["User-Agent"] and len(calls) == 1


live = pytest.mark.skipif(os.getenv("VEDA_LIVE") != "1", reason="live veda-pg/Zetaris test: set VEDA_LIVE=1")


@live
def test_ingest_snapshot_idempotent_and_readable_via_zetaris(tmp_path):
    from dotenv import load_dotenv

    from app.adapters import zetaris
    load_dotenv(trace.ROOT / ".env")
    trace.start_run("live B-06 test", log_dir=tmp_path, quiet=True)
    try:
        jps.ingest(from_file=SNAPSHOT)
        again = jps.ingest(from_file=SNAPSHOT)
        r = zetaris.run_sql("SELECT s.station_key, s.name, l.level_m, s.danger_m FROM veda_pg.river_levels l "
                            "JOIN veda_pg.stations s ON s.station_key = l.station_key "
                            "WHERE s.station_key = '5320038_DKKI0003' AND l.source = 'jps-snapshot'", agent="Test")
    finally:
        trace.end_run()
    assert again["new_levels"] == 0 and again["stations"] == 36
    assert ["5320038_DKKI0003", "Sg. Galas di Dabong (F1)", 29.57, 38.0] in r.rows
