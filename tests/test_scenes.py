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

from app import config, gazetteer, main, scenes, trace

FIXTURES = trace.ROOT / "data" / "fixtures" / "zetaris"
PAGE = (trace.ROOT / "app" / "web" / "scenes.html").read_text(encoding="utf-8")
METRES = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?m(?![m\w])")
CHECKS = {"verdict_in", "verdict_not_in", "used", "left_out", "step_present", "safety_passed"}


@pytest.fixture(scope="module", autouse=True)
def offline():
    """SAMPLE_MODE with no credentials, as in CI: the scenes run on the committed fixtures alone."""
    mp = pytest.MonkeyPatch()
    mp.setenv("SAMPLE_MODE", "true")
    gazetteer.clear_cache()
    yield
    mp.undo()
    gazetteer.clear_cache()


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
        assert res["matched"] == res["total"] == len(res["rows"])
        for lang in ("en", "ms"):
            assert [x["key"] for x in res["how"][lang]] == list(scenes.STEPS_SENT), (sid, lang)
        assert res["log"] and {t["key"] for t in res["log"]} <= set(scenes.STEPS_SENT)


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
    for path in ("/scenes", "/scenes/rp-peak"):                                    # B-96: the shared frame (a28a6ff)
        html = c.get(path).text
        assert html.count('class="vf-top"') == 1 and html.count('class="vf-foot"') == 1 and "<!--VEDA:" not in html
        assert re.search(r'href="/scenes"[^>]*aria-current="page"', html), path
    assert PAGE.index("window.vedaSetLang = setLang;") < PAGE.index("<!--VEDA:FOOT-->")   # before /frame.js loads
    d = c.get("/scenes/data.json").json()
    assert [s["id"] for s in d["scenes"]][0] == "rp-before" and all(s["data"] for s in d["scenes"])
    assert c.post("/scenes/rp-peak/check", content=b"x" * (scenes.MAX_BODY + 1)).status_code == 413
    assert c.post("/scenes/rp-peak/check", content=b"not json").status_code == 400
    monkeypatch.setattr(config, "demo_mode", lambda: True)                         # the public demo
    assert c.get("/scenes/rp-peak").status_code == 200 and c.get("/scenes/data.json").status_code == 200


def test_page_words_and_links():
    """Cowork wireframes v3 (B-96): the list title and intro, three numbered steps, the result links and last line."""
    for text in ('list_title: "Test VEDA yourself"',
                 '"Each test shows the situation and the data, tells you what VEDA should say, then you run it and compare."',
                 'group_real: "Real flood · November 2024"', 'group_made: "Made-up tests"',
                 'step1: "The situation"', 'step2: "The data at that moment"', 'step3: "What VEDA should do → what it did"',
                 'match: "✓ match"', 'different: "✗ different"', 'score: "{n} of {m} matched"',
                 'how_title: "How VEDA got there"', 'full_answer: "See the full answer VEDA gave ›"',
                 'live_link: "See a real live run with Nemotron ›"', 'show_log: "Show technical log"',
                 'feedback_q: "Did VEDA match what you expected?"', 'tell_us: "Tell us"', 'next: "Next test ›"',
                 '"A river level post (gauge) measures how high the river is.', 'href="/how-it-works#live"', "/feedback?lang="):
        assert text in PAGE, text
    ui = PAGE.split("const UI = {", 1)[1].split("\n};", 1)[0]
    en, ms = ui.split("\n  ms: {", 1)
    keys = lambda block: set(re.findall(r"(?:^|[{,]|\n)\s*([a-z_0-9]+): (?=[\"{])", block))   # noqa: E731
    assert keys(en) - {"en"} == keys(ms) and len(keys(ms)) > 40


def test_every_data_row_has_a_source_tag():
    """Cowork B-91b, B-96: each row of step 2 says where its values come from, as plain grey text (not a tag)."""
    body = PAGE.split("function dataRows(d) {", 1)[1].split("\n}\n", 1)[0]
    pushes = body.split("rows.push(")[1:]
    assert len(pushes) == 5 and all("origin" in p or "${om}" in p for p in pushes)
    assert "function origin(g)" in PAGE and 'class="origin"' in PAGE
    for key, en, ms in (("o_news", "news report: {s}", "laporan berita: {s}"), ("o_demo", "demo data", "data demo"),
                        ("o_jps", "JPS station list", "senarai stesen JPS"), ("o_om", "Open-Meteo archive", "arkib Open-Meteo")):
        assert f'{key}: "{en}"' in PAGE and f'{key}: "{ms}"' in PAGE


def test_the_v3_ui_rules():
    """Cowork B-96: one filled button (Start test); no guess buttons, no 'Show what to expect', no chips or pills;
    the expectations show at once with '–' before the run; nothing collapses but the log and per-value details."""
    assert PAGE.count('class="primary"') == 1 and 'id="start"' in PAGE.split('class="primary"', 1)[1][:30]
    for gone in ("show-expect", "guess", "chip", "tag-src", "Open ›", "<details id=\"brief\"", "briefing"):
        assert gone not in PAGE, gone
    assert PAGE.count("<details") == 2 and PAGE.count("details class=\"more\"") == 2   # the log + per-value details
    assert 'pending: "–"' in PAGE and "function renderExpect()" in PAGE


