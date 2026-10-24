"""B-86 (organiser answer, 23 Oct): logs show which model handled each successful AI request AND plainly mark every
request where the fallback was used - one `ai.fallback` line per fallback, repeated on run_end; none on a run where
the AI steps worked; none on the quick path (code by design, not a fallback)."""
import json
from types import SimpleNamespace

import pytest

from app import gazetteer, loop, progress, router
from app.adapters import nightshift
from app.agents import critic


def _lines(r):
    return [json.loads(x) for x in open(r["trace"], encoding="utf-8")]


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    monkeypatch.setattr(router, "data_triggers", lambda *a, **k: ["test: forced full"])
    gazetteer.clear_cache()
    yield tmp_path
    gazetteer.clear_cache()


def llm_with(draft=True, review=True):
    def llm(lane, messages, agent, **kw):
        if messages[0]["content"] in (critic.CRITIC_SYSTEM, critic.SMALL_SYSTEM):
            if not review:
                raise nightshift.NightshiftError("Nightshift failed after 1 attempts: HTTP 200: nvidia_500")
            return SimpleNamespace(data={"ok": True, "reason": "matches"}, text="")
        if not draft:
            raise nightshift.NightshiftError("Nightshift failed after 1 attempts: HTTP 200: ttfb_timeout:x")
        return SimpleNamespace(data={"explanation": "VEDA checked the river readings for this place."}, text="")
    return llm


def test_a_run_where_both_ai_steps_worked_has_no_fallback_line(offline):
    r = loop.run("Is Tumpat safe tomorrow?", llm=llm_with(), log_dir=offline, quiet=True)
    steps = _lines(r)
    assert not [s for s in steps if s["action"] == "ai.fallback"]
    assert steps[-1]["decision"] == "no AI fallback in this run" and steps[-1]["details"]["ai_fallbacks"] == []


def test_draft_failure_is_marked_and_listed_on_run_end(offline):
    r = loop.run("Is Tumpat safe tomorrow?", llm=llm_with(draft=False), log_dir=offline, quiet=True)
    steps = _lines(r)
    marks = [s for s in steps if s["action"] == "ai.fallback"]
    assert [m["agent_name"] for m in marks] == ["Coordinator"]
    assert marks[0]["status"] == "fallback" and marks[0]["output_summary"].startswith(
        "fallback: code-only card, explanation dropped (Nightshift unavailable") and "ttfb_timeout" in \
        marks[0]["output_summary"]
    assert steps[-1]["decision"] == "AI fallback used: Coordinator: code-only card, explanation dropped"
    assert progress.describe(marks[0]).startswith("  ! Coordinator: fallback: code-only card")


def test_review_failure_is_marked_and_the_explanation_drop_too(offline):
    r = loop.run("Is Tumpat safe tomorrow?", llm=llm_with(review=False), log_dir=offline, quiet=True)
    marks = [s for s in _lines(r) if s["action"] == "ai.fallback"]
    assert [(m["agent_name"], m["details"]["what"]) for m in marks] == [
        ("Critic", "critic code + Zetaris only, AI review unavailable"),
        ("System", "explanation dropped, not reviewed by AI")]
    assert "nvidia_500" in marks[0]["output_summary"] and not r["answer"].get("explanation")


def test_quick_path_is_code_by_design_not_a_fallback(offline, monkeypatch):
    monkeypatch.setattr(router, "data_triggers", lambda *a, **k: [])
    r = loop.run("Tumpat ok?", llm=llm_with(), log_dir=offline, quiet=True)
    assert r["plan"]["effort"] == "quick"
    assert not [s for s in _lines(r) if s["action"] == "ai.fallback"]


def test_a_by_name_answer_reads_as_pinned_not_as_a_lane_problem(monkeypatch, tmp_path):
    """B-85 asks for Super VL by name: Nightshift reports no routing mode; the served model matching is enough."""
    from app import trace
    monkeypatch.delenv("METERLESS_MODEL_DEEP", raising=False)
    monkeypatch.setenv("SAMPLE_MODE", "false")
    monkeypatch.setenv("METERLESS_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("METERLESS_RUNTIME_TOKEN", "test-token")
    payload = {"model": "nvidia/nemotron-3.5-super-vl-120b-a12b", "choices": [{"message": {"content": "{\"ok\": true}"}}],
               "meterless": {"decision_id": "req_x"}}
    monkeypatch.setattr(nightshift, "_call", lambda *a, **k: (payload, 1))
    trace.start_run("t", log_dir=tmp_path, quiet=True)
    try:
        r = nightshift.chat("deep", [{"role": "user", "content": "x"}], agent="Critic", json_mode=True)
    finally:
        path = trace.end_run()
    assert r.pinned and r.served_model == "nvidia/nemotron-3.5-super-vl-120b-a12b"
    line = next(json.loads(x) for x in open(path, encoding="utf-8") if '"nightshift.chat"' in x)
    assert line["decision"] == "Answered by nvidia/nemotron-3.5-super-vl-120b-a12b (requested by name, lane 'deep')"
