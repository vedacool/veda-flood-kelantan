"""B-73 tests: OpenStreetMap lines on the card (possible PPS for an evacuation question, bridges + low ground for a
cut-off question), the ODbL credit, the 'not an official list' label, and the approved checks - no text may say a PPS
is open or predict a road / bridge being cut off (card, Critic code checks, safety gate)."""
import pytest

from app import card, safety, trace
from app.agents import critic
from tests.test_card import EVIDENCE, forecast

PPS = [{"name": "SK Contoh", "category": "school", "km": 1.2}, {"name": "Masjid Contoh", "category": "masjid", "km": 0.8},
       {"name": "Surau Contoh", "category": "surau", "km": 2.5}, {"name": "Balai Raya Contoh", "category": "community_hall",
                                                                  "km": 3.0}]
BRIDGES = [{"name": "Jambatan Contoh", "river": "Sg. Golok", "km": 2.1, "band": "danger", "gauge": "G", "gauge_km": 0.5,
            "has_gauge": True},
           {"name": "Jalan Contoh", "river": "Sg. Golok", "km": 4.0, "band": None, "gauge": "G", "gauge_km": 3.0,
            "has_gauge": True},
           {"name": "FT 3", "river": "Sg. Lemal", "km": 6.0, "band": None, "gauge": None, "gauge_km": None,
            "has_gauge": False}]


SHORT = dict(EVIDENCE, cross_check={}, context=dict(EVIDENCE["context"], rain=None, met_forecast=None))


def build(intent, osm=None, verdict="WATCH", base=SHORT):
    ev = dict(base, osm=osm if osm is not None else {"status": "ok", "pps": PPS, "bridges": BRIDGES,
                                                          "loaded_at": "2026-10-23T09:40:00+00:00"})
    return card.build({"place": {"name": "Rantau Panjang"}, "intent": intent}, ev, forecast(verdict=verdict))


@pytest.mark.parametrize("lang,label", [("en", "Possible PPS — not an official list, confirm with APM / the village head"),
                                        ("ms", "Kemungkinan PPS — bukan senarai rasmi, sahkan dengan APM / ketua kampung")])
def test_evacuation_question_lists_possible_pps_with_the_label(lang, label):
    text = card.render(build("evacuation"), lang)
    line = next(l for l in text.split("\n") if l.startswith(label))
    assert "SK Contoh (1.2 km); Masjid Contoh (0.8 km); Surau Contoh (2.5 km)" in line       # 3 shown
    assert "Balai Raya" not in text and "Jambatan" not in text and "Sg. Lemal" not in text
    assert "© OpenStreetMap contributors (ODbL)" in text


def test_cut_off_question_states_bridge_facts_only():
    ms = card.render(build("cut_off"), "ms")
    assert "Jambatan Contoh merentasi Sg. Golok (2.1 km); paras sungai di situ: Bahaya." in ms
    assert "Jambatan di Jalan Contoh merentasi Sg. Golok (4 km); paras sungai di situ: tiada bacaan terkini." in ms
    assert "FT 3" not in ms                                                               # 2 bridges shown
    assert "VEDA belum mengetahui kawasan mana yang rendah." in ms and "PPS" not in ms.split("WHAT")[0].split("\n", 1)[1]
    en = card.render(build("cut_off"), "en")
    assert "Jambatan Contoh crosses Sg. Golok (2.1 km); river level there: Danger." in en
    assert "VEDA does not know yet which areas are low-lying." in en
    for text in (ms, en):
        assert card.osm_claim(text) is None and "putus" not in text and "cut off" not in text


def test_bridge_without_a_gauge_on_its_river_says_so():
    c = build("cut_off", {"status": "ok", "pps": [], "bridges": BRIDGES[2:], "loaded_at": None})
    assert "Bridge on FT 3 crosses Sg. Lemal (6 km); river level there: no JPS gauge nearby on this river." in \
        card.render(c, "en")


def test_nothing_found_and_unreadable_table_are_said_plainly():
    none = build("evacuation", {"status": "ok", "pps": [], "bridges": [], "loaded_at": None})
    assert "Possible PPS: none named in OpenStreetMap within 10 km" in card.render(none, "en")
    failed = build("cut_off", {"status": "failed", "pps": [], "bridges": [], "loaded_at": None})
    text = card.render(failed, "ms")
    assert "Tidak disemak: OpenStreetMap (tidak dapat dibaca)." in text and "ODbL" not in text


def test_risk_question_gets_no_osm_lines():
    assert build("risk_check")["osm"]["pps"] is None and build("risk_check")["osm"]["bridges"] is None
    text = card.render(build("risk_check"), "en")
    assert "PPS" not in text.split("\n", 1)[1].replace(card.ADVICE["WATCH"]["en"], "") and "crosses" not in text


