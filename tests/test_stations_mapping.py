"""Tests for B-67: scripts/seed_stations.py load_rows() and validate_mapping()."""
import importlib.util

import pytest

from app import trace

ROOT = trace.ROOT
spec = importlib.util.spec_from_file_location("seed_stations", ROOT / "scripts" / "seed_stations.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def make_gauge(key, **overrides):
    row = {
        "record_type": "gauge", "station_key": key, "brief_name": "", "is_core": "no",
        "chain_order": "1", "lat": "5.5", "lon": "102.0", "backup_of": "", "status": "ok",
        "needs_review_by": "Dr Ariff",
    }
    row.update(overrides)
    return {k: "" if v is None else str(v) for k, v in row.items()}


def make_link(a, b, kind, **overrides):
    row = {
        "record_type": "link", "from_key": a, "to_key": b, "link_type": kind,
        "lag_min_h": "", "lag_max_h": "", "lag_source": "", "status": "ok",
        "needs_review_by": "Dr Ariff",
    }
    row.update(overrides)
    return {k: "" if v is None else str(v) for k, v in row.items()}


def test_committed_mapping_is_valid():
    rows = seed.load_rows(ROOT / "data" / "stations_mapping.csv")
    gauges = [r for r in rows if r["record_type"] == "gauge"]
    links = [r for r in rows if r["record_type"] == "link"]
    known = {g["station_key"] for g in gauges}
    assert seed.validate_mapping(rows, known) == []
    core = [g for g in gauges if g["is_core"] == "yes"]
    assert len(core) == 5
    assert all(g["brief_name"] for g in core)
    assert all(r["needs_review_by"] for r in rows)
    for link in links:
        if link["lag_min_h"] or link["lag_max_h"]:
            assert link["lag_source"]


def test_small_valid_example():
    rows = [
        make_gauge("A"), make_gauge("B"),
        make_link("A", "B", "upstream_of", lag_min_h="1", lag_max_h="2"),
    ]
    assert seed.validate_mapping(rows, {"A", "B"}) == []


@pytest.mark.parametrize("rows,known,needle", [
    ([make_gauge("A")], set(), "not in the stations table"),
    ([make_gauge("A"), make_gauge("A")], {"A"}, "duplicate gauge station_key"),
    ([make_gauge("A", is_core="maybe")], {"A"}, "is_core must be yes or no"),
    ([make_gauge("A", chain_order="1.5")], {"A"}, "chain_order must be a whole number"),
    ([make_gauge("A", lat="5.5", lon="")], {"A"}, "lat and lon must both be set"),
    ([make_gauge("A", lat="3.14", lon="101.69")], {"A"}, "outside Kelantan"),
    ([make_gauge("A", backup_of="MISSING")], {"A"}, "is not a gauge"),
    ([make_gauge("A"), make_gauge("B"), make_link("A", "C", "upstream_of")], {"A", "B"},
     "both ends must be gauges"),
    ([make_gauge("A"), make_link("A", "A", "upstream_of")], {"A"}, "cannot link to itself"),
    ([make_gauge("A"), make_gauge("B"), make_link("A", "B", "sibling")], {"A", "B"},
     "link_type must be one of"),
    ([make_gauge("A"), make_gauge("B"),
      make_link("A", "B", "upstream_of"), make_link("A", "B", "upstream_of")], {"A", "B"},
     "duplicate link"),
    ([make_gauge("A"), make_gauge("B"),
      make_link("A", "B", "upstream_of", lag_min_h="5", lag_max_h="2")], {"A", "B"},
     "lag_min_h > lag_max_h"),
    ([make_gauge("A"), make_gauge("B"),
      make_link("A", "B", "upstream_of", lag_min_h="-1", lag_max_h="2")], {"A", "B"},
     "lags cannot be negative"),
    ([make_gauge("A"), make_gauge("B"),
      make_link("A", "B", "upstream_of", lag_min_h="x", lag_max_h="2")], {"A", "B"},
     "lags are not numbers"),
    ([make_gauge("A"), make_gauge("B"),
      make_link("A", "B", "upstream_of"), make_link("B", "A", "upstream_of")], {"A", "B"},
     "upstream_of links form a loop"),
    ([{"record_type": "station", "station_key": "A", "status": "ok", "is_core": "no",
       "chain_order": "", "lat": "", "lon": "", "backup_of": ""}], {"A"},
     "record_type must be gauge or link"),
])
def test_validate_reports_problem(rows, known, needle):
    problems = seed.validate_mapping(rows, known)
    assert problems
    assert any(needle in p for p in problems)
