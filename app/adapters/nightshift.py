"""Nightshift adapter: the only path from VEDA to a model (lanes `fast` / `deep`, retries, JSON mode, trace).

Every call goes to METERLESS_BASE_URL (OpenAI-compatible) and writes one trace line with the model that
actually answered and whether Nightshift honoured the requested lane.

    from app.adapters import nightshift
    r = nightshift.chat("fast", [{"role": "user", "content": "..."}], agent="Coordinator", json_mode=True)
    r.data, r.served_model, r.pinned

Check from the command line:  python -m app.adapters.nightshift "Is Pasir Mas at risk?"
"""
import json
import os
import sys
import time
from dataclasses import dataclass, field

import requests

from app import config, trace

LANES = ("fast", "deep")
EXPECTED_MODEL = {  # B-66: the Nemotron model each lane must be answered by (override: METERLESS_EXPECT_<LANE>)
    "fast": "nvidia/nemotron-3.5-lightning-30b-a3b",
    "deep": "nvidia/nemotron-3.5-super-vl-120b-a12b",
}
RETRY_STATUSES = {429, 500, 502, 503, 504}
BACKOFF_S = (2, 4, 8)          # waits before retry 1, 2, 3
MIN_MAX_TOKENS = 200           # B-64: tiny budgets + reasoning -> empty response
DEFAULT_MAX_TOKENS = 2000      # B-03 probe: Lightning spends ~1.1-1.4k hidden tokens even with thinking off
TIMEOUT_S = 180
_sleep = time.sleep            # patched in tests


class NightshiftError(Exception):
    """A model call failed after retries, or the adapter is misconfigured."""


@dataclass
class LLMResult:
    """What one chat() call returns."""
    text: str
    lane: str
    served_model: str | None
    routed_mode: str | None
    mode_coerced: bool | None
    pinned: bool               # lane honoured AND the expected model answered
    expected_model: str
    attempts: int
    latency_ms: int
    usage: dict = field(default_factory=dict)
    tool_calls: list = field(default_factory=list)
    data: dict | None = None   # parsed JSON when json_mode=True


def lane_model(lane):
    """Model name sent to Nightshift for a lane (from env). Refuses unknown lanes and anything `auto`."""
    if lane not in LANES:
        raise ValueError(f"unknown lane {lane!r}; use one of {LANES}")
    model = os.getenv(f"METERLESS_MODEL_{lane.upper()}", f"meterless/{lane}").strip()  # Setup Guide 4.6: pin a meterless/* route
    if "auto" in model.lower():
        raise ValueError(f"METERLESS_MODEL_{lane.upper()}={model!r} is not allowed - never route through auto")
    return model


def expected_model(lane):
    """The model that must answer a lane (env METERLESS_EXPECT_<LANE>, else EXPECTED_MODEL)."""
    return os.getenv(f"METERLESS_EXPECT_{lane.upper()}", "").strip() or EXPECTED_MODEL[lane]


def lane_app(lane):
    """`meterless-app` header for a lane. Nightshift pins routing mode per app, so each lane has its own app."""
    return os.getenv(f"METERLESS_APP_{lane.upper()}", f"veda-{lane}").strip() or f"veda-{lane}"


def _config():
    base = os.getenv("METERLESS_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("METERLESS_RUNTIME_TOKEN", "").strip()
    if not base:
        raise NightshiftError("METERLESS_BASE_URL is not set")
    if not token or token == "rt-local":
        raise NightshiftError("METERLESS_RUNTIME_TOKEN is not set (copy it from Nightshift Console)")
    return base, token


def _receipt(payload):
    """Pull routing facts out of Nightshift's `meterless` receipt."""
    meta = payload.get("meterless") or {}
    policy = (meta.get("receipt") or {}).get("app_policy") or {}
    return {
        "served_model": payload.get("model"),
        "routed_mode": policy.get("routed_mode") or meta.get("mode"),
        "mode_coerced": policy.get("mode_coerced"),
        "receipt_id": meta.get("decision_id") or meta.get("request_id"),
    }


def _parse_json(text):
    """Parse a JSON object from model text (tolerates ```json fences). Raises ValueError."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").removeprefix("json").strip()
    data = json.loads(t)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


def _last_user(messages):
    return next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")


def _post(base, token, body, app, timeout=TIMEOUT_S):
    headers = {"Authorization": f"Bearer {token}", "meterless-app": app, "meterless-scope": "user",
               "Content-Type": "application/json"}
    return requests.post(f"{base}/chat/completions", headers=headers, json=body, timeout=timeout)


def _has_choices(payload):
    ch = payload.get("choices")
    return isinstance(ch, list) and bool(ch) and isinstance(ch[0], dict)


def _error_message(payload, r):
    """Nightshift's error text, whatever shape the body has (dict / str / missing)."""
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("message", r.text))[:200]
    return str(err or r.text or f"HTTP {r.status_code}")[:200]


