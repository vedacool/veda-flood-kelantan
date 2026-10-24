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
        out += [v["water"][lang]["main"]] + v["water"][lang]["detail"]
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
            assert "999" in text and v["headline"][lang].upper() in text
            # v2 share text (Cowork 24 Oct): who checked, when, from what - and a replay or test scene says so
            assert ("Checked by VEDA · " if lang == "en" else "Disemak oleh VEDA · ") in text
            if v.get("label"):
                assert v["label"][lang] in text
            if v["synthetic"]:
                assert "SYNTHETIC" in text


def test_labels_say_replay_or_made_up(views):
    assert views["nov2024"][1]["label"]["en"].startswith("Past flood replay")
    assert views["nov2024"][1]["strip"]["en"] == "✓ Checked twice, using 3 sources"    # Cowork 24 Oct: which, in Details
    assert views["nov2024"][1]["strip"]["ms"] == "✓ Disemak dua kali, menggunakan 3 sumber"
    assert "(reading reported in the news)" in views["nov2024"][1]["water"]["en"]["detail"][0]
    for key in ("synthetic_calm", "synthetic_rising", "synthetic_silent_upstream"):
        v = views[key][1]
        assert v["label"]["en"].startswith("Made-up test scene") and v["label"]["ms"].startswith("Senario ujian rekaan")
        assert "(made-up test reading)" in v["water"]["en"]["detail"][0] and v["synthetic"]


def test_rising_line_agrees_with_the_water_row(views):
    for _, (_, v) in views.items():
        if not v["water"]:
            continue
        main = v["water"]["en"]["main"]
        if "still rising" in v["line"]["en"]:
            assert main.startswith("Rising"), main
        if "about the same" in main:
            assert "rising" not in v["line"]["en"] and "falling" not in v["line"]["en"]


def test_act_replay_rows(views):
    v = views["nov2024"][1]
    assert v["verdict"] == "ACT" and v["line"]["en"] == "The river is 1.94 m above the danger level and still rising."
    assert v["water"]["en"]["main"] == "Rising about 12–15 cm an hour. Already 1.94 m over the danger mark."
    assert v["water"]["en"]["detail"] == [
        "10.94 m at 19:30 (reading reported in the news) · rising 12–15 cm an hour · up 35 cm in 3 hours",
        "3.94 m above the alert level (7 m)", "1.94 m above the danger level (9 m)"]
    assert v["water"]["ms"]["main"] == "Naik kira-kira 12–15 cm sejam. Sudah 1.94 m melebihi paras Bahaya."
    assert v["combined"] is None                      # the river here alone already says Act now
    assert v["upstream"]["en"] == [                      # Cowork 24 Oct: plain words, no gauge names or mm
        "Very heavy rain across the border in Thailand over the last 3 days. That water flows down towards here.",
        "We have no fresh river reading upstream, so we can't see exactly what is coming."]
    assert v["rain"]["en"] == "Heavy rain here in the last day."
    assert v["rain_detail"]["en"][0].startswith("Heavy rain upstream: Buke Ta (Waeng; Thailand)")     # numbers: Details
    assert "No fresh reading upstream (Kg. Jenob) - VEDA can't see what may be coming." in v["rain_detail"]["en"]
    assert "evacuation centre (PPS)" in v["todo"]["en"] and "pusat pemindahan (PPS)" in v["todo"]["ms"]
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
                                  "6–10 hours.")
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
    assert v["strip"]["en"] == f"✓ Checked twice, using {len(used)} sources" and dropped    # left out: in Details
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
    assert nc["text"]["en"] == ("VEDA covers Kota Bharu, Pasir Mas, Rantau Panjang and Tumpat for now. "
                                "The nearest is Rantau Panjang.") and nc["nearest"] == "Rantau Panjang"
    nine = view.other_view({"plan": {"place_status": "not_covered", "covered": ["Dabong", "Kota Bharu", "Tumpat"]}})
    assert nine["text"]["ms"] == "Buat masa ini VEDA meliputi Dabong, Kota Bharu dan Tumpat."   # A7: from the finder
    assert view.other_view({"plan": {"place_status": "did_you_mean", "suggestions": ["Tumpat"]}})["suggestions"] == ["Tumpat"]
    assert view.other_view({"plan": {"place_status": "found"}}) is None


def test_calm_and_cant_confirm_lines(views):
    assert views["synthetic_calm"][1]["note"]["en"] == "Nothing to do now. VEDA checks again whenever you ask."
    card = {"verdict": "INSUFFICIENT_DATA", "gauge": None, "replay": None}
    assert view._line(card, {}, "en").startswith("We could not get a fresh river reading, so we will not guess.")


