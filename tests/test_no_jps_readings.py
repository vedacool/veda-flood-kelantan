"""B-75 guard (organiser ruling 23 Oct 2026): no JPS readings are redistributed in this repo. JPS levels are fetched
live at runtime on the user's machine only; offline data is the Nov 2024 replay (news-reported, cited), SYNTHETIC
scenes, data.gov.my open data and Open-Meteo (CC BY 4.0)."""
import json
import re
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


# --- audit 27 Oct A-P1-18: docs/ and scripts/ too -------------------------------------------------------------------
# A metre value in a tracked doc or script must be a cited threshold, a historic peak or a replay anchor (read from the
# data files), or one reviewed on 27 Oct and listed here as SHA-256("file:value") - rule constants, SYNTHETIC
# generator settings, news-reported figures and projections worked out from the cited replay. No value is written
# here. A new value fails until it is checked: a live JPS reading or a rise / range worked out from one is replaced
# by "[JPS reading]" / "[rise]" (B-75), never added here.
REVIEWED_METRES = frozenset({
    "1753fd12368effa26a1d1e1a53873eee919d60481d7e7f4fd5a0adb683da0076",
    "2088e5fbdc1c2771696dc3d56d1a2bd0e0d8f34f0c8a7db6d8e4ee9e2ff98f4c",
    "2ce7f8eb34c647e3cf067442bc85a5db283915f73dbc49d80f5b28093549c46e",
    "2d94c6872fa1fb03b52484d1812ffd7401906ed3a9c5dceb4d2dd7aea58f6193",
    "2edb0ab730577b01ed439b113f6e0673f87f05968632818391fdc31d29bcf57c",
    "36fcc856b8edf557df982f19099cb85d1c07bb0d181e3876e7bbeb2c20f7f1ae",
    "39041cb911816933179f9ac5f9abb339a08e37dfbc6849c722dbad1250fd1caf",
    "3b9996d9e4a6cd5e16cfb4c3380d258647f77913a063b57d915351440aeecb9b",
    "45f26ce92fad7af8dad050d9f2019ee3a427e7e846d012694893ff06ba55f34e",
    "46344ff809be374b05f50cd77e1bc12fdd7067750144176f2362e41e05b8adeb",
    "4b884c546e6df8d5e0ed882baac9166534c59b0d674327832f7d7d840e4ea7c4",
    "4bf2fa80048ef575e097d5892bd6234d8ce68dd0db5f6a180b12c272503af9eb",
    "5f8f6fe2a28b2eba57037553ceada5a7b939dba04210a7e26aa45a8c0f72c499",
    "618ee27890f3bf279216b66a8efc712957a057439b2f9b48d235ccb4f0493549",
    "74e4f3c3b5e180b17e49d8e7ab2020fd6d85c4b07b3617479730a16d195b1bb8",
    "8446411625994d975086cdfb137cb4e88bb2beddd44f347316ae5634d1415e39",
    "9d4536079cf10869194cfd3d89040bc867bf6d33af94b38f4e57bc30691455fd",
    "a765127363c89ab770f3ce311e8a9ef2cfeb025055a9adea6ef970dad7326cbd",
    "af01fc57ad349d0496af2e79c3a53f6d13441364e30ea6cd1bcb4397bc59faa7",
    "c176b455711f01abcbacbd14812e8720840013a7d12a62459172eaacb8edc186",
    "ca173e5544d7e93fdcb50d8d1725256c5b1227cf28217482aafee8364b78ea0d",
    "d9b936ac1b4bf174d7bd096be090de78e16984172a71f1056ecb7393f3a2a4c7",
    "de3690982b6bc77bb52c045656060d5692066b2b62b0611701a98f1dac34133d",
    "dfad4f1cbcbb00571d35648a9068cadabd87675f1790e57f94bf38c6e2a81c3c",
    "e426b31c71c03bc0372d2e778a8368dfc1b3bdf03a3d69b7c3f601ee296b0e28",
    "e52ad546892b443798890a5689b3a438b8b9a8eaeac89e6305a92ef3b3a91144",
    "e59f41b29004d9bf5b16baeaa7aa12698a14c77f9268ad2d3022b227680bb8de",
    "ea2eb22f8a14fd3d46e87eef55705ba30440d5323cfd2398a1033f5b52318c3b",
    "effedf8b910c0482cb81b27b21808a6584dac9daba014c20fd210562bf75a1d5",
    "f86bc3be2d0995601a209a935cda33fe29973a693bcb2323e4e2315ca8d69d41",
    "fb7cae8626070703fdd0c844a660865c51af1825f285d5492a47944dbf2af27f",
    "fc6581db8bbec45baa7886fe06b9dd959facee5a4951ecfc5a520e1903d677bb",
    "fddff75790ad362da638797b21d848e3bfceb8b076f9c835749ae7700c8ecb46",
})
METRES = re.compile(r"(?<![\w.])(-?\d+\.\d+)\s?m(?![m\w²])")


def _cited_metres():
    import csv
    keep = set()
    for r in csv.DictReader((ROOT / "data" / "stations_mapping.csv").open(encoding="utf-8")):
        keep |= {round(float(v), 2) for k, v in r.items() if k.startswith("jps") and k.endswith("_m") and v}
    for r in csv.DictReader((ROOT / "data" / "historic_peaks.csv").open(encoding="utf-8")):
        keep |= {round(float(r[k]), 2) for k in ("peak_m", "normal_m", "alert_m", "warning_m", "danger_m") if r.get(k)}
    for name in ("nov2024_anchors.csv", "synthetic_anchors.csv"):
        for r in csv.DictReader((ROOT / "data" / "replay" / name).open(encoding="utf-8")):
            if r.get("level_m"):
                keep.add(round(float(r["level_m"]), 2))
    return keep


def test_docs_and_scripts_carry_no_jps_readings():
    """Audit 27 Oct (A-P1-18): the B-75 guard covers tracked docs/ and scripts/ - reports file:line only, never a value."""
    import hashlib
    keep, bad = _cited_metres(), []
    for f in tracked("docs", "scripts"):
        if not f.endswith((".md", ".py", ".txt", ".csv", ".json", ".html")) or f.startswith("docs/media"):
            continue
        text = (ROOT / f).read_text(encoding="utf-8", errors="replace")
        for m in METRES.finditer(text):
            v = round(float(m.group(1)), 2)
            if v not in keep and hashlib.sha256(f"{f}:{v:.2f}".encode()).hexdigest() not in REVIEWED_METRES:
                bad.append(f"{f}:{text.count(chr(10), 0, m.start()) + 1}")
    assert bad == [], f"metre values to check (B-75): {bad[:10]}"


def test_the_guard_catches_a_reading_in_a_doc(tmp_path, monkeypatch):
    """The scan itself works: a made-up level in a new doc is reported by file:line (never by value)."""
    import hashlib
    keep = _cited_metres()
    v = 1.23
    while round(v, 2) in keep:
        v += 0.01
    assert hashlib.sha256(f"docs/new.md:{v:.2f}".encode()).hexdigest() not in REVIEWED_METRES
    assert METRES.search(f"Rantau Panjang was {v:.2f} m at 16:45.")
