"""Tests for app/trace.py (B-02): JSONL format, step order, redaction, statuses, run lifecycle."""
import json

import pytest

from app import trace

REQUIRED = {"timestamp", "trace_id", "run_id", "step", "agent_name", "action", "input_summary", "output_summary",
            "decision", "target_agent", "confidence", "retry_count", "status", "source", "mode", "duration_ms",
            "details"}


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def run(tmp_path):
    r = trace.start_run("Is Pasir Mas at risk?", log_dir=tmp_path, quiet=True)
    yield r
    if trace.current_run() is not None:
        trace.end_run()


def test_lines_are_json_with_required_fields_and_ordered_steps(run):
    trace.step("Coordinator", "plan", input_summary="question", output_summary="plan with 3 sources",
               target_agent="Data", confidence=0.7)
    trace.step("Critic", "review_draft", status="needs_revision", target_agent="Coordinator", retry_count=1,
               decision="Stale source -> revise", source="nightshift:deep", duration_ms=1830)
    path = trace.end_run("success")
    lines = read_lines(path)
    assert [line["action"] for line in lines] == ["run_start", "plan", "review_draft", "run_end"]
    assert [line["step"] for line in lines] == [1, 2, 3, 4]
    for line in lines:
        assert REQUIRED <= line.keys()
        assert line["run_id"] == run.run_id
    assert lines[2]["status"] == "needs_revision" and lines[2]["retry_count"] == 1
    assert path.name == f"trace-{run.run_id}.jsonl"


def test_secrets_are_redacted(run, monkeypatch):
    # fake secrets are assembled at runtime so this file never contains a secret-shaped literal (B-65 scan)
    bearer_value = "abcdefghij" * 3
    nv_key = "nv" + "api-" + "A" * 24
    monkeypatch.setenv("ZETARIS_API_KEY", "zk_live_ABCDEF123456")
    trace.step("Data", "run_sql",
               input_summary="Authorization: " + "Bearer " + bearer_value,
               output_summary=f"key {nv_key} and zk_live_ABCDEF123456",
               details={"jdbc": 'password "Sup3rSecret!"', "nested": ["token=abcd1234efgh"]})
    text = run.path.read_text(encoding="utf-8")
    for secret in (bearer_value, nv_key[:10], "zk_live_ABCDEF123456", "Sup3rSecret", "abcd1234efgh"):
        assert secret not in text
    assert "***" in text


def test_normal_words_are_not_redacted(run):
    rec = trace.step("Coordinator", "call_model", output_summary="max_tokens 400, token budget fine")
    assert rec["output_summary"] == "max_tokens 400, token budget fine"


def test_long_text_is_truncated(run):
    rec = trace.step("Data", "fetch", output_summary="x" * 5000)
    assert len(rec["output_summary"]) == trace.MAX_SUMMARY and rec["output_summary"].endswith("...")


def test_unknown_status_raises(run):
    with pytest.raises(ValueError):
        trace.step("Critic", "review", status="ok")


def test_injected_fault_status_allowed(run):
    rec = trace.step("Data", "jps_fetch", status="injected_fault", decision="VEDA_FAULTS=jps_timeout")
    assert rec["status"] == "injected_fault"


def test_step_without_run_raises():
    trace._current.set(None)
    with pytest.raises(RuntimeError):
        trace.step("Coordinator", "plan")


def test_sample_mode_is_recorded(tmp_path, monkeypatch):
    for key in ("ZETARIS_API_KEY", "METERLESS_RUNTIME_TOKEN", "VEDA_PG_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SAMPLE_MODE", "true")
    trace.start_run("offline question", log_dir=tmp_path, quiet=True)
    trace.step("Data", "run_sql", source="zetaris-replay")
    lines = read_lines(trace.end_run())
    assert lines[0]["details"]["sample_mode"] is True
    assert {line["mode"] for line in lines} == {"sample"}


def test_stdout_sentence_and_viewer(tmp_path, capsys):
    trace.start_run("q", log_dir=tmp_path)
    trace.step("Critic", "review_draft", status="needs_revision", target_agent="Coordinator",
               decision="Stale source -> revise", confidence=0.4)
    path = trace.end_run()
    out = capsys.readouterr().out
    assert "Critic -> Coordinator | review_draft | needs_revision | Stale source -> revise (conf 0.4)" in out
    assert trace.main(["app.trace", str(path)]) == 0
    assert capsys.readouterr().out.count("\n") == 3


def test_write_failure_does_not_crash(run, capsys):
    run.path = run.path.parent / "missing-dir" / "x.jsonl"
    trace.step("Data", "fetch")
    assert "could not write" in capsys.readouterr().err
