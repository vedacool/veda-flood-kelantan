"""B-93: every AI call's trace line says the requested model, served model, Nightshift receipt, duration, outcome,
purpose and whether it was a fallback - failed calls too; run_end counts the AI calls ("no AI calls" offline)."""
import json

import pytest
import requests

from app import gazetteer, loop, trace
from app.adapters import nightshift


def _lines(path, action):
    return [r for r in map(json.loads, open(path, encoding="utf-8")) if r.get("action") == action]


def test_a_timed_out_call_still_names_the_model_outcome_and_purpose(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "false")
    monkeypatch.delenv("VEDA_DEMO", raising=False)
    monkeypatch.setenv("METERLESS_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("METERLESS_RUNTIME_TOKEN", "test-token")

    def timeout(*a, **k):
        raise requests.Timeout("stub")
    monkeypatch.setattr(nightshift, "_post", timeout)
    run = trace.start_run("trace fields", log_dir=tmp_path, quiet=True)
    with pytest.raises(nightshift.NightshiftError):
        nightshift.chat("deep", [{"role": "user", "content": "facts"}], agent="Critic", max_attempts=1, budget_s=5,
                        purpose="facts-only judgement (the explanation call failed)", fallback=True)
    trace.end_run()
    call = _lines(run.path, "nightshift.chat")[-1]
    d = call["details"]
    assert call["status"] == "failed" and call["duration_ms"] is not None
    assert d["requested_model"] == nightshift.expected_model("deep") and d["served_model"] is None
    assert d["receipt_id"] is None and d["outcome"] == "timeout" and d["fallback"] is True
    assert d["purpose"].startswith("facts-only judgement")
    end = _lines(run.path, "run_end")[-1]["details"]
    assert end["ai_calls"] == 1 and "ai" not in end


def test_an_offline_run_says_no_ai_calls(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    r = loop.run("Is Kota Bharu at risk in the next two days?", quiet=True, log_dir=tmp_path, default_scene=True)
    end = _lines(r["trace"], "run_end")[-1]["details"]
    assert end["ai_calls"] == 0 and end["ai"] == "no AI calls"