def test_verdict_colours_have_contrast_and_differ_in_lightness():
    """Accessibility pass 24 Oct: text on each verdict colour >= 4.5:1, and the colours differ in lightness (not only
    hue) so the verdict reads without colour vision."""
    html = (config.ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")

    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    lums = []
    for v in ("normal", "watch", "prepare", "act", "unknown"):
        bg = re.search(rf"--v-{v}: (#[0-9a-f]{{6}})", html).group(1)
        fg = re.search(rf"--on-{v}: (#[0-9a-f]{{6}})", html).group(1)
        a, b = sorted((lum(bg), lum(fg)), reverse=True)
        assert (a + 0.05) / (b + 0.05) >= 4.5, v
        lums.append(lum(bg))
    lums.sort()
    assert all(hi / lo >= 1.3 for lo, hi in zip(lums, lums[1:])), lums


def test_hide_question_keeps_a_place_name_that_is_only_part_of_it():
    q = "Is Rantau Panjang at risk of flooding right now?"
    v = view.hide_question({"input": "Rantau Panjang", "cut": q[:30] + "...", "copy": q[:-1]}, q, "X")
    assert v == {"input": "Rantau Panjang", "cut": "X", "copy": "X"}


def test_line_under_the_badge_says_what_set_the_verdict(views):
    """Cowork 24 Oct: never 'Get ready' over a calm-river line - the reason that set the verdict, in plain words."""
    assert views["nov2024"][1]["line"]["en"] == "The river is 1.94 m above the danger level and still rising."
    assert views["synthetic_silent_upstream"][1]["line"]["en"] == "The river upstream is high, and the water may be on its way."
    fc = {"verdict": "PREPARE", "triggers": [{"level": "WATCH", "rule": "upstream-rain"},
                                             {"level": "PREPARE", "rule": "upstream+local-rain"}]}
    assert view.set_by(fc) == "rain_both"
    assert view.SET_BY["rain_both"]["en"] == "Heavy rain upstream is on its way, and it is raining hard here."
    assert view.set_by({"verdict": "PREPARE", "triggers": [{"level": "WATCH", "rule": "level>=alert"},
                                                           {"level": "PREPARE", "rule": "rising-fast"}]}) == "river"


def test_water_row_is_one_plain_sentence(views):
    assert views["synthetic_calm"][1]["water"]["en"]["main"] == "The sea tide moves this river, so we don't show a trend."
    card = {"comparison": {"alert": -1.0, "danger": -3.0}, "tidal": False}
    fc = {"controlling": [{"role": "controlling", "rate_m_per_h": {"min": 0.0, "max": 0.002}}]}
    assert view._water_plain(card, fc, "en") == "Calm, below the alert mark."
    card["comparison"] = {"alert": 0.3, "danger": -0.7}
    assert view._water_plain(card, fc, "en") == "Steady. Over the alert mark, 0.7 m under the danger mark."


# -- Cowork 24 Oct demo UI round ----------------------------------------------------------------------------------
def test_pps_reads_evacuation_centre_on_screens_but_the_card_keeps_pps():
    from app import card
    assert view.plain_pps(card.ADVICE["ACT"]["en"], "en").startswith(
        "Follow APM / police instructions and go to the evacuation centre (PPS) if told.")
    assert "pusat pemindahan (PPS) terdekat - tanya ketua kampung / JKKK." in view.plain_pps(card.ADVICE["PREPARE"]["ms"], "ms")
    assert "go to the PPS if told" in card.ADVICE["ACT"]["en"]                      # the length-capped card text
    assert view.words()["emergency"]["steps"]["en"][0].endswith("evacuation centre (PPS) if told.")


def test_strip_is_short_and_says_one_source_singular():
    rows = [{"kind": "river", "used": True, "left_out": False}, {"kind": "rain", "used": False, "left_out": True}]
    assert view._strip({"approved": True}, rows, "en") == "✓ Checked twice, using 1 source"
    assert view._strip({"approved": False}, rows * 2, "ms") == "✓ Disemak, menggunakan 2 sumber"


def test_demo_page_has_the_moment_chips_intro_and_peak_default():
    from app import trace
    page = (trace.ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'const PEAK = "nov2024|2024-11-27 19:30"' in page and "if (sampleMode && !want) $(\"mode\").value = PEAK;" in page
    assert '"Replay of the November 2024 Kelantan flood. Start with Rantau Panjang."' in page      # one line (24 Oct)
    assert '"Ulang tayang banjir Kelantan November 2024. Mula dengan Rantau Panjang."' in page
    assert page.index('id="towns"') < page.index('id="few-readings"')        # the readings note under the town list
    for key in ("before", "morning", "peak", "test_scenes", "tap_skip", "c_gather", "c_critique", "few_readings"):
        assert page.count(f"{key}: ") == 2, key                                      # EN and BM
    assert page.index('id="a-again"') < page.index('class="sos outline" id="a-sos"')    # outlined, at the bottom
    assert 'class="btn wa wide" id="sh-wa"' in page                                  # share screen: the same green


# -- v2 answer screen (Cowork blueprint 24 Oct) -------------------------------------------------------------------
def test_v2_act_now_block_steps_post_and_flow(views):
    v = views["nov2024"][1]
    assert v["level"] == 4 and v["level_text"]["en"] == "Level 4 of 4" and v["level_text"]["ms"] == "Tahap 4 daripada 4"
    assert v["action"]["en"] == ["Move to higher ground. Follow APM / police."]
    assert len(v["steps"]["en"]) == 3 and v["steps"]["en"][2].endswith("Don't go back for animals or things.")
    assert v["steps"]["en"][0].startswith("Follow APM / police instructions and go to the evacuation centre (PPS)")
    r = v["river"]["en"]
    assert (r["alert_m"], r["warning_m"], r["danger_m"], r["y2014_m"]) == (7.0, 8.0, 9.0, 10.84)   # the gauge's own
    assert r["lines"][:2] == ["10.94 m now", "1.94 m above the danger mark"]
    assert not any("hours to the danger" in x for x in r["lines"])             # already over it: no time line
    assert [d["state"] for d in v["flow"]["en"]["dots"]] == ["rain", "none", "you"]
    assert v["flow"]["en"]["dots"][0]["name"] == "Thailand" and v["official_link"] is None


def test_v2_cant_confirm_and_get_ready():
    from app import card
    assert view.steps("INSUFFICIENT_DATA", "en") == [
        "If water is rising around you, don't wait for us: move to higher ground.",
        "Check the official river levels yourself.", "In danger, call 999."]
    assert view.action_lines("INSUFFICIENT_DATA", "Pasir Mas", "ms") == ["Kami tiada bacaan sungai terkini untuk Pasir Mas."]
    prep = view.steps("PREPARE", "en")
    assert prep[1] == "Move the car, animals and valuables to higher ground now, while it's easy." and len(prep) == 3
    assert view.action_lines("PREPARE", "X", "en")[1].startswith("Older people, the sick and babies")
    assert "go to the PPS if told" in card.ADVICE["ACT"]["en"]                    # the plain-text card keeps PPS


def test_upstream_dots_follow_the_river_chain_hulu_to_hilir():
    """Cowork 24 Oct: order from the river chain (chain_order grows downstream), never from the list order."""
    up = [{"gauge": "Sg. Kelantan di Kg. Salor (F1)", "band": "normal", "rising": False, "chain_order": 7},
          {"gauge": "Sg. Kelantan di Kuala Krai (F1)", "band": "alert", "rising": True, "chain_order": 4},
          {"gauge": "Sg. Kelantan di Jambatan Tendong (F2)", "band": "warning", "rising": True, "chain_order": 6}]
    f = view.flow({"place": "Kota Bharu"}, {"upstream": up}, "en")
    assert [d["name"] for d in f["dots"]] == ["Jambatan Tendong", "Kg. Salor", "Kota Bharu"]   # the two nearest, in order
    assert [d["state"] for d in f["dots"]] == ["high", "normal", "you"]
    rain = {"place": "Kota Bharu", "rain_up": {"heavy": [{"name": "Kuala Krai", "past_72h_mm": 120, "fallen": True}]}}
    assert [d["name"] for d in view.flow(rain, {"upstream": up}, "en")["dots"]] == ["Kuala Krai", "Kg. Salor", "Kota Bharu"]
    unknown = [dict(u, chain_order=None) for u in up]                      # no chain data: the list order is kept
    assert [d["name"] for d in view.flow({"place": "X"}, {"upstream": unknown}, "en")["dots"]][:2] == \
        ["Kuala Krai", "Jambatan Tendong"]


def test_real_scene_upstream_gauges_carry_their_chain_order(views):
    for key in ("nov2024", "synthetic_silent_upstream", "synthetic_rising"):
        ups = views[key][0]["forecast"]["upstream"]
        assert ups and all(isinstance(u["chain_order"], int) for u in ups), key


def test_level_unknown_and_keep_watching_line_match_the_steps():
    assert view.V2["no_level"] == {"en": "Level unknown", "ms": "Tahap tidak diketahui"}
    assert view.action_lines("WATCH", "X", "en") == ["Check again in 3 hours."] == view.steps("WATCH", "en")[:1]
    assert view.action_lines("WATCH", "X", "ms")[0] == view.steps("WATCH", "ms")[0]
    assert view._range_cm(0.12, 0.15) == "12–15" and view.dash("in 9-17 h") == "in 9–17 h"


def test_explanation_lang_is_the_question_language_or_none(views):
    """A4 (24 Oct evening): the AI paragraph is written once, in the question's language; the result says which."""
    import copy
    from app import main
    r, _ = views["nov2024"]
    assert main.result_json(r)["explanation_lang"] is None                     # offline: no AI paragraph
    r2 = copy.deepcopy(r)
    r2["answer"].update(explanation="Paras sungai melebihi paras Bahaya.", approved=True, language="ms")
    assert main.result_json(r2)["explanation_lang"] == "ms"
    r2["answer"]["approved"] = False                                            # not approved -> not shown
    assert main.result_json(r2)["explanation_lang"] is None


def test_how_it_worked_lines_have_no_station_codes(views):
    """A5: the 'How VEDA worked this out' rows show plain step text; the trace keeps '(F1)'."""
    r, _ = views["nov2024"]
    lines = [l["text"] for row in view.how_it_worked(r["trace"])["rows"] for l in row["lines"]]
    assert lines and not any(re.search(r"\(F\d+\)", t) or re.search(r"(^|[:-]\s)(full|quick):\s", t) for t in lines)
    assert "(F1)" in open(r["trace"], encoding="utf-8").read()
