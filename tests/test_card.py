"""B-21 tests: the answer card - advice per verdict (BM + EN), order, comparisons, range, sources, stale and
conflict lines, length, the explanation check (card numbers only), place replies, and that a code-written card
passes the Critic's code checks by construction."""
import re
from types import SimpleNamespace

import pytest

from app import card
from app.agents import coordinator, critic

GAUGE = {"station": "station:jps:_DPMS0003", "name": "Sg. Golok di Rantau Panjang (F1)", "role": "controlling",
         "level_m": [JPS reading], "band": "alert", "observed_at": "2026-10-22T12:45:00Z", "age_minutes": 16,
         "freshness": "fresh", "health": {"ok": True},
         "thresholds": {"normal_m": 5.0, "alert_m": 7.0, "warning_m": 8.0, "danger_m": 9.0}}
EVIDENCE = {"place": {"name": "Rantau Panjang"}, "usable": True, "clock": "2026-10-22T13:00:00Z",
            "context": {"gauges": [GAUGE], "sentinels": [],
                        "rain": {"rain_next_24h_mm": 10.9, "age_minutes": 130},
                        "met_forecast": {"summary": "Ribut petir"}},
            "cross_check": {"status": "stale", "newest": "2024-02-23 14:45 MYT"}, "conflicts_unresolved": []}


def forecast(verdict="WATCH", band="alert", label="high", rng=(6.9, 7.4), tidal=False, upstream=()):
    return {"verdict": verdict, "level_name": card.BAND.get(band), "confidence": {"label": label, "score": 0.8},
            "triggers": [{"level": verdict, "rule": "r", "reason": "at alert"}], "mode": "full",
            "controlling": [{"role": "controlling", "tide_influenced": tidal,
                             "projection_m": {"24h": {"min": rng[0], "max": rng[1]}} if rng else {}}],
            "upstream": list(upstream),
            "history": [{"event": "Nov 2024 (29 Nov)", "peak_m": 11.43}, {"event": "Dec 2014", "peak_m": 10.84}]}


def build(**kw):
    return card.build({"place": {"name": "Rantau Panjang"}}, EVIDENCE, forecast(**kw))


# -- advice ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("verdict", ["NORMAL", "WATCH", "PREPARE", "ACT", "INSUFFICIENT_DATA"])
@pytest.mark.parametrize("lang", ["en", "ms"])
def test_every_verdict_leads_with_its_advice(verdict, lang):
    c = card.build({}, EVIDENCE, forecast(verdict=verdict))
    first = card.render(c, lang).split("\n")[0]
    assert first == f"{card.T['action'][lang]}: {card.ADVICE[verdict][lang]}"


def test_insufficient_data_never_reads_like_normal():
    ev = dict(EVIDENCE, usable=False)
    text = card.render(card.build({}, ev, forecast(verdict="INSUFFICIENT_DATA", rng=None)), "en")
    assert "cannot confirm" in text and "No action needed" not in text and "NORMAL" not in text


def test_act_advice_never_sends_people_into_water():
    for lang in ("en", "ms"):
        text = card.render(build(verdict="ACT", band="danger"), lang)
        assert all(not critic.UNSAFE.search(s) or critic.NEGATION.search(s) for s in critic._sentences(text))


# -- content and order ----------------------------------------------------------------------------------------
def test_english_card_reads_in_order():
    lines = card.render(build(), "en").split("\n")
    assert lines[1] == "Rantau Panjang: WATCH - JPS level Alert"
    assert lines[2] == ("River: [JPS reading] m at 22 Oct 20:45 (Sg. Golok di Rantau Panjang (F1)); [distance] above Alert (7 m), "
                        "[distance] below Danger (9 m), [distance] below the Nov 2024 (29 Nov) peak (11.43 m).")
    assert lines[3] == "Next 24 h: 6.9-7.4 m (straight-line trend). Confidence: high."
    assert lines[4] == "Rain next 24 h: 10.9 mm (Open-Meteo)."
    assert lines[5] == "Sources: JPS 16 min ago; Open-Meteo 2 h ago; MetMalaysia forecast for today."
    assert lines[6] == "Excluded: data.gov.my flood-warning (stale, last update 2024-02-23)."


def test_malay_card_reads_in_order():
    lines = card.render(build(), "ms").split("\n")
    assert lines[0].startswith("APA PERLU DIBUAT SEKARANG: Semak semula dalam 3 jam")
    assert lines[1] == "Rantau Panjang: WATCH - paras JPS Waspada"
    assert "[distance] di atas Waspada (7 m), [distance] di bawah Bahaya (9 m)" in lines[2]
    assert lines[3] == "24 jam akan datang: 6.9-7.4 m (unjuran garis lurus). Keyakinan: tinggi."
    assert lines[-1].startswith("Diketepikan: data.gov.my flood-warning (lapuk")


