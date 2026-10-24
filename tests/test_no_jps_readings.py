"""B-75 guard (organiser ruling 23 Oct 2026): no JPS readings are redistributed in this repo. JPS levels are fetched
live at runtime on the user's machine only; offline data is the Nov 2024 replay (news-reported, cited), SYNTHETIC
scenes, data.gov.my open data and Open-Meteo (CC BY 4.0)."""
import json
import subprocess

from app import trace

ROOT = trace.ROOT
JPS_TABLES = ("veda_pg.river_levels", "veda.place_gauge_status", "veda.river_status_latest",
              "veda_wx.mygov_warning", "veda.place_risk_inputs", "water_level_current")   # + MetMalaysia, flood feed


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
        head = json.loads(text.splitlines()[0])          # first line says what was redacted and why
        assert "per organiser ruling 23 Oct" in head["redaction"] and head["run_id"] in path.name, path.name
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


def test_publish_trace_redacts_readings_in_prompts_and_keeps_cited_values(tmp_path):
    """scripts/publish_trace.py (24 Oct): a live trace now carries the exact prompt sent to the AI - the river level
    in it is redacted on publishing; a cited threshold stays; ids, times and durations stay."""
    import re
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import publish_trace
    rid = "20261025-101500-abcd"
    rec = {"timestamp": "2026-10-25T02:15:00Z", "run_id": rid, "step": 9, "action": "nightshift.chat",
           "duration_ms": 12000, "agent_name": "Coordinator",
           "details": {"prompt": [{"role": "user", "content": '{"FACTS": {"river": "10.94 m at 19:30", '
                                                              '"vs_danger": "1.94 m above the Danger level (9 m)"}}'}],
                       "level_m": 10.94}}
    src = tmp_path / f"trace-{rid}.jsonl"
    src.write_text(json.dumps({"action": "run_start", "run_id": rid, "timestamp": rec["timestamp"]}) + "\n"
                   + json.dumps(rec) + "\n", encoding="utf-8")
    out = publish_trace.publish(src, "test", out_dir=tmp_path)
    text = out.read_text(encoding="utf-8")
    assert out.name == f"2026-10-25_1015MYT_test_{rid}.trace.jsonl"
    assert "10.94" not in text and "1.94 m" not in text and "(9 m)" in text            # 9 m = the cited Danger level
    assert '"duration_ms": 12000' in text and "per organiser ruling 23 Oct" in text.splitlines()[0]


def test_clock_fixture_is_the_exact_clock_query_whatever_the_file_order(tmp_path):
    """Audit 24 Oct P1-4: other fixtures contain current_timestamp() too; on Linux the wrong one came first."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("mss", ROOT / "scripts" / "make_synthetic_scenes.py")
    mss = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mss)
    (tmp_path / "0.json").write_text(json.dumps({"sql": "WITH clock AS (SELECT current_timestamp()) SELECT 1",
                                                 "rows": [["0"]]}), encoding="utf-8")
    (tmp_path / "1.json").write_text(json.dumps({"sql": "SELECT current_timestamp() AS now_utc",
                                                 "rows": [["2026-10-22 13:33:08"]]}), encoding="utf-8")
    assert mss.clock_fixture(tmp_path)["rows"][0][0] == "2026-10-22 13:33:08"
