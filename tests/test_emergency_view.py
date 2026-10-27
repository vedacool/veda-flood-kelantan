"""Audit 27 Oct A-P1-17: a trapped / stranded person gets the ACT advice on the answer screen (view) and in the API,
with the "safety first" label - never "Nothing to do now". The verdict still shows what the data says. Offline."""
import pytest
from starlette.testclient import TestClient

from app import card as card_mod
from app import gazetteer, main, trace, view

ACT_EN = view.action_lines("ACT", "x", "en")[0]
ACT_MS = view.action_lines("ACT", "x", "ms")[0]


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    monkeypatch.delenv("VEDA_DEMO", raising=False)
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    if trace.current_run():
        trace.end_run()
    yield
    gazetteer.clear_cache()


CASES = [  # question, scene, API language, verdict the data gives
    ("I am trapped at Tumpat, water around my house", "synthetic_calm", "en", "NORMAL"),
    ("Saya terperangkap di Tumpat, air sekeliling rumah", "synthetic_calm", "bm", "NORMAL"),
    ("I am stranded in Kota Bharu", "synthetic_rising", "en", "WATCH"),
    ("Saya terkandas di Kota Bharu", "synthetic_rising", "bm", "WATCH"),
]


@pytest.mark.parametrize("question, scene, lang, verdict", CASES)
def test_the_api_gives_the_act_advice_with_the_safety_first_label(offline, question, scene, lang, verdict):
    a = TestClient(main.app).post("/api/v1/ask", json={"question": question, "lang": lang, "scene": scene}).json()
    lg = "ms" if lang == "bm" else "en"
    assert a["emergency"] is True and a["level"] == verdict                     # the data's level is still shown
    todo = a["what_to_do"]
    assert todo[0] == card_mod.T["stranded"][lg] + "." and (ACT_EN if lg == "en" else ACT_MS) in todo
    assert not any(x.startswith(("Nothing to do", "Tiada apa perlu", "No action needed", "Check again in 3 hours",
                                 "Semak semula dalam 3 jam")) for x in todo)
    if verdict == "NORMAL":
        assert card_mod.T["stranded_normal"][lg] + "." in todo


@pytest.mark.parametrize("question, scene, lang, verdict", CASES)
def test_the_answer_screen_shows_the_same_in_both_languages(offline, question, scene, lang, verdict):
    q, replay, at = main.parse_input(question, scene, None)
    v = view.answer_view(main._run(q, replay, at))
    assert v["emergency"] and v["verdict"] == verdict and v["note"] is None
    for lg in ("en", "ms"):
        assert v["action"][lg][0] == card_mod.T["stranded"][lg] + "."
        assert v["steps"][lg] == view.steps("ACT", lg)                          # the ACT steps, both languages


def test_a_question_without_an_emergency_is_unchanged(offline):
    a = TestClient(main.app).post("/api/v1/ask", json={"question": "Is Tumpat at risk?", "scene": "synthetic_calm"}).json()
    assert a["emergency"] is False and a["what_to_do"][0] == view.action_lines("NORMAL", "Tumpat", "en")[0]