def _call(lane, body, agent, prompt_summary, deadline=None):
    """POST with retry/backoff. Returns (payload, attempts). Raises NightshiftError when out of retries or time.
    deadline: time.monotonic() value after which no new attempt starts (the run's time budget)."""
    base, token = _config()
    attempt, grew = 0, False
    while True:
        attempt += 1
        t0 = time.perf_counter()
        problem = fatal = None
        left = deadline - time.monotonic() if deadline else TIMEOUT_S
        try:
            if left <= 1:
                raise requests.Timeout("run time budget used up")
            r = _post(base, token, body, lane_app(lane), timeout=min(TIMEOUT_S, left))
            payload = r.json() if r.content else {}
            if not isinstance(payload, dict):          # list / str body: never crash on .get
                payload = {"error": str(payload)[:200]}
            if r.ok and _has_choices(payload):
                return payload, attempt
            message = _error_message(payload, r)
            if r.status_code == 401:
                fatal = "Nightshift refused the token (401) - check METERLESS_RUNTIME_TOKEN"
            if "empty_response" in message and not grew:
                grew = True  # model spent its budget on hidden reasoning: retry once with double budget
                body = {**body, "max_tokens": body["max_tokens"] * 2}
                problem = f"empty response -> retry with max_tokens={body['max_tokens']}"
            elif r.status_code in RETRY_STATUSES or r.ok:   # 200 without choices = garbage, retry
                problem = f"HTTP {r.status_code}: {message}"
            else:
                fatal = f"Nightshift error HTTP {r.status_code}: {message}"
        except (requests.ConnectionError, requests.Timeout) as e:
            problem = f"network error: {type(e).__name__}"
        except ValueError:
            problem = "response was not JSON"
        ms = int((time.perf_counter() - t0) * 1000)
        wait = BACKOFF_S[min(attempt, len(BACKOFF_S)) - 1]
        if deadline is not None and not fatal and time.monotonic() + wait >= deadline:
            fatal = f"run time budget used up after {attempt} attempt(s): {problem}"
        if fatal:
            trace.step(agent, "nightshift.chat", input_summary=prompt_summary, output_summary=fatal,
                       status="failed", source=f"nightshift:{lane}", retry_count=attempt - 1, duration_ms=ms,
                       decision="Not retryable - caller must fall back")
            raise NightshiftError(fatal)
        if attempt > len(BACKOFF_S):
            trace.step(agent, "nightshift.chat", input_summary=prompt_summary, output_summary=problem,
                       status="failed", source=f"nightshift:{lane}", retry_count=attempt - 1, duration_ms=ms,
                       decision="Out of retries - caller must fall back")
            raise NightshiftError(f"Nightshift failed after {attempt} attempts: {problem}")
        trace.step(agent, "nightshift.chat", input_summary=prompt_summary, output_summary=problem,
                   status="retrying", source=f"nightshift:{lane}", retry_count=attempt, duration_ms=ms,
                   decision=f"Retrying in {wait}s")
        _sleep(wait)


