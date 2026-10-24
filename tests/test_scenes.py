"""B-91 Scenes test page: labelled scenes, expectations with reasons and sources, the data table from the fixtures,
✓ / ✗ computed from the real run output (and flipping when the output changes), no live JPS values."""
import copy
import csv
import importlib.util
import io
import json
import re
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import config, main, scenes, trace

FIXTURES = trace.ROOT / "data" / "fixtures" / "zetaris"
PAGE = (trace.ROOT / "app" / "web" / "scenes.html").read_text(encoding="utf-8")
METRES = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?m(?![m\w])")
CHECKS = {"verdict_in", "verdict_not_in", "used", "left_out", "step_present", "safety_passed"}


@pytest.fixture(scope="module")
def runs():
    """Each scene run offline on the app's own path -> its compact result (what the page sends to the check)."""
    out = {}
    for s in scenes.expected()["scenes"]:
        q, rp, at = main.parse_input(scenes.QUESTION["en"].format(town=s["town"]), s["replay"], s["at"])
        with redirect_stdout(io.StringIO()):
            r = main._run(q, rp, at, None, "en")
        out[s["id"]] = scenes.compact(main.result_json(r))
    return out


def test_every_scene_has_a_source_label_and_a_story():
    data = {d["id"]: d for d in scenes.scene_data()["scenes"]}
    exp = scenes.expected()["scenes"]
    assert len(exp) == 7 and set(data) == {s["id"] for s in exp}
    for s in exp:
        d = data[s["id"]]
        assert s["replay"] in config.REPLAYS and s["at"] in config.REPLAYS[s["replay"]]["scenes"]   # existing scenes only
        assert s["story"]["en"] and s["story"]["ms"]
        label = d["source_label"]
        if config.synthetic(s["replay"]):
            assert label == {"en": "Made-up example", "ms": "Contoh rekaan"} and d["kind"] == "synthetic"
        else:
            assert label["en"].startswith("Based on ") and label["ms"].startswith("Berdasarkan ") and "JPS" in label["en"]


def test_every_expectation_has_a_reason_a_source_and_a_check():
    for s in scenes.expected()["scenes"]:
        assert 2 <= len(s["expect"]) <= 4, s["id"]
        for e in s["expect"]:
            for k in ("text", "reason", "source"):
                assert e[k]["en"].strip() and e[k]["ms"].strip(), (s["id"], e["id"], k)
            assert set(e["check"]) <= CHECKS and len(e["check"]) == 1, (s["id"], e["id"])


