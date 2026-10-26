"""Audit 26 Oct P1-1 (Cowork): a Nightshift stream that drops mid-answer (requests' ChunkedEncodingError) must never
crash a run. The adapter turns it into a traced failure; loop.run turns any exception from an AI step into the
code-written card - the Critic's code checks and the safety gate still run. Offline: a stand-in model."""
import json
import sys
from types import SimpleNamespace

import pytest
import requests

from app import config, trace
from app.adapters import nightshift
from app.agents import critic

sys.path.insert(0, str(config.ROOT / "scripts"))
import run_evals  # noqa: E402

DROP = requests.exceptions.ChunkedEncodingError("Connection broken: IncompleteRead (eval)")


def test_the_adapter_traces_a_dropped_stream_and_fails_cleanly(monkeypatch):
    lines = []
    monkeypatch.setattr(nightshift, "_config", lambda: ("http://nightshift.test/v1", "placeholder-token"))
    monkeypatch.setattr(nightshift, "_post", lambda *a, **k: SimpleNamespace(
        headers={"content-type": "text/event-stream"}, ok=True, status_code=200, content=b""))
    monkeypatch.setattr(nightshift, "_read_stream", lambda r, stop: (_ for _ in ()).throw(DROP))
    monkeypatch.setattr(trace, "step", lambda *a, **k: lines.append((a, k)))
    monkeypatch.setattr(trace, "notify", lambda *a, **k: None)
    with pytest.raises(nightshift.NightshiftError, match="ChunkedEncodingError"):
        nightshift._call("deep", {"model": "m", "stream": True, "max_tokens": 300}, "Critic", "q", max_attempts=1)
    assert lines and lines[-1][0][1] == "nightshift.chat" and lines[-1][1]["status"] == "failed"


def stand_in(drop_at):
    """The eval stand-in, except the stream drops at one step: the draft, the Critic's review or the facts-only
    judgement (which runs when the draft failed)."""
    def llm(lane, messages, agent, **kw):
        system = messages[0]["content"]
        if system == critic.JUDGE_SYSTEM:
            if drop_at == "judge":
                raise DROP
            return SimpleNamespace(data={"ai_level": None, "reasons": [], "confidence": "low"}, text="")
        if system in (critic.CRITIC_SYSTEM, critic.SMALL_SYSTEM):
            if drop_at == "critic":
                raise DROP
            return SimpleNamespace(data={"decision": "approve", "problems": [], "ok": True, "reason": ""}, text="")
        if drop_at == "draft":
            raise DROP
        if drop_at == "judge":
            raise nightshift.NightshiftError("eval: the draft failed")       # so the facts-only judgement runs
        return SimpleNamespace(data={"explanation": "The river is being watched; follow official advice."}, text="")
    return llm


@pytest.mark.parametrize("drop_at", ["draft", "critic", "judge"])
def test_a_dropped_stream_at_any_ai_step_still_gives_the_checked_card(monkeypatch, tmp_path, drop_at):
    monkeypatch.setenv("SAMPLE_MODE", "true")                                     # offline, as the evals run
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    sc = json.loads((config.ROOT / "tests" / "evals" / "safety" / "replay_prepare.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(run_evals, "stand_in", lambda spec: stand_in(drop_at))
    ok, problems, r = run_evals.run_one(sc, tmp_path)
    assert r["status"] != "failed", problems
    assert r["forecast"]["verdict"] == sc["expect"]["verdict"]                    # the code's verdict, unchanged
    assert "999" in r["answer"]["safety_line"]                                     # the safety gate still ran
    assert r["answer"].get("drafted_by") != "model" or drop_at != "draft"
    assert ok, problems                                                            # the scenario's own checks pass


def test_final_is_always_the_verdict_the_person_sees(monkeypatch, tmp_path):
    """Audit 26 Oct (A-P1-11): if an accepted raise does not reach the verdict, the judgement says "not used" with
    final = the real verdict - the badge and Details never disagree. (Forced here by a forecast that drops it.)"""
    from app.agents import forecast_agent
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    real = forecast_agent.forecast
    monkeypatch.setattr(forecast_agent, "forecast",
                        lambda p, ev, world: real(p, {k: v for k, v in ev.items() if k != "ai_minimum"}, world))
    sc = json.loads((config.ROOT / "tests" / "evals" / "safety" /
                     "ai_judgement_no_river_met_warning_raise_en.json").read_text(encoding="utf-8"))
    ok, problems, r = run_evals.run_one(sc, tmp_path)
    assert r["forecast"]["verdict"] == "PREPARE"
    assert r["ai_judgement"]["final"] == "PREPARE" and r["ai_judgement"]["status"] == "ignored"
