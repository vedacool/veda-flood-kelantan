"""The public answer screen's data (Cowork weekend plan B, 24 Oct): EN + BM equal, no jargon, the share text never
carries the question, every verdict rule has a plain Why sentence, and the page itself loads nothing from outside."""
import json
import re
from datetime import datetime

import pytest

from app import config, gazetteer, loop, view
from app.agents import forecast_agent

SCENES = [("nov2024", "2024-11-27 19:30", "Rantau Panjang"), ("synthetic_calm", "2024-06-15 10:00", "Kota Bharu"),
          ("synthetic_silent_upstream", "2024-06-15 10:00", "Pasir Mas"), ("synthetic_rising", "2024-11-25 18:00", "Tumpat")]
JARGON = re.compile(r"\b(gauges?|rules?|critic|sentinels?|triggers?|JPS level|controlling|fail-safe|stesen utama)\b", re.I)
MARKER = "kodQZXWV Siti 0123456789"


@pytest.fixture(scope="module")
def views(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("SAMPLE_MODE", "true")
    gazetteer.clear_cache()
    out = {}
    try:
        for replay, at, town in SCENES:
            when = datetime.strptime(at, "%Y-%m-%d %H:%M").replace(tzinfo=config.MYT)
            r = loop.run(f"{MARKER} is {town} safe?", quiet=True, replay=replay, at=when,
                         log_dir=tmp_path_factory.mktemp("logs"))
            out[replay] = (r, view.answer_view(r))
    finally:
        gazetteer.clear_cache()
        mp.undo()
    return out


def _public_strings(v, lang):
    """Every string a person reads on the answer screen (the strip says 'official river gauge' on purpose: Cowork's
    wording for live data - it is checked separately)."""
    out = [v["headline"][lang], v["line"][lang], v["todo"][lang], v["why"][lang]] + v["upstream"][lang]
    if v["water"]:
        out += [v["water"][lang]["main"], v["water"][lang]["compare"]]
    if v["rain"]:
        out.append(v["rain"][lang])
    if v["label"]:
        out.append(v["label"][lang])
    out += [s["name"] + " " + s["note"] for s in v["sources"][lang]]
    return out


def test_both_languages_complete_and_headlines_fixed(views):
    for replay, (r, v) in views.items():
        assert v["verdict"] == r["forecast"]["verdict"]
        assert v["headline"] == view.HEADLINE[v["verdict"]]
        for lang in ("en", "ms"):
            assert all(_public_strings(v, lang)), (replay, lang)
            assert v["sources"][lang] and v["share"][lang]
        assert v["line"]["en"] != v["line"]["ms"] and v["why"]["en"] != v["why"]["ms"]


def test_headline_words_match_the_review_pack():
    assert [view.HEADLINE[k]["en"] for k in ("NORMAL", "WATCH", "PREPARE", "ACT", "INSUFFICIENT_DATA")] == [
        "Normal for now", "Keep watching", "Get ready", "Act now", "Can't confirm right now"]
    assert [view.HEADLINE[k]["ms"] for k in ("NORMAL", "WATCH", "PREPARE", "ACT", "INSUFFICIENT_DATA")] == [
        "Normal buat masa ini", "Terus berjaga-jaga", "Bersedia", "Bertindak sekarang", "Tidak dapat disahkan sekarang"]


def test_no_jargon_on_the_public_screen(views):
    for replay, (_, v) in views.items():
        for lang in ("en", "ms"):
            for s in _public_strings(v, lang):
                assert not JARGON.search(s), (replay, lang, s)


def test_share_text_never_carries_the_question(views):
    for _, (_, v) in views.items():
        for lang in ("en", "ms"):
            text = v["share"][lang]
            assert not any(piece in text for piece in MARKER.split()), text
            assert "999" in text and v["headline"][lang] in text


def test_labels_say_replay_or_made_up(views):
    assert views["nov2024"][1]["label"]["en"].startswith("Past flood replay")
    assert views["nov2024"][1]["strip"]["en"] == ("✓ Double-checked · combined from 2 sources: river here, rain"
                                                  " · 2 left out")
    assert "(reading reported in the news)" in views["nov2024"][1]["water"]["en"]["main"]
    for key in ("synthetic_calm", "synthetic_rising", "synthetic_silent_upstream"):
        v = views[key][1]
        assert v["label"]["en"].startswith("Made-up test scene") and v["label"]["ms"].startswith("Senario ujian rekaan")
        assert "(made-up test reading)" in v["water"]["en"]["main"] and v["synthetic"]


def test_rising_line_agrees_with_the_water_row(views):
    for _, (_, v) in views.items():
        if not v["water"]:
            continue
        main = v["water"]["en"]["main"]
        if "still rising" in v["line"]["en"]:
            assert "rising" in main, main
        if "about the same" in main:
            assert "rising" not in v["line"]["en"] and "falling" not in v["line"]["en"]


def test_act_replay_rows(views):
    v = views["nov2024"][1]
    assert v["verdict"] == "ACT" and v["line"]["en"] == "The river is 1.94 m above the danger level and still rising."
    assert v["water"]["en"]["main"] == ("10.94 m at 19:30 (reading reported in the news) · rising 12-15 cm an hour"
                                        " · up 35 cm in 3 hours")
    assert v["combined"] is None                      # the river here alone already says Act now
    assert v["upstream"]["en"] == ["No fresh reading upstream (Kg. Jenob) - VEDA can't see what may be coming."]
    assert v["why"]["en"] == "The river is at or above the danger level."
    out = [s for s in v["sources"]["en"] if not s["used"]]
    assert any(s["note"] == "left out: reading too old (29 h ago)" for s in out)


def test_every_verdict_rule_has_a_why_sentence():
    src = open(forecast_agent.__file__, encoding="utf-8").read()
    rules = set(re.findall(r'"((?:level>=|danger<=|alert<=|sentinel>=)[a-z0-9]+|rain-[a-z-]+|rising-fast|no-trigger|fail-safe)"', src))
    rules |= {f"level>={k}" for k in ("alert", "warning", "danger")}
    assert rules - {"level>="} <= set(view.WHY), sorted(rules - set(view.WHY))
    fc = {"verdict": "PREPARE", "triggers": [
        {"level": "PREPARE", "rule": "sentinel>=danger", "reason": "x"}, {"level": "WATCH", "rule": "alert<=24h",
                                                                          "reason": "could reach alert in about 3.5 h"}],
          "upstream": [{"gauge": "Sg. Galas di Dabong (F1)", "band": "danger", "arrives_in_h": {"min": 6, "max": 10}}]}
    assert view.why(fc, "en") == ("The river upstream at Dabong is at the danger level; the water may reach here in "
                                  "6-10 hours.")
    assert "Dabong" in view.why(fc, "ms")


def test_words_for_the_emergency_screen():
    w = view.words()
    for lang in ("en", "ms"):
        steps = w["emergency"]["steps"][lang]
        assert len(steps) >= 3 and any("999" in s for s in steps)
        assert w["safety"][lang]


def test_api_serves_view_and_words(views):
    from app import main
    r, v = views["nov2024"]
    out = main.result_json(r)
    assert out["view"] == json.loads(json.dumps(v, ensure_ascii=False))
    from starlette.testclient import TestClient
    c = TestClient(main.app)
    assert c.get("/ui/words").json()["headline"]["ACT"]["ms"] == "Bertindak sekarang"


def test_page_is_self_contained_and_bilingual():
    html = (config.ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
    assert not re.search(r'<(script|link)[^>]+(src|href)="https?:', html)      # nothing loaded from outside
    assert 'href="tel:999"' in html and 'href="tel:991"' in html
    assert "veda.lang" in html and 'startsWith("ms")' in html                  # remembered; browser language first
    block = lambda name: html.split(f"  {name}: {{", 1)[1].split("\n  },", 1)[0]          # noqa: E731
    keys = lambda b: set(re.findall(r"(\w+): [\"\[]", b))                                  # noqa: E731
    assert keys(block("en")) == keys(block("ms"))                                         # every UI word in both
    for name in ("s-home", "s-wait", "s-answer", "s-share", "s-sos"):
        assert f'id="{name}"' in html
    assert "font-size: 18px" in html and "min-height: 48px" in html


def test_how_it_worked_from_a_recorded_live_run():
    path = next((config.ROOT / "data" / "sample" / "live_traces").glob("*2341MYT*.jsonl"))
    h = view.how_it_worked(path)
    keys = [r["key"] for r in h["rows"]]
    assert keys[:5] == ["plan", "gather", "forecast", "draft", "critique"] and keys[-1] == "safety"
    draft = h["rows"][keys.index("draft")]
    assert draft["ai"][0]["model"] == "nvidia/nemotron-3.5-super-vl-120b-a12b" and draft["ai"][0]["receipt"]
    assert draft["seconds"] == 34.7 and h["total_s"] == 49.1
    critic = h["rows"][keys.index("critique")]
    assert critic["ai"] and any("code checks" in line["text"] for line in critic["lines"])
    question = json.loads(path.read_text(encoding="utf-8").splitlines()[1])["input_summary"]
    assert question not in json.dumps(h, ensure_ascii=False)


def test_how_it_worked_offline_marks_the_fallback(views):
    r, _ = views["nov2024"]
    h = view.how_it_worked(r["trace"])
    draft = next(row for row in h["rows"] if row["key"] == "draft")
    assert not draft["ai"] and any(line["status"] == "fallback" for line in draft["lines"])
    assert "kodQZXWV" not in json.dumps(h) and sum(row["queries"] for row in h["rows"]) > 0
    from app import main
    assert main.result_json(r)["how"] == h


def test_hide_question_walks_and_catches_shortened_copies():
    q = "Mak saya di Tumpat, kena pindah malam ni?"
    v = view.hide_question({"a": [q[:20] + "…", "other"], "details": {"normalized": "mak saya tumpat"}}, q, "X")
    assert v == {"a": ["X", "other"], "details": {"normalized": "X"}}


def test_strip_counts_used_and_left_out_from_the_run(views):
    v = views["synthetic_silent_upstream"][1]
    used = [s for s in v["sources"]["en"] if s["used"]]
    dropped = [s for s in v["sources"]["en"] if s["left_out"]]
    assert v["strip"]["en"].startswith(f"✓ Double-checked · combined from {len(used)} sources: river here, river upstream")
    assert v["strip"]["en"].endswith(f" · {len(dropped)} left out")
    assert any(s["note"].startswith("not used: ") for s in v["sources"]["en"])       # not asked for != left out


def test_combined_sentence_when_more_than_the_river_here_decides(views):
    v = views["synthetic_silent_upstream"][1]
    assert v["verdict"] == "WATCH"
    assert v["combined"]["en"] == ("The river here alone would say “Normal for now”; it is the river upstream that "
                                   "raises this to “Keep watching”.")
    assert "sungai di hulu" in v["combined"]["ms"]
    fc = {"verdict": "PREPARE", "triggers": [{"level": "WATCH", "rule": "level>=alert"},
                                             {"level": "PREPARE", "rule": "rain-heavy"},
                                             {"level": "PREPARE", "rule": "sentinel>=danger"}]}
    assert view.combined(fc, "en") == ("The river here alone would say “Keep watching”; it is the river upstream and "
                                       "the rain forecast that raise this to “Get ready”.")


def test_states_without_a_place_card():
    assert view.other_view({"plan": {"place_status": "unavailable"}})["text"]["en"].startswith("VEDA can't answer")
    nc = view.other_view({"plan": {"place_status": "not_covered", "nearest": {"name": "Rantau Panjang", "km": 125}}})
    assert nc["text"]["en"] == ("VEDA covers Rantau Panjang, Pasir Mas, Kota Bharu and Tumpat for now. "
                                "The nearest is Rantau Panjang.") and nc["nearest"] == "Rantau Panjang"
    assert view.other_view({"plan": {"place_status": "did_you_mean", "suggestions": ["Tumpat"]}})["suggestions"] == ["Tumpat"]
    assert view.other_view({"plan": {"place_status": "found"}}) is None


def test_calm_and_cant_confirm_lines(views):
    assert views["synthetic_calm"][1]["note"]["en"] == "Nothing to do now. VEDA checks again whenever you ask."
    card = {"verdict": "INSUFFICIENT_DATA", "gauge": None, "replay": None}
    assert view._line(card, {}, "en").startswith("We could not get a fresh river reading, so we will not guess.")