def test_every_scene_has_a_hook_and_the_list_has_two_groups():
    exp = scenes.expected()["scenes"]
    data = {d["id"]: d for d in scenes.scene_data()["scenes"]}
    for s in exp:
        assert s["hook"]["en"].strip() and s["hook"]["ms"].strip() and len(s["hook"]["en"]) <= 70, s["id"]
    assert [s["id"] for s in exp if data[s["id"]]["kind"] == "replay"] == ["rp-before", "rp-morning", "rp-peak"]
    assert len([s for s in exp if data[s["id"]]["kind"] == "synthetic"]) == 4


def test_plain_words_on_screen(runs):
    """B-96: what the result shows outside the technical log - the ✗ text and "How VEDA got there" - never holds
    SAMPLE_MODE, not_run, BUILD_BRIEF, internal ids, rule names or confidence decimals."""
    banned = re.compile(r"SAMPLE_MODE|not_run|BUILD_BRIEF|\d{8}-\d{6}-[0-9a-f]{4}|\(F\d\)|confidence|(?<![\d.])0\.\d{2}|_[a-z]+_|"
                        r"[a-z]+\.[a-z]+\(|need:|section 7", re.I)
    for sid, out in runs.items():
        res = scenes.check(sid, out)
        for lang in ("en", "ms"):
            shown = [r["said"][lang] for r in res["rows"]] + [f'{x["who"]}: {x["text"]}' for x in res["how"][lang]]
            for text in shown:
                assert not banned.search(text), (sid, lang, text)
    peak = copy.deepcopy(runs["rp-peak"])                                      # a failing safety row is plain too
    for st in peak["steps"]:
        if st["key"] == "safety":
            st["lines"] = [{"action": "safety", "text": "1 fix: removed an unsafe sentence - BUILD_BRIEF section 7"}]
    row = next(r for r in scenes.check("rp-peak", peak)["rows"] if r["id"] == "safety")
    assert row["said"]["en"] == "The safety gate had to fix the answer."


def test_how_veda_got_there_reads_the_run(runs):
    """app/trail.py: the Critic line says what the Critic did in THIS run (asked for data, what was found, approved)."""
    from app import trail
    silent = {x["key"]: x["text"] for x in trail.how_lines(runs["pm-silent-upstream"], "en")}
    assert silent["critique"] == ("Asked the Data agent for a fresh upstream reading. It found Sg. Kelantan di Kusial "
                                  "Baru. The level was worked out again. Checked the facts again and approved the answer.")
    assert silent["safety"] == "All safety checks passed."
    assert silent["gather"].startswith("Used 6 of 11 sources. Left out: Sg. Kelantan di Air Mulih, reading too old")
    calm = {x["key"]: x["text"] for x in trail.how_lines(runs["tumpat-calm"], "ms")}
    assert calm["critique"] == "Menyemak semula fakta dan meluluskan jawapan."
    assert calm["forecast"].startswith("Normal buat masa ini. ")
    sent_back = copy.deepcopy(runs["tumpat-calm"])
    for st in sent_back["steps"]:
        if st["key"] == "critique":
            st["lines"] = [{"action": "critic.review", "text": "needs_revision: a number is not in the facts"}]
    assert trail.how_lines(sent_back, "en")[2]["text"] == "Sent the answer back to be fixed."


def test_news_report_tags_only_on_the_allow_listed_values():
    """A value is tagged 'News report' only if the scene's allow-list (with the article's URL) names it, and the
    shown value equals it; trends, ages and made-up scenes are never news."""
    c = TestClient(main.app)
    want = {"rp-before": {("_DPMS0003", "level"), ("_DPMS0003", "warning"), ("_DTMH0008", "level"), ("_DTMH0008", "danger")},
            "rp-morning": {("_DPMS0003", "level"), ("_DPMS0003", "warning"), ("_DTMH0008", "level"), ("_DTMH0008", "danger")},
            "rp-peak": {("_DPMS0003", "level"), ("_DPMS0003", "danger"), ("_DTMH0008", "level"), ("_DTMH0008", "danger")}}
    for s in c.get("/scenes/data.json").json()["scenes"]:
        allowed = {(v["station"], v["field"], v["value"], a["url"]) for a in s.get("news") or [] for v in a["values"]}
        assert all(a["url"].startswith("https://") for a in s.get("news") or [])
        tagged = set()
        for g in s["data"]["gauges"]:
            for n in g["news"]:
                assert (g["station"], n["field"], n["value"], n["url"]) in allowed, (s["id"], g["name"], n)
                assert n["field"] in ("level", "alert", "warning", "danger")
                tagged.add((g["station"], n["field"]))
        assert tagged == want.get(s["id"], set()), s["id"]
    peak = next(s for s in c.get("/scenes/data.json").json()["scenes"] if s["id"] == "rp-peak")
    rp = next(g for g in peak["data"]["gauges"] if g["station"] == "_DPMS0003")
    assert {n["url"] for n in rp["news"]} == {"https://www.kosmo.com.my/2024/11/27/paras-air-sungai-golok-lepasi-bacaan-bah-kuning-2014/"}