def chat(lane, messages, agent, json_mode=False, thinking=False, tools=None, max_tokens=DEFAULT_MAX_TOKENS,
         temperature=0.2, target_agent=None, budget_s=None):
    """Send one chat request through Nightshift on lane `fast` or `deep`. Returns LLMResult, raises NightshiftError.
    budget_s: optional cap on total seconds incl. retries and the JSON repair (pass the run's remaining time)."""
    deadline = time.monotonic() + budget_s if budget_s else None
    if config.sample_mode():
        raise NightshiftError("SAMPLE_MODE: offline SampleGenerator arrives in B-18; no live model calls allowed")
    model = lane_model(lane)
    body = {"model": model, "messages": list(messages), "temperature": temperature,
            "max_tokens": max(int(max_tokens), MIN_MAX_TOKENS),
            "chat_template_kwargs": {"enable_thinking": bool(thinking)}}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if tools:
        body["tools"], body["tool_choice"] = tools, "auto"
    prompt_summary = trace.summarize(_last_user(messages), 120)

    t0 = time.perf_counter()
    payload, attempts = _call(lane, body, agent, prompt_summary, deadline)
    msg = payload["choices"][0].get("message") or {}
    text = msg.get("content") or ""
    data = None
    if json_mode:
        try:
            data = _parse_json(text)
        except ValueError as e:  # one repair round
            trace.step(agent, "nightshift.chat", input_summary=prompt_summary, output_summary=trace.summarize(text, 120),
                       status="retrying", source=f"nightshift:{lane}", retry_count=attempts,
                       decision=f"Invalid JSON ({e}) -> asking the model to repair it once")
            repair = {**body, "messages": body["messages"] + [
                {"role": "assistant", "content": text},
                {"role": "user", "content": "That was not valid JSON. Reply with only the JSON object, nothing else."}]}
            payload, more = _call(lane, repair, agent, prompt_summary, deadline)
            attempts += more
            text = (payload["choices"][0].get("message") or {}).get("content") or ""
            try:
                data = _parse_json(text)
            except ValueError as e2:
                trace.step(agent, "nightshift.chat", input_summary=prompt_summary, status="failed",
                           output_summary=trace.summarize(text, 120), source=f"nightshift:{lane}",
                           retry_count=attempts, decision="Still not valid JSON after repair")
                raise NightshiftError(f"model did not return valid JSON after one repair: {e2}") from e2
            msg = payload["choices"][0].get("message") or {}

    ms = int((time.perf_counter() - t0) * 1000)
    rc = _receipt(payload)
    want = expected_model(lane)
    lane_ok = rc["mode_coerced"] is not True and rc["routed_mode"] in (lane, model)
    model_ok = rc["served_model"] == want
    pinned = lane_ok and model_ok
    if pinned:
        decision = f"Answered by {rc['served_model']} on lane '{lane}'"
    elif not lane_ok:
        decision = (f"Lane NOT pinned: asked '{lane}', Nightshift routed '{rc['routed_mode']}'"
                    f"{' (app rule coerced it)' if rc['mode_coerced'] else ''}; answered by {rc['served_model']}")
    else:
        decision = (f"WRONG MODEL on lane '{lane}': expected {want}, answered by {rc['served_model']} "
                    f"- check the app's lane allowlist in Nightshift")
    result = LLMResult(text=text, lane=lane, served_model=rc["served_model"], routed_mode=rc["routed_mode"],
                       mode_coerced=rc["mode_coerced"], pinned=pinned, expected_model=want, attempts=attempts,
                       latency_ms=ms,
                       usage=payload.get("usage") or {}, tool_calls=msg.get("tool_calls") or [], data=data)
    trace.step(agent, "nightshift.chat", input_summary=prompt_summary,
               output_summary=(f"{len(result.tool_calls)} tool call(s)" if result.tool_calls
                               else trace.summarize(text, 120)),
               status="success", target_agent=target_agent, source=f"nightshift:{lane}",
               retry_count=attempts - 1, duration_ms=ms, decision=decision,
               details={"requested_model": model, "app": lane_app(lane), **rc, "expected_model": want, "pinned": pinned, "usage": result.usage,
                        "attempts": attempts, "json_mode": json_mode, "thinking": bool(thinking)})
    return result


def get_llm(lane, agent):
    """Meterless engine-style injected generator for a lane: generator(prompt, ...) -> {"text": ...}."""
    lane_model(lane)  # fail fast on a bad lane

    def generator(prompt, attachments=None, system_prompt=None, on_stream=None, abort_signal=None):
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + \
                   [{"role": "user", "content": prompt}]
        text = chat(lane, messages, agent=agent).text  # text-only: attachments are not sent
        if on_stream:
            on_stream(text)
        return {"text": text}

    return generator


PLAN_SYSTEM = ("You are the Coordinator of VEDA, a flood-risk assistant for Kelantan, Malaysia. "
               "Write a short plan as one JSON object with keys: intent (risk_check | evacuation | cut_off | other), "
               "place (string), user_type (resident | family_far_away | school | unknown), "
               "sources (list of: jps_river_levels, open_meteo_rain, mygov_forecast, mygov_warning), "
               "effort (quick | full), reason (one sentence). Output only the JSON object.")


def main(argv):
    """CLI check: send a Coordinator-style planning prompt to the fast lane and print the plan."""
    from dotenv import load_dotenv
    load_dotenv(trace.ROOT / ".env")
    question = " ".join(argv[1:]) or "Is Pasir Mas at risk of flooding tomorrow?"
    trace.start_run(question)
    try:
        r = chat("fast", [{"role": "system", "content": PLAN_SYSTEM}, {"role": "user", "content": question}],
                 agent="Coordinator", json_mode=True, target_agent="Data & Reconciler")
    except NightshiftError as e:
        trace.end_run("failed", str(e))
        print(f"FAILED: {trace.redact(str(e))}")
        return 1
    print(json.dumps(r.data, indent=2, ensure_ascii=False))
    print(f"served_model={r.served_model} pinned={r.pinned} attempts={r.attempts} latency={r.latency_ms} ms")
    print("trace:", trace.end_run())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