def test_the_data_table_is_what_the_fixtures_give():
    """scenes_data.json = a fresh build from the fixtures; every river value = its row in the fixture file it came
    from; every threshold = the cited JPS line in data/stations_mapping.csv."""
    assert scenes.build_all() == scenes.scene_data()
    lines = {r["station_key"]: r for r in csv.DictReader((trace.ROOT / "data" / "stations_mapping.csv")
                                                         .open(encoding="utf-8")) if r["record_type"] == "gauge"}
    for s in scenes.scene_data()["scenes"]:
        assert s["gauges"], s["id"]
        for g in s["gauges"]:
            doc = json.loads((FIXTURES / f"{g['query_hash']}.json").read_text(encoding="utf-8"))
            col = {c: i for i, c in enumerate(doc["columns"])}
            utc = (datetime.strptime(g["at"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone(timedelta(hours=8)))
                   .astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
            rows = [r for r in doc["rows"] if r[col["station_key"]] == g["station"] and r[col["observed_at"]].startswith(utc)]
            assert rows and float(rows[0][col["level_m"]]) == g["level_m"], (s["id"], g["name"])
            line = lines[g["station"]]
            for k in ("alert", "warning", "danger"):
                want = float(line[f"jps_{k}_m"]) if line[f"jps_{k}_m"] else None
                assert g["thresholds"][k] == want, (s["id"], g["name"], k)


def test_no_live_jps_value():
    """Only demo data: replay readings reported in the news (the replay anchors) or made-up scene values (B-75)."""
    spec = importlib.util.spec_from_file_location("build_replay", trace.ROOT / "scripts" / "build_replay.py")
    br = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(br)
    replay = {(r["station_key"], r["observed_at"].strftime("%Y-%m-%d %H:%M"), r["level_m"])
              for r in br.reconstruct(br.load_rows())}
    for s in scenes.scene_data()["scenes"]:
        for g in s["gauges"]:
            doc = json.loads((FIXTURES / f"{g['query_hash']}.json").read_text(encoding="utf-8"))
            assert "veda_pg.replay_levels" in doc["sql"] and f"scenario = '{s['replay']}'" in doc["sql"]
            if s["kind"] == "replay":
                assert (g["station"], g["at"], g["level_m"]) in replay, (s["id"], g["name"])
    assert METRES.findall(PAGE) == []                               # the page itself holds no reading


def test_every_expectation_passes_on_the_real_runs(runs):
    """Report, not a target: the expectations are written from the inputs; this records how VEDA did on 24 Oct."""
    for sid, out in runs.items():
        res = scenes.check(sid, out)
        assert [r["id"] for r in res["rows"] if not r["ok"]] == [], (sid, res["rows"])
        assert res["trail"] and {t["key"] for t in res["trail"]} <= set(scenes.STEPS_SENT)


def test_a_changed_output_flips_the_check_to_a_cross(runs):
    """✓ / ✗ comes from the run output only: change the output and the matching expectation fails, saying why."""
    peak = copy.deepcopy(runs["rp-peak"])
    peak["verdict"] = "WATCH"
    row = next(r for r in scenes.check("rp-peak", peak)["rows"] if r["id"] == "level")
    assert not row["ok"] and row["said"]["en"] == "VEDA said: Keep watching"
    used = copy.deepcopy(runs["rp-peak"])
    for s in used["sources"]:
        if "Kg. Jenob" in s["name"]:
            s["used"] = True
    row = next(r for r in scenes.check("rp-peak", used)["rows"] if r["id"] == "stale-upstream")
    assert not row["ok"] and "Kg. Jenob: used" in row["said"]["en"]
    silent = copy.deepcopy(runs["pm-silent-upstream"])
    for st in silent["steps"]:
        st["lines"] = [ln for ln in st["lines"] if ln["action"] != "critic.request"]
    row = next(r for r in scenes.check("pm-silent-upstream", silent)["rows"] if r["id"] == "critic-asks")
    assert not row["ok"] and row["said"]["en"] == "This step did not happen in the run."
    unsafe = copy.deepcopy(runs["rp-peak"])
    for st in unsafe["steps"]:
        if st["key"] == "safety":
            st["lines"] = [{"action": "safety", "text": "1 fix: removed an unsafe sentence"}]
    assert not next(r for r in scenes.check("rp-peak", unsafe)["rows"] if r["id"] == "safety")["ok"]
    assert all(not r["ok"] for r in scenes.check("rp-peak", {})["rows"])          # nothing in -> nothing passes


def test_the_page_sends_the_same_compact_shape_and_stays_small(runs):
    assert "function compact(r)" in PAGE and '["gather", "forecast", "critique", "safety"]' in PAGE
    assert ".slice(0, 12)" in PAGE and ".slice(0, 160)" in PAGE                   # = scenes.compact()
    assert max(len(json.dumps(out)) for out in runs.values()) < scenes.MAX_BODY


def test_routes(monkeypatch):
    c = TestClient(main.app)
    assert c.get("/scenes").status_code == 200 and 'id="scenes"' in c.get("/scenes").text
    assert c.get("/scenes/rp-peak").status_code == 200 and c.get("/scenes/nope").status_code == 404
    d = c.get("/scenes/data.json").json()
    assert [s["id"] for s in d["scenes"]][0] == "rp-before" and all(s["data"] for s in d["scenes"])
    assert c.post("/scenes/rp-peak/check", content=b"x" * (scenes.MAX_BODY + 1)).status_code == 413
    assert c.post("/scenes/rp-peak/check", content=b"not json").status_code == 400
    monkeypatch.setattr(config, "demo_mode", lambda: True)                         # the public demo
    assert c.get("/scenes/rp-peak").status_code == 200 and c.get("/scenes/data.json").status_code == 200


def test_page_words_and_links():
    for text in ('"Did VEDA match what you expected? Tell us"',
                 'nemotron: "Nemotron\'s own judgement: live mode only."',
                 'judges_link: "See the recorded live run on the For judges page ›"',
                 '"A river level post (gauge) measures how high the river is.', 'href="/judges"', "/feedback?lang="):
        assert text in PAGE, text
    ui = PAGE.split("const UI = {", 1)[1].split("\n};", 1)[0]
    en, ms = ui.split("\n  ms: {", 1)
    keys = lambda block: set(re.findall(r"(?:^|[{,]|\n)\s*([a-z_0-9]+): (?=[\"{])", block))   # noqa: E731
    assert keys(en) - {"en"} == keys(ms) and len(keys(ms)) > 40