def test_review_texts_and_banned_malay_words():
    exp = scenes.EXPECTED.read_text(encoding="utf-8")
    for banned in ("tiang paras sungai", "Tiang paras sungai", "tolok", "tiang"):
        assert banned not in exp and banned not in PAGE.split("\n  ms: {", 1)[1], banned
    for text in ("Heavy rain has fallen over the past day, here and across the border in Thailand.",
                 "Hujan lebat turun sejak semalam, di sini dan di seberang sempadan di Thailand.",
                 "An ordinary Saturday morning in June", "Pagi Sabtu biasa pada bulan Jun",
                 "Tumpat is near the river mouth, so VEDA checks two river level stations, one of them affected by the tide.",
                 "Tumpat berhampiran muara sungai, jadi VEDA menyemak dua stesen paras air, salah satunya dipengaruhi air pasang.",
                 "Either is acceptable: the river here is low, but VEDA may stay cautious because it can't see upstream.",
                 "VEDA's own rain rule (there is no official JPS rule for rain alone)",
                 '"The river level is used."', '"Paras sungai digunakan."',
                 "Penyemak mendapati stesen hulu berhenti menghantar bacaan, lalu meminta Ejen Data mencari stesen lain.",
                 "Nearest rain point VEDA uses: Kota Bharu", "Titik hujan terdekat yang digunakan VEDA: Kota Bharu"):
        assert text in exp, text
    for text in ('real: "Real flood, Nov 2024"', 'made: "Made-up test"', 'people: "the people are imagined"',
                 'real: "Banjir sebenar, Nov 2024"', 'made: "Ujian rekaan"', 'people: "orang dalam cerita ini rekaan"'):
        assert text in PAGE, text
    judges = (trace.ROOT / "app" / "web" / "judges.html").read_text(encoding="utf-8")
    from app import trail                                                         # the same BM names as /judges
    for name in ("Penyemak", "Ejen Data", "Ejen Ramalan", "Semakan keselamatan"):
        assert f'"{name}"' in judges and name in {a["ms"] for a in trail.AGENTS.values()}


def test_each_value_is_tagged_with_its_real_origin():
    """Cowork B-91c: News report = the article states it; JPS station list = an official line from
    data/stations_mapping.csv that the article does not state; Demo data = generated (trends, made-up readings)."""
    official = scenes.station_lines()
    c = TestClient(main.app)
    for s in c.get("/scenes/data.json").json()["scenes"]:
        for g in s["data"]["gauges"]:
            news = {n["field"] for n in g["news"]}
            lines = {n["field"]: n["value"] for n in g["lines"]}
            for k in ("alert", "warning", "danger"):              # every shown line has exactly one origin
                if g["thresholds"][k] is not None:
                    assert (k in news) != (k in lines), (s["id"], g["name"], k)
            for k, v in lines.items():
                assert official[g["station"]][k] == v, (s["id"], g["name"], k)
            if s["data"]["kind"] == "replay":
                assert "level" in news, (s["id"], g["name"])       # every replay reading shown is a reported one
            else:
                assert not news and g["demo"], (s["id"], g["name"])  # made-up scenes: nothing is news
            trends = g["change_1h_m"] is not None or g["change_3h_m"] is not None
            assert g["demo"] == ("level" not in news or trends), (s["id"], g["name"])
    assert 'o_jps: "JPS station list"' in PAGE and 'o_jps: "senarai stesen JPS"' in PAGE


def test_the_kosmo_2014_sentence_is_tagged_and_1_94_is_never_shown():
    peak = next(s for s in scenes.expected()["scenes"] if s["id"] == "rp-peak")
    en = "Kosmo reported that the river had passed its level in the 2014 flood (10.52 m)."
    ms = "Kosmo melaporkan paras sungai telah melepasi paras banjir 2014 (10.52 m)."
    assert peak["story"]["en"].startswith("Wednesday 27 November 2024, 7:30 pm. " + en)
    assert peak["story"]["ms"].startswith("Rabu, 27 November 2024, 7:30 malam. " + ms)
    (n,) = peak["story_news"]
    assert n["text"] == {"en": en, "ms": ms} and "kosmo.com.my/2024/11/27/" in n["url"]
    assert n["url"] in {a["url"] for a in peak["news"]}                      # the same Kosmo article
    for text in (scenes.EXPECTED.read_text(encoding="utf-8"), scenes.DATA.read_text(encoding="utf-8"), PAGE):
        assert "1.94" not in text