def test_tidal_gauge_says_trend_not_projected():
    text = card.render(build(rng=None, tidal=True), "en")
    assert "Trend not projected (tide-influenced gauge). Confidence: high." in text


def test_upstream_rise_with_travel_time():
    up = {"gauge": "Kuala Krai", "band": "alert", "rising": True, "arrives_in_h": {"min": 9, "max": 17}}
    assert "Upstream: Kuala Krai (Alert, rising), may reach here in 9-17 h." in card.render(build(upstream=[up]), "en")
    assert "Hulu: Kuala Krai (Waspada, sedang naik), mungkin sampai ke sini dalam 9-17 jam." in \
        card.render(build(upstream=[up]), "ms")


def test_active_met_warning_is_shown():
    ev = dict(EVIDENCE, met_warnings={"active": [{"heading": "CONTINUOUS RAIN WARNING"}]})
    c = card.build({}, ev, forecast())
    assert "MetMalaysia warning: CONTINUOUS RAIN WARNING." in card.render(c, "en")


@pytest.mark.parametrize("verdict", ["NORMAL", "WATCH", "PREPARE", "ACT"])
@pytest.mark.parametrize("lang", ["en", "ms"])
def test_card_fits_a_whatsapp_message(verdict, lang):
    assert len(card.render(build(verdict=verdict), lang)) <= card.MAX_CARD_CHARS


# -- explanation check (Husaini: every number must be in the card) --------------------------------------------
@pytest.mark.parametrize("text, problem", [
    ("The river passed the Alert level of 7 m a short while ago.", None),
    ("Paras sungai [JPS reading] m, sedikit di atas paras Waspada 7.0 m.", None),          # 7.0 = 7 by value
    ("The river may reach 8.5 m tonight.", "not in the card"),
    ("This is a PREPARE situation.", "not the card's"),
    ("", "empty"),
    ("x" * 401, "too long"),
])
def test_explanation_check(text, problem):
    got = card.explanation_problem(text, build())
    assert (got is None) if problem is None else (problem in got)


# -- the code-written card passes the Critic's code checks by construction -------------------------------------
@pytest.mark.parametrize("verdict, band", [("NORMAL", "normal"), ("WATCH", "alert"), ("ACT", "danger")])
@pytest.mark.parametrize("lang", ["en", "ms"])
def test_card_passes_critic_code_checks(verdict, band, lang):
    fc = forecast(verdict=verdict, band=band)
    c = card.build({}, EVIDENCE, fc)
    facts = coordinator.facts_for_model(EVIDENCE, fc)
    assert critic.code_checks(card.render(c, lang), facts, EVIDENCE, c, None) == []


def test_explanation_with_new_number_fails_critic_code_check():
    c = build()
    found = critic.code_checks(card.render(c, "en", "It will hit 8.8 m."), coordinator.facts_for_model(
        EVIDENCE, forecast()), EVIDENCE, c, "It will hit 8.8 m.")
    assert [f["type"] for f in found] == ["unsupported"]


# -- place replies --------------------------------------------------------------------------------------------
def res(status, known=None, nearest=None, suggestions=()):
    return SimpleNamespace(status=status, known=known, nearest=nearest, suggestions=list(suggestions),
                           covered=["Kota Bharu", "Pasir Mas", "Rantau Panjang", "Tumpat"], query="x")


@pytest.mark.parametrize("r, lang, expected", [
    (res("not_covered", "Bachok", {"name": "Kota Bharu", "km": 20}), "en",
     "Bachok is in Kelantan but not covered by VEDA yet. Nearest covered place: Kota Bharu (about 20 km away)."),
    (res("not_covered", "Bachok", {"name": "Kota Bharu", "km": 20}), "ms",
     "Bachok di Kelantan tetapi belum diliputi VEDA. Tempat terdekat yang diliputi: Kota Bharu (kira-kira 20 km)."),
    (res("not_covered", "Machang"), "ms", "Machang di Kelantan tetapi belum diliputi VEDA. Tempat yang diliputi:"),
    (res("not_covered"), "en", "That place is not covered by VEDA yet."),
    (res("not_covered"), "ms", "Tempat itu belum diliputi VEDA."),
    (res("not_covered", "Kelantan"), "ms", "Sila nyatakan bandar atau daerah di Kelantan."),
    (res("did_you_mean", suggestions=["Rantau Panjang"]), "ms", "Adakah maksud anda Rantau Panjang?"),
])
def test_place_replies_in_the_users_language(r, lang, expected):
    assert card.place_reply(r, lang).startswith(expected)


def test_numbers_are_compared_by_value():
    assert {7.0, [JPS reading], 9.0} <= card.numbers(build())
    assert not re.search(r"\d", card.place_reply(res("not_covered"), "en"))
