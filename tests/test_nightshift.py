"""Tests for app/adapters/nightshift.py (B-03). Offline: HTTP is faked with monkeypatch.

The one live test runs only with VEDA_LIVE=1 (real Nightshift, real .env).
"""
import json
import os

import pytest

from app import trace
from app.adapters import nightshift

FAKE_TOKEN = "rt" + "-test-" + "0123456789abcdef"  # assembled so the file holds no secret-shaped literal


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload
        self.ok = 200 <= status < 300
        self.content = json.dumps(payload).encode()
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def ok_payload(text="hello", model="nvidia/nemotron-3.5-lightning-30b-a3b", routed="fast", coerced=False,
               tool_calls=None):
    return {"model": model,
            "choices": [{"message": {"content": text, "tool_calls": tool_calls}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "meterless": {"mode": routed, "decision_id": "req_x",
                          "receipt": {"app_policy": {"routed_mode": routed, "mode_coerced": coerced}}}}


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """Queue of responses; records every request body + headers."""
    monkeypatch.setenv("METERLESS_BASE_URL", "http://127.0.0.1:8088/v1")
    monkeypatch.setenv("METERLESS_RUNTIME_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("SAMPLE_MODE", "false")
    monkeypatch.delenv("METERLESS_MODEL_FAST", raising=False)
    monkeypatch.delenv("METERLESS_MODEL_DEEP", raising=False)
    monkeypatch.delenv("METERLESS_APP_FAST", raising=False)
    monkeypatch.delenv("METERLESS_APP_DEEP", raising=False)
    monkeypatch.delenv("METERLESS_EXPECT_FAST", raising=False)
    monkeypatch.delenv("METERLESS_EXPECT_DEEP", raising=False)
    monkeypatch.setattr(nightshift, "_sleep", lambda s: None)
    state = {"queue": [], "calls": []}

    def post(url, headers=None, json=None, timeout=None):
        state["calls"].append({"url": url, "headers": headers, "body": json})
        item = state["queue"].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(nightshift.requests, "post", post)
    run = trace.start_run("test", log_dir=tmp_path, quiet=True)
    state["run"] = run
    yield state
    if trace.current_run() is not None:
        trace.end_run()


def trace_lines(state):
    return [json.loads(x) for x in state["run"].path.read_text(encoding="utf-8").splitlines()]


def test_happy_path_logs_served_model_and_pinned(fake):
    fake["queue"].append(FakeResponse(200, ok_payload()))
    r = nightshift.chat("fast", [{"role": "user", "content": "Say OK"}], agent="Coordinator")
    assert r.text == "hello" and r.pinned and r.attempts == 1
    call = fake["calls"][0]
    assert call["body"]["model"] == "meterless/fast" and call["body"]["max_tokens"] == nightshift.DEFAULT_MAX_TOKENS
    assert call["headers"]["meterless-app"] == "veda-fast"
    line = trace_lines(fake)[-1]
    assert line["agent_name"] == "Coordinator" and line["source"] == "nightshift:fast"
    assert line["details"]["served_model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert line["details"]["pinned"] is True


def test_each_lane_uses_its_own_app(fake, monkeypatch):
    monkeypatch.setenv("METERLESS_APP_DEEP", "veda-deep-custom")
    fake["queue"] += [FakeResponse(200, ok_payload()), FakeResponse(200, ok_payload(routed="deep"))]
    nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator")
    nightshift.chat("deep", [{"role": "user", "content": "x"}], agent="Critic")
    assert [c["headers"]["meterless-app"] for c in fake["calls"]] == ["veda-fast", "veda-deep-custom"]
    assert trace_lines(fake)[-1]["details"]["app"] == "veda-deep-custom"


SUPER_VL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"


def test_deep_pinned_only_with_super_vl(fake):
    fake["queue"].append(FakeResponse(200, ok_payload(model=SUPER_VL, routed="deep")))
    r = nightshift.chat("deep", [{"role": "user", "content": "x"}], agent="Critic")
    assert r.pinned and r.expected_model == SUPER_VL
    assert trace_lines(fake)[-1]["details"]["expected_model"] == SUPER_VL


def test_wrong_model_on_right_lane_is_flagged(fake):
    # the B-66 failure: Nightshift honoured lane 'fast' but the race was won by Super VL
    fake["queue"].append(FakeResponse(200, ok_payload(model=SUPER_VL, routed="fast")))
    r = nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator")
    assert r.pinned is False and r.served_model == SUPER_VL
    line = trace_lines(fake)[-1]
    assert line["decision"].startswith("WRONG MODEL on lane 'fast'") and LIGHTNING in line["decision"]
    assert line["details"]["pinned"] is False


def test_expected_model_override_from_env(fake, monkeypatch):
    monkeypatch.setenv("METERLESS_EXPECT_FAST", "nvidia/some-other-nemotron")
    fake["queue"].append(FakeResponse(200, ok_payload(model="nvidia/some-other-nemotron", routed="fast")))
    assert nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator").pinned


def test_token_never_in_trace(fake):
    fake["queue"].append(FakeResponse(200, ok_payload()))
    nightshift.chat("fast", [{"role": "user", "content": "hi"}], agent="Coordinator")
    assert FAKE_TOKEN not in fake["run"].path.read_text(encoding="utf-8")


def test_not_pinned_is_reported(fake):
    fake["queue"].append(FakeResponse(200, ok_payload(routed="auto", coerced=True)))
    r = nightshift.chat("deep", [{"role": "user", "content": "check"}], agent="Critic")
    assert r.pinned is False
    line = trace_lines(fake)[-1]
    assert "Lane NOT pinned" in line["decision"] and "app rule" in line["decision"]


@pytest.mark.parametrize("bad", ["auto", "meterless/auto", "medium"])
def test_bad_lanes_refused(fake, bad):
    with pytest.raises(ValueError):
        nightshift.chat(bad, [{"role": "user", "content": "x"}], agent="Coordinator")


def test_auto_model_in_env_refused(fake, monkeypatch):
    monkeypatch.setenv("METERLESS_MODEL_FAST", "meterless/auto")
    with pytest.raises(ValueError):
        nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator")


def test_retry_on_429_then_success(fake):
    fake["queue"] += [FakeResponse(429, {"error": {"message": "rate limited"}}), FakeResponse(200, ok_payload())]
    r = nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator")
    assert r.attempts == 2
    statuses = [x["status"] for x in trace_lines(fake) if x["action"] == "nightshift.chat"]
    assert statuses == ["retrying", "success"]


def test_network_error_retried_until_failure(fake):
    fake["queue"] += [nightshift.requests.ConnectionError("down")] * 4
    with pytest.raises(nightshift.NightshiftError):
        nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator")
    statuses = [x["status"] for x in trace_lines(fake) if x["action"] == "nightshift.chat"]
    assert statuses == ["retrying", "retrying", "retrying", "failed"]


def test_string_error_body_is_retried_not_crashed(fake):
    # audit P2: {"error": "rate limited"} used to raise AttributeError (no trace, wrong exception type)
    fake["queue"] += [FakeResponse(429, {"error": "rate limited"}), FakeResponse(200, ok_payload())]
    r = nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator")
    assert r.attempts == 2


def test_list_body_is_handled(fake):
    fake["queue"] += [FakeResponse(200, ["not", "a", "dict"])] * 4
    with pytest.raises(nightshift.NightshiftError):
        nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator")
    assert trace_lines(fake)[-1]["status"] == "failed"


def test_budget_stops_retries(fake):
    fake["queue"] += [nightshift.requests.ConnectionError("down")] * 4
    with pytest.raises(nightshift.NightshiftError, match="budget"):
        nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator", budget_s=1.5)
    assert len(fake["calls"]) == 1


def test_401_not_retried(fake):
    fake["queue"].append(FakeResponse(401, {"error": {"message": "bad token"}}))
    with pytest.raises(nightshift.NightshiftError, match="401"):
        nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator")
    assert len(fake["calls"]) == 1
    assert trace_lines(fake)[-1]["status"] == "failed"


def test_empty_response_retried_once_with_double_budget(fake):
    empty = {"error": {"message": "/nemotron-3.5-lightning-30b-a3b_empty_response"}}
    fake["queue"] += [FakeResponse(502, empty), FakeResponse(200, ok_payload())]
    nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator", max_tokens=400)
    assert [c["body"]["max_tokens"] for c in fake["calls"]] == [400, 800]


def test_max_tokens_floor(fake):
    fake["queue"].append(FakeResponse(200, ok_payload()))
    nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator", max_tokens=5)
    assert fake["calls"][0]["body"]["max_tokens"] == nightshift.MIN_MAX_TOKENS


def test_json_mode_parses_and_sends_flags(fake):
    fake["queue"].append(FakeResponse(200, ok_payload('```json\n{"intent": "risk_check"}\n```')))
    r = nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator", json_mode=True)
    assert r.data == {"intent": "risk_check"}
    body = fake["calls"][0]["body"]
    assert body["response_format"] == {"type": "json_object"}
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


def test_json_repair_once_then_error(fake):
    fake["queue"] += [FakeResponse(200, ok_payload("not json")), FakeResponse(200, ok_payload('{"ok": true}'))]
    r = nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator", json_mode=True)
    assert r.data == {"ok": True} and r.attempts == 2
    fake["queue"] += [FakeResponse(200, ok_payload("nope")), FakeResponse(200, ok_payload("still nope"))]
    with pytest.raises(nightshift.NightshiftError, match="valid JSON"):
        nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator", json_mode=True)


def test_tool_calls_returned(fake):
    tc = [{"id": "c1", "type": "function", "function": {"name": "run_sql", "arguments": "{\"sql\": \"SELECT 1\"}"}}]
    fake["queue"].append(FakeResponse(200, ok_payload("", tool_calls=tc)))
    tools = [{"type": "function", "function": {"name": "run_sql", "parameters": {"type": "object"}}}]
    r = nightshift.chat("deep", [{"role": "user", "content": "x"}], agent="Critic", tools=tools)
    assert r.tool_calls == tc and fake["calls"][0]["body"]["tool_choice"] == "auto"
    assert trace_lines(fake)[-1]["output_summary"] == "1 tool call(s)"


def test_generator_form(fake):
    fake["queue"].append(FakeResponse(200, ok_payload("engine text")))
    seen = []
    gen = nightshift.get_llm("deep", agent="WorldModel")
    out = gen("prompt", system_prompt="sys", on_stream=seen.append)
    assert out == {"text": "engine text"} and seen == ["engine text"]
    assert fake["calls"][0]["body"]["messages"][0] == {"role": "system", "content": "sys"}


def test_sample_mode_refuses_live_calls(fake, monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    with pytest.raises(nightshift.NightshiftError, match="B-18"):
        nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator")
    assert fake["calls"] == []


def test_missing_token(fake, monkeypatch):
    monkeypatch.delenv("METERLESS_RUNTIME_TOKEN")
    with pytest.raises(nightshift.NightshiftError, match="METERLESS_RUNTIME_TOKEN"):
        nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator")


@pytest.mark.skipif(os.getenv("VEDA_LIVE") != "1", reason="live Nightshift test: set VEDA_LIVE=1")
def test_live_planner_prompt(tmp_path):
    from dotenv import load_dotenv
    load_dotenv(trace.ROOT / ".env")
    trace.start_run("live B-03 test", log_dir=tmp_path, quiet=True)
    try:
        r = nightshift.chat("fast", [{"role": "system", "content": nightshift.PLAN_SYSTEM},
                                     {"role": "user", "content": "Is Pasir Mas at risk of flooding tomorrow?"}],
                            agent="Coordinator", json_mode=True)
    finally:
        trace.end_run()
    assert {"intent", "place", "sources"} <= r.data.keys()
    assert r.served_model and "nemotron" in r.served_model


def test_one_try_only_does_not_retry(fake):
    fake["queue"] += [FakeResponse(502, {"error": {"message": "Meterless provider request failed."}})]
    with pytest.raises(nightshift.NightshiftError):
        nightshift.chat("deep", [{"role": "user", "content": "x"}], agent="Critic", max_attempts=1)
    rec = [x for x in trace_lines(fake) if x["action"] == "nightshift.chat"]
    assert len(fake["calls"]) == 1 and [x["status"] for x in rec] == ["failed"]
    assert rec[0]["decision"] == "One try only - caller falls back"


def test_one_try_only_skips_the_json_repair_round(fake):
    fake["queue"] += [FakeResponse(200, ok_payload(text="not json at all"))]
    with pytest.raises(nightshift.NightshiftError):
        nightshift.chat("fast", [{"role": "user", "content": "x"}], agent="Coordinator", json_mode=True,
                        max_attempts=1)
    assert len(fake["calls"]) == 1


def test_deep_lane_may_take_longer_than_fast(fake):
    assert nightshift.LANE_TIMEOUT_S["deep"] > nightshift.LANE_TIMEOUT_S["fast"]
