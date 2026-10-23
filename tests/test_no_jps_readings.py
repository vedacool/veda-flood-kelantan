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
