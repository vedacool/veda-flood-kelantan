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
    fake_env_value = "zk_live_" + "ABCDEF123456"
    pw = "Sup3r" + "Secret!"
    spaced_pw = "Abc def" + "!123"
    monkeypatch.setenv("ZETARIS_API_KEY", fake_env_value)
    trace.step("Data", "run_sql",
               input_summary="Authorization: " + "Bearer " + bearer_value,
               output_summary=f"key {nv_key} and {fake_env_value}",
               details={"jdbc": "pass" + 'word "' + pw + '"', "spaced": "pass" + 'word "' + spaced_pw + '"',
                        "url": "postgresql://postgres:" + "hunter22" + "@localhost:5433/veda",
                        "nested": ["tok" + "en=" + "abcd1234efgh"], "json": '{"api_' + 'key": "' + fake_env_value[::-1] + '"}'})
    text = run.path.read_text(encoding="utf-8")
    for secret in (bearer_value, nv_key[:10], fake_env_value, pw, spaced_pw, "hunter22", "abcd1234efgh", fake_env_value[::-1]):
        assert secret not in text
    assert "***" in text


def test_no_over_redaction(run, monkeypatch):
    # other tools' env keys are not VEDA secrets: their values must not mask normal text (audit P3)
    monkeypatch.setenv("MONKEY_BUSINESS", "Kuala Krai")
    rec = trace.step("Data", "x", output_summary="Kuala Krai gauge; secret: none of this; password \"{PW}\"")
    assert rec["output_summary"] == "Kuala Krai gauge; secret: none of this; password \"{PW}\""


def test_end_run_with_bad_status_still_closes(tmp_path):
    trace.start_run("t", log_dir=tmp_path, quiet=True)
    path = trace.end_run("not-a-status")
    assert trace.current_run() is None
    assert read_lines(path)[-1]["status"] == "failed"


def test_bind_carries_run_into_threads(run):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(1) as ex:
        rec = ex.submit(trace.bind(trace.step), "Data", "in_thread").result()
    assert rec["run_id"] == run.run_id


def test_sentence_uses_malaysia_time():
    rec = {"timestamp": "2026-10-22T02:30:00Z", "step": 1, "agent_name": "A", "action": "x", "status": "success"}
    assert trace.sentence(rec).startswith("10:30:00 ")


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


@pytest.mark.parametrize("text, masked", [
    ("call me 012-3456789", "call me [phone]"),
    ("my number 0123456789.", "my number [phone]."),
    ("+60 12-345 6789 please", "[phone] please"),
    ("+60123456789", "[phone]"),
    ("rumah 09-748 1234", "rumah [phone]"),
    ("IC 880101-03-5678", "IC [IC]"),
    ("ic 880101035678", "ic [IC]"),
    ("IC 880101 03 5678", "IC [IC]"),                     # audit 23 Oct: spaces, dots, emails
    ("tel 012.345.6789", "tel [phone]"),
    ("email name@example.com", "email [email]"),
])
def test_phone_and_ic_numbers_are_masked(text, masked):
    assert trace.redact(text) == masked


@pytest.mark.parametrize("text", [
    "station:jps:5521044_DKKI0014", "6021065_DPMS0001", "run 20261022-185555-bcc9", "2026-10-22T10:30:00Z",
    "5.756620964560449, 102.14462513200138", "hash 645376666066d288", "level 7.18 m (2339 ms)", "26296",
])
def test_ids_times_and_coordinates_are_not_masked(text):
    assert trace.redact(text) == text


def test_question_with_a_phone_number_is_masked_in_the_file(tmp_path):
    r = trace.start_run("Rumah mak 019-8765432 di Tumpat, selamat?", log_dir=tmp_path, quiet=True)
    trace.end_run()
    text = r.path.read_text(encoding="utf-8")
    assert "8765432" not in text and "[phone]" in text and "Tumpat" in text