def test_osm_lines_sit_outside_the_cap_and_other_lines_still_fit():
    """Husaini 23 Oct: up to 3 possible PPS and 2 bridges past the ~750 cap (evacuation / cut-off questions only)."""
    full = card.render(build("cut_off", base=EVIDENCE), "ms")          # stale source + rain + forecast: over the cap
    assert "Jambatan Contoh merentasi" in full and "Jalan Contoh merentasi" in full and "kawasan mana yang rendah" in full
    rest = [l for k, l in card._lines(build("cut_off", base=EVIDENCE), "ms", None, False, set(card.FIT_STEPS))
            if k not in card.OSM_LINES]
    assert card._length([(None, l) for l in rest]) <= card.MAX_CARD_CHARS + 100     # the cap still trims the rest
    c = build("evacuation", verdict="ACT")
    c["upstream"] = [{"gauge": f"Sg. Contoh di Hulu {i} (F1)", "band": "danger", "rising": True,
                      "arrives_in_h": {"min": 3, "max": 6}} for i in range(4)]
    text = card.render(c, "ms")
    assert "SK Contoh (1.2 km); Masjid Contoh (0.8 km); Surau Contoh (2.5 km)" in text


def test_key_facts_carry_the_label_and_the_bridge_facts():
    f = card.key_facts(build("evacuation"), lang="ms")
    assert f["possible_pps"]["note"].startswith("Kemungkinan PPS — bukan senarai rasmi")
    b = card.key_facts(build("cut_off"), lang="en")["bridges"]
    assert b[0].startswith("Jambatan Contoh crosses Sg. Golok") and b[-1] == "VEDA does not know yet which areas are low-lying"


@pytest.mark.parametrize("text", [
    "PPS di SK Contoh sudah dibuka.", "The relief centre at SK Contoh is open now.", "Jalan ke kampung akan terputus.",
    "Jambatan Contoh boleh putus malam ini.", "The road may be cut off tonight.", "Bridges could be flooded soon.",
    "Jalan Contoh mungkin ditenggelami air."])
def test_open_pps_and_cut_off_predictions_are_caught(text):
    assert card.osm_claim(text)
    assert "cut off" in card.explanation_problem(text, build("evacuation")) or "PPS" in \
        card.explanation_problem(text, build("evacuation"))


@pytest.mark.parametrize("text", ["Sahkan PPS dengan APM atau ketua kampung.", "Confirm the PPS with APM first.",
                                  "Sungai di Rantau Panjang di paras Waspada.", "If trapped, stay on high ground."])
def test_plain_advice_is_not_a_claim(text):
    assert card.osm_claim(text) is None


def test_critic_needs_the_label_when_pps_are_shown():
    c = build("evacuation")
    good = card.render(c, "en")
    assert not [f for f in critic.code_checks(good, {}, EVIDENCE, card=c) if "PPS" in f["detail"]]
    bad = good.replace(" — not an official list, confirm with APM / the village head", "")
    assert any("not an official list" in f["detail"] for f in critic.code_checks(bad, {}, EVIDENCE, card=c))


def test_safety_gate_drops_an_explanation_that_says_a_pps_is_open(tmp_path):
    trace.start_run("t", log_dir=tmp_path, quiet=True)
    c = build("evacuation")
    expl = "PPS di SK Contoh sudah dibuka."
    answer = {"language": "ms", "explanation": expl, "drafted_by": "model", "text": card.render(c, "ms", expl)}
    out = safety.gate(answer, c, dict(EVIDENCE), forecast())
    assert out["explanation"] is None and expl not in out["text"]
    assert any("PPS is open" in f for f in out["safety"]) and not any("BUG" in f for f in out["safety"])
    trace.end_run("success")


def test_a_numeric_road_ref_is_still_a_name():
    """Zetaris reads a bridge named only by its road ref ('223') as a number - the card must still render (live 23 Oct)."""
    from types import SimpleNamespace
    from app.agents import data_agent
    rec = {"place_id": "kota_bharu", "kind": "bridge", "osm_ref": "way/1", "name": 223, "category": "secondary",
           "river": "Sg. Pengkalan Chepa", "km": 2.0, "station_key": None, "gauge_km": None, "loaded_at": "x"}
    osm = data_agent.osm_features(SimpleNamespace(records=[rec]), {"place_id": "kota_bharu"}, None, None)
    c = build("cut_off", osm)
    assert "Bridge on 223 crosses Sg. Pengkalan Chepa (2 km)" in card.render(c, "en")
    assert card.key_facts(c, lang="en")["bridges"][0].startswith("Bridge on 223")


def test_card_lists_schools_and_halls_first():
    from types import SimpleNamespace
    from app.agents import data_agent
    rec = lambda name, cat, km: {"place_id": "p", "kind": "pps_candidate", "osm_ref": name, "name": name,  # noqa: E731
                                 "category": cat, "river": None, "km": km, "station_key": None, "gauge_km": None,
                                 "loaded_at": "x"}
    osm = data_agent.osm_features(SimpleNamespace(records=[rec("Masjid A", "masjid", 0.1), rec("SK B", "school", 2.0),
                                                           rec("Dewan C", "community_hall", 1.0)]),
                                  {"place_id": "p"}, None, None)
    assert [p["name"] for p in osm["pps"]] == ["Dewan C", "SK B", "Masjid A"]
