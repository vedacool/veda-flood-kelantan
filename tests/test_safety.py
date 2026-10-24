"""B-58 tests: the safety gate on its own (every rule, both languages) + the safety eval set via scripts/run_evals.py.

The eval scenarios also hit earlier layers (Critic code checks, explanation check); these unit tests prove the gate
itself catches each problem even if everything before it let it through."""
import importlib.util

import pytest

from app import card, safety, trace
from app.agents.coordinator import SAFETY

EVIDENCE = {"place": {"name": "Rantau Panjang"}, "usable": True,
            "context": {"gauges": [{"station": "s", "name": "Rantau Panjang", "role": "controlling", "level_m": 7.1,
                                    "band": "alert", "observed_at": "2026-10-22T12:00:00Z", "age_minutes": 10,
                                    "thresholds": {"alert_m": 7.0, "danger_m": 9.0}}], "sentinels": []}}
FC = {"verdict": "WATCH", "level_name": card.BAND["alert"], "confidence": {"label": "high"}, "triggers": [],
      "controlling": [{"role": "controlling", "projection_m": {"24h": {"min": 7.4, "max": 7.9}}}], "history": []}


@pytest.fixture(autouse=True)
def run(tmp_path):
    trace.start_run("safety test", log_dir=tmp_path, quiet=True)
    yield
    trace.end_run()


def answer(c, lang="en", explanation=None, **kw):
    return {"text": card.render(c, lang, explanation), "language": lang, "drafted_by": "llm",
            "explanation": explanation, "card": c, "safety_line": SAFETY[lang], **kw}


def test_clean_answer_passes_untouched():
    c = card.build({}, EVIDENCE, FC)
    a = answer(c, explanation="The river is just above Alert.")
    out = safety.gate(a, c, EVIDENCE, FC)
    assert out["safety"] == [] and out["text"] == a["text"]


@pytest.mark.parametrize("lang, bad", [("en", "You can still drive through the water on the main road."),
                                       ("ms", "Boleh redah air di jalan kampung."),
                                       ("en", "Wade across carefully if you must.")])
def test_unsafe_explanation_is_removed(lang, bad):
    c = card.build({}, EVIDENCE, FC)
    out = safety.gate(answer(c, lang, bad), c, EVIDENCE, FC)
    assert bad not in out["text"] and out["explanation"] is None and "unsafe advice removed" in out["safety"][0]
    assert out["text"] == card.render(c, lang)


def test_normal_without_fresh_data_becomes_insufficient():
    c = card.build({}, EVIDENCE, {**FC, "verdict": "NORMAL"})
    out = safety.gate(answer(c), c, {**EVIDENCE, "usable": False}, FC)
    assert "Can't confirm right now" in out["text"] and "NORMAL" not in out["text"]
    assert card.ADVICE["INSUFFICIENT_DATA"]["en"] in out["text"]


def test_flat_range_is_dropped():
    fc = {**FC, "controlling": [{"role": "controlling", "projection_m": {"24h": {"min": 7.5, "max": 7.5}}}]}
    c = card.build({}, EVIDENCE, fc)
    assert "7.5-7.5" in card.render(c, "en")
    out = safety.gate(answer(c), c, EVIDENCE, fc)
    assert "7.5-7.5" not in out["text"] and "no width" in out["safety"][0]


@pytest.mark.parametrize("lang", ["en", "ms"])
def test_missing_or_wrong_language_disclaimer_is_set(lang):
    c = card.build({}, EVIDENCE, FC)
    out = safety.gate(answer(c, lang, safety_line=None), c, EVIDENCE, FC)
    assert out["safety_line"] == SAFETY[lang] and "999" in out["safety_line"]


def test_replay_title_is_added_when_missing():
    c = card.build({}, {**EVIDENCE, "replay": {"scenario": "nov2024"}}, FC)
    a = answer(c)
    a["text"] = a["text"].split("\n", 1)[1]                    # something stripped the title
    out = safety.gate(a, c, EVIDENCE, FC)
    assert out["text"].startswith("REPLAY · Nov 2024\n")


def test_place_reply_without_card_gets_its_disclaimer():
    out = safety.gate({"text": "Tempat itu belum diliputi VEDA.", "language": "ms", "drafted_by": "code"})
    assert out["safety_line"] == SAFETY["ms"]


def test_every_advice_line_passes_the_gate():
    for verdict in card.ADVICE:
        for lang in ("en", "ms"):
            assert safety._unsafe(card.ADVICE[verdict][lang]) == [], (verdict, lang)


def test_safety_eval_set_passes(capsys, tmp_path):
    spec = importlib.util.spec_from_file_location("run_evals", trace.ROOT / "scripts" / "run_evals.py")
    run_evals = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run_evals)
    trace.end_run()                                           # the evals open their own runs
    try:
        assert run_evals.main(["safety"]) == 0, capsys.readouterr().out
    finally:
        trace.start_run("safety test (reopen)", quiet=True, log_dir=tmp_path)
