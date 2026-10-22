"""Spike 4 — Nightshift from Windows Python: models, fast/deep lanes, JSON with thinking off,
extra_body + tools passthrough, latency. Logs only short summaries — never the token or headers."""
import json
import os

from _common import log, nightshift, short

S = "s4"
FAST = os.getenv("METERLESS_MODEL_FAST", "fast")
DEEP = os.getenv("METERLESS_MODEL_DEEP", "deep")
THINK_OFF = {"chat_template_kwargs": {"enable_thinking": False}}


def chat(case, model, messages, **extra):
    body = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 400, **extra}
    ok, p, secs = nightshift("POST", "/chat/completions", S, body)
    text, served, usage, has_reasoning, tool_calls = "", None, None, False, None
    if ok and isinstance(p, dict) and p.get("choices"):
        msg = p["choices"][0].get("message", {})
        text = msg.get("content") or ""
        has_reasoning = bool(msg.get("reasoning_content") or msg.get("reasoning"))
        tool_calls = msg.get("tool_calls")
        served, usage = p.get("model"), p.get("usage")
    err = None if ok else short(p, 200)
    log(S, "nightshift.chat", case=case, model=model, served_model=served, ok=ok, secs=secs,
        prompt=short(messages[-1]["content"], 80), answer=short(text, 120), reasoning=has_reasoning,
        tool_calls=bool(tool_calls), usage=usage, error=err)
    print(f"\n[{case}] model={model} served={served} ok={ok} {secs}s reasoning={has_reasoning}")
    print("  answer:", short(text, 200) if ok else err)
    if tool_calls:
        print("  tool_calls:", short(json.dumps(tool_calls), 200))
    return ok, text, tool_calls


# 1. models list
ok, p, secs = nightshift("GET", "/models", S)
ids = [m.get("id") for m in p.get("data", [])] if ok and isinstance(p, dict) else []
log(S, "nightshift.models", ok=ok, secs=secs, n=len(ids), ids=ids[:30])
print("models:", ok, secs, ids)

# 2. plain hello on both lanes
hello = [{"role": "user", "content": "Reply with exactly: VEDA OK"}]
chat("fast_hello", FAST, hello)
chat("deep_hello", DEEP, hello)

# 3. JSON output, thinking off (extra_body passthrough)
json_msgs = [
    {"role": "system", "content": "You output only one JSON object, no prose, no code fences."},
    {"role": "user", "content": 'Tag this question. Keys: intent (one of risk_check, evacuation, other), place (string). '
                                'Question: "Is Pasir Mas going to flood tomorrow?"'},
]
for lane in (FAST, DEEP):
    ok, text, _ = chat(f"{lane}_json_thinking_off", lane, json_msgs, **THINK_OFF)
    try:
        parsed = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
        valid = isinstance(parsed, dict) and {"intent", "place"} <= parsed.keys()
    except (ValueError, AttributeError):
        parsed, valid = None, False
    print("  json valid:", valid, parsed)
    log(S, "json_check", lane=lane, valid=valid)

# 4. response_format json_object passthrough
chat("fast_response_format", FAST, json_msgs, response_format={"type": "json_object"}, **THINK_OFF)

# 5. tools passthrough
tools = [{"type": "function", "function": {
    "name": "run_sql", "description": "Run one read-only SQL query on Zetaris",
    "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}}}]
tool_msgs = [{"role": "user", "content": "Use the run_sql tool to count rows in table veda.places."}]
for lane in (FAST, DEEP):
    ok, _, tc = chat(f"{lane}_tools", lane, tool_msgs, tools=tools, tool_choice="auto", **THINK_OFF)
    log(S, "tools_check", lane=lane, tool_called=bool(tc))

# 6. deep lane with thinking ON (Critic setting) — latency + is reasoning returned
chat("deep_thinking_on", DEEP, [{"role": "user", "content":
     "A river gauge reading is dated Feb 2024 and today is Oct 2026. In one sentence: can it be trusted for today?"}],
     max_tokens=1500)
