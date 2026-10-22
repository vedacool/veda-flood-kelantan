"""B-17 router tests: answer language (BM / EN / mixed / Kelantan dialect), question triggers, data triggers and
MetMalaysia warnings (stale feed triggers nothing, sea warnings don't count, district lists)."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import router, trace
from app.agents import data_agent


@pytest.mark.parametrize("question, lang", [
    ("Is Rantau Panjang at risk of flooding?", "en"),
    ("Kota Bharu ok?", "en"),
    ("Adakah Tumpat selamat malam ini?", "ms"),
    ("Is Pasir Mas ok tak?", "ms"),                                   # mixed BM/EN -> BM
    ("My mak lives in Tumpat, should she move?", "ms"),
    ("Air naik doh ko Rantau Panjang?", "ms"),                        # Kelantan dialect
    ("Gapo jadi sungai Golok malam ni?", "ms"),
    ("Demo dok Pasir Mas, nok tubik ke dok?", "ms"),
])
def test_language_any_bm_word_means_bm(question, lang):
    assert router.language(question) == lang


@pytest.mark.parametrize("question, kind", [
    ("Should my parents evacuate?", "evacuation"),
    ("Kena pindah ke?", "evacuation"),
    ("Where is the nearest PPS?", "evacuation"),
    ("Kami terkandas di rumah", "cut_off"),
    ("Mak terperangkap, tak boleh keluar", "cut_off"),
    ("Tak leh keluar rumah doh", "cut_off"),
    ("We are trapped", "cut_off"),
    ("Stranded near Rantau Panjang", "cut_off"),
    ("Air naik doh?", "rising_water"),
    ("Is the river rising?", "rising_water"),
    ("Banjir tak minggu ni?", "next_days"),
    ("Malam ni macam mana?", "next_days"),
    ("Will Tumpat flood tomorrow?", "next_days"),
    ("Is it safe this week?", "next_days"),
    ("Esok sekolah buka?", "next_days"),
])
def test_question_triggers(question, kind):
    assert kind in [k for k, _ in router.question_triggers(question)]


@pytest.mark.parametrize("question", ["Kota Bharu ok?", "What is the level at Rantau Panjang now?",
                                      "Paras air Tumpat sekarang?", "Kampung Pasir Mas"])
def test_simple_questions_trigger_nothing(question):
    assert router.question_triggers(question) == []


def test_words_inside_other_words_do_not_trigger():
    assert router.question_triggers("Is the pindahan form ready? surprise") == []


def gauge(name="Rantau Panjang", band="normal", level=5.5, ch1=0.0, ch3=0.0, age=20, tide=False):
    return {"name": name, "band": band, "level_m": level, "change_1h_m": ch1, "change_3h_m": ch3,
            "age_minutes": age, "tide_influenced": tide}


CALM = {"gauges": [gauge()], "sentinels": [gauge("Kg Jenob")], "rain": {"x": 1}, "met_forecast": {"x": 1}}
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def test_calm_data_triggers_nothing():
    assert router.data_triggers(CALM, {"active": []}, NOW) == []


@pytest.mark.parametrize("change, reason", [
    ({"gauges": [gauge(band="alert", level=7.1)]}, "is at alert"),
    ({"sentinels": [gauge("Kuala Krai", band="danger", level=26)]}, "Kuala Krai is at danger"),
    ({"gauges": [gauge(ch3=0.35)]}, "is rising"),
    ({"gauges": [gauge(ch1=0.2)]}, "is rising"),
    ({"gauges": [gauge(age=200)]}, "no fresh reading (stale)"),
    ({"sentinels": [gauge("Kg Jenob", level=None)]}, "Kg Jenob has no fresh reading (none)"),
    ({"rain": None}, "no rain forecast data"),
    ({"met_forecast": None}, "no MetMalaysia forecast"),
    ({"gauges": []}, "no controlling gauge data"),
])
def test_each_data_trigger(change, reason):
    reasons = router.data_triggers({**CALM, **change}, {"active": []}, NOW)
    assert any(reason in r for r in reasons), reasons


def test_tidal_rise_does_not_trigger():
    assert router.data_triggers({**CALM, "gauges": [gauge(ch3=0.4, tide=True)]}, {"active": []}, NOW) == []


def test_active_warning_triggers_full():
    reasons = router.data_triggers(CALM, {"active": [{"heading": "CONTINUOUS RAIN WARNING"}]}, NOW)
    assert reasons == ["active MetMalaysia warning: CONTINUOUS RAIN WARNING"]


# -- MetMalaysia warnings --------------------------------------------------------------------------------------
PLACE = {"place_id": "tumpat", "name": "Tumpat", "district": "Tumpat"}


def warnings(rows):
    return SimpleNamespace(records=rows, sql="SELECT ...", query_hash="h")


def row(heading="CONTINUOUS RAIN WARNING", text="Continuous rain is expected in Kelantan.", issued="2026-10-22T18:00:00",
        valid_from="2026-10-22T18:00:00", valid_to="2026-10-24T18:00:00"):
    return {"heading_en": heading, "text_en": text, "text_bm": None, "issued": issued, "valid_from": valid_from,
            "valid_to": valid_to}


@pytest.fixture
def run(tmp_path):
    trace.start_run("warnings test", log_dir=tmp_path, quiet=True)
    yield
    trace.end_run()


def test_statewide_rain_warning_is_active(run):
    w = data_agent.met_warnings(warnings([row()]), PLACE, NOW)
    assert w["status"] == "ok" and w["active"][0]["heading"] == "CONTINUOUS RAIN WARNING"


@pytest.mark.parametrize("text, active", [
    ("Continuous rain in Kelantan (Tumpat, Pasir Mas and Kota Bharu).", True),
    ("Continuous rain in Kelantan (Gua Musang and Jeli).", False),
    ("Continuous rain in Terengganu (Besut).", False),
])
def test_district_lists_are_respected(run, text, active):
    assert bool(data_agent.met_warnings(warnings([row(text=text)]), PLACE, NOW)["active"]) is active


def test_sea_and_wind_warnings_do_not_count(run):
    sea = row(heading="SECOND CATEGORY WARNING ON STRONG WINDS AND ROUGH SEAS",
              text="Thunderstorms expected over the waters of Pahang, Terengganu, Kelantan.")
    assert data_agent.met_warnings(warnings([sea]), PLACE, NOW)["active"] == []


def test_expired_warning_is_not_active(run):
    old = row(valid_from="2026-10-20T08:00:00", valid_to="2026-10-21T08:00:00", issued="2026-10-22T18:00:00")
    assert data_agent.met_warnings(warnings([old]), PLACE, NOW)["active"] == []


def test_stale_feed_is_marked_stale_and_triggers_nothing(run):
    w = data_agent.met_warnings(warnings([row(issued="2026-10-01T08:00:00")]), PLACE, NOW)
    assert w["status"] == "stale" and w["active"] == [] and "stale" in w["note"]


def test_unreadable_feed_is_reported(run):
    assert data_agent.met_warnings(None, PLACE, NOW)["status"] == "failed"


@pytest.mark.parametrize("question, kind", [
    ("Sekolah anak saya di Tumpat selamat ke?", "school"),
    ("Cikgu, kena tutup sekolah esok?", "school"),
    ("Guru di Pasir Mas tanya", "school"),
    ("Mak ayah saya di Tumpat", "family_far_away"),
    ("Anak saya tinggal di Kota Bharu", "family_far_away"),
    ("Isteri saya di Rantau Panjang", "family_far_away"),
    ("Rumah mak di Pasir Mas ok?", "family_far_away"),
    ("Orang tua saya di Tumpat", "family_far_away"),
    ("Ada warga emas di kampung", "family_far_away"),
    ("My parents live in Tumpat", "family_far_away"),
    ("Rumah saya di Pasir Mas", "resident"),
    ("I live in Kota Bharu, is it safe?", "resident"),
    ("Kota Bharu ok?", "unknown"),
])
def test_user_type_from_words(question, kind):
    assert router.user_type(question) == kind
