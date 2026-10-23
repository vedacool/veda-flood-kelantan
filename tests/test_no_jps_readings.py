"""B-75 guard (organiser ruling 23 Oct 2026): no JPS readings are redistributed in this repo. JPS levels are fetched
live at runtime on the user's machine only; offline data is the Nov 2024 replay (news-reported, cited), SYNTHETIC
scenes, data.gov.my open data and Open-Meteo (CC BY 4.0)."""
import json
import subprocess

from app import trace

ROOT = trace.ROOT
JPS_TABLES = ("veda_pg.river_levels", "veda.place_gauge_status", "veda.river_status_latest")


def tracked(*paths):
    out = subprocess.run(["git", "ls-files", *paths], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def test_every_fixture_from_a_jps_table_is_synthetic():
    for path in sorted((ROOT / "data" / "fixtures" / "zetaris").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        sql = " ".join(doc.get("sql", "").split())
        if any(t in sql for t in JPS_TABLES):
            assert doc.get("synthetic") is True and "SYNTHETIC" in doc.get("note", ""), path.name


def test_no_jps_page_is_committed():
    assert tracked("data/snapshots/jps") == []
    page = (ROOT / "tests" / "fixtures" / "jps_synthetic_page.html").read_text(encoding="utf-8")
    assert page.startswith("<!-- SYNTHETIC test page")


def test_scene_rows_are_cited_or_synthetic():
    import csv
    for name in ("nov2024_anchors.csv", "synthetic_anchors.csv"):
        for row in csv.DictReader((ROOT / "data" / "replay" / name).open(encoding="utf-8")):
            if row["scenario"].startswith("synthetic_"):
                assert row["source_name"] == "SYNTHETIC"
            else:
                assert row["source_url"].startswith("https://") and row["quote"]


def test_recorded_live_traces_carry_no_jps_readings():
    """Only cited thresholds / peaks may appear as metre values; readings read '[JPS reading — not redistributed]'."""
    import csv
    import re
    keep = set()
    for r in csv.DictReader((ROOT / "data" / "stations_mapping.csv").open(encoding="utf-8")):
        keep |= {round(float(v), 2) for k, v in r.items() if k.startswith("jps") and k.endswith("_m") and v}
    for r in csv.DictReader((ROOT / "data" / "historic_peaks.csv").open(encoding="utf-8")):
        keep.add(round(float(r["peak_m"]), 2))
    metres = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?m(?![m\w])")
    for path in sorted((ROOT / "data" / "sample" / "live_traces").glob("*.trace.jsonl")):
        text = path.read_text(encoding="utf-8")
        assert "[JPS reading — not redistributed]" in text, path.name
        assert not re.search(r'"value": -?\d', text), path.name
        left = [m.group(0) for m in metres.finditer(text) if round(float(m.group(1)), 2) not in keep]
        assert left == [], (path.name, left[:5])


def test_synthetic_values_are_exactly_what_the_seeded_method_makes():
    """Every SYNTHETIC output comes from scripts/make_synthetic_scenes.py (cited thresholds, 2014 peaks, travel
    times, fixed seed) - a hand edit, or a value adapted from a real reading, fails here."""
    import sys
    out = subprocess.run([sys.executable, "scripts/make_synthetic_scenes.py", "--check"], cwd=ROOT, capture_output=True,
                         text=True)
    assert out.returncode == 0, out.stdout + out.stderr
