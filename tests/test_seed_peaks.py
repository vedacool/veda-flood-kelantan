"""Tests for B-55: scripts/seed_peaks.py validate_peaks() and the committed data/historic_peaks.csv (offline)."""
import importlib.util

import pytest

from app import trace
from app.adapters import zetaris

ROOT = trace.ROOT
spec = importlib.util.spec_from_file_location("seed_peaks", ROOT / "scripts" / "seed_peaks.py")
seed_peaks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_peaks)

CORE = {"5320038_DKKI0003", "5521044_DKKI0014", "_DMCG0215", "_DKBR0007", "_DPMS0003"}


def make_peak(**overrides):
    row = {"station_key": "_DPMS0003", "event": "Dec 2014", "peak_m": "10.84", "observed_when": "18 Dec 2014 11:00",
           "source_type": "official", "source_name": "JPS", "source_url": "https://example.org/report.pdf",
           "normal_m": "5", "alert_m": "7", "warning_m": "8", "danger_m": "9", "notes": ""}
    row.update(overrides)
    return row


def test_committed_peaks_file_is_valid_and_covers_core_stations():
    rows = seed_peaks.load_rows()
    assert seed_peaks.validate_peaks(rows, {r["station_key"] for r in rows}) == []
    official_2014 = {r["station_key"] for r in rows if r["event"] == "Dec 2014" and r["source_type"] == "official"}
    assert CORE <= official_2014          # 'bigger than 2014?' needs all 5 core stations
    assert all(r["source_url"].startswith("https://") for r in rows)


def test_valid_row_passes():
    assert seed_peaks.validate_peaks([make_peak()], {"_DPMS0003"}) == []


@pytest.mark.parametrize("overrides, needle", [
    ({"station_key": "_NOPE"}, "not in the stations table"),
    ({"event": ""}, "event is empty"),
    ({"source_type": "blog"}, "official or news"),
    ({"source_url": "http://example.org/x"}, "https URL"),
    ({"source_url": "not a url"}, "https URL"),
    ({"source_name": ""}, "source_name is empty"),
    ({"peak_m": ""}, "peak_m is required"),
    ({"peak_m": "abc"}, "peak_m is not a number"),
    ({"peak_m": "5000"}, "outside -50..1000"),
    ({"danger_m": "x"}, "danger_m is not a number"),
])
def test_bad_rows_are_reported(overrides, needle):
    problems = seed_peaks.validate_peaks([make_peak(**overrides)], {"_DPMS0003"})
    assert any(needle in p for p in problems), problems


def test_duplicate_station_event_is_reported():
    problems = seed_peaks.validate_peaks([make_peak(), make_peak()], {"_DPMS0003"})
    assert any("duplicate" in p for p in problems)


def test_compare_query_is_read_only():
    assert zetaris.read_only_problem(seed_peaks.COMPARE_SQL) is None


def test_myt_formatting():
    assert seed_peaks._myt("2026-10-22 08:45:00.0") == "22 Oct 16:45 MYT"


@pytest.mark.skipif(__import__("os").getenv("VEDA_LIVE") != "1", reason="live Zetaris test: set VEDA_LIVE=1")
def test_live_bigger_than_2014_for_core_stations(tmp_path):
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    trace.start_run("live B-55 test", log_dir=tmp_path, quiet=True)
    try:
        lines = seed_peaks.compare_lines()
    finally:
        trace.end_run()
    assert len(lines) == 5
    assert all("Dec 2014 peak" in line and "MYT" in line for line in lines)
