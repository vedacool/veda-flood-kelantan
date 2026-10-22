# How VEDA works
_Module contracts (inputs → outputs → failure behaviour). Filled in as modules are built._

## Guard rails (B-65) — `scripts/codemap.py`, `scripts/precommit.py`, `tests/test_architecture.py`, `.githooks/`
- **Inputs:** the repo's Python files (`app/`, `scripts/`, `run.py`), all git-tracked files (secret scan), the local `.env` (only to know which secret values must never appear), the commit message.
- **Outputs:** `docs/CODEMAP.md` (module → purpose, public functions, callers), regenerated and staged on every commit; pass/fail for 6 guard rules; pass/fail for the backlog-ID check.
- **Failure behaviour:** any failed rule exits non-zero → git refuses the commit and prints the file:line and the rule broken. Secret values are never printed, only where they were found. Rules 1–2 skip `spikes/`; the secret scan covers every tracked file.

## Trace logger (B-02) — `app/trace.py`
- **Inputs:** `start_run(question)` once per run; then `step(agent, action, input_summary, output_summary, status, target_agent, confidence, retry_count, source, decision, duration_ms, details)` for every agent step, Zetaris call and Nightshift call; `end_run(status)`.
- **Outputs:** `logs/trace-<run_id>.jsonl`, one JSON line per step (official FAQ fields + `run_id`, `step`, `decision`, `source`, `mode`, `duration_ms`, `details`), with `run_start` / `run_end` lines; one readable sentence per step on stdout. `python -m app.trace <file>` replays a trace as sentences.
- **Failure behaviour:** unknown `status` → `ValueError`; `step()` before `start_run()` → `RuntimeError` (no silent lost steps). A failed disk write prints a warning and the run continues. Summaries are capped at 300 characters, and secrets (Bearer/nvapi/password patterns + any secret value in the environment) are replaced by `***` before writing.
- **Statuses:** `success`, `failed`, `retrying`, `fallback`, `needs_revision`, `approved`, `injected_fault`.

## Nightshift adapter (B-03) — `app/adapters/nightshift.py`
- **Inputs:** `chat(lane, messages, agent, json_mode=False, thinking=False, tools=None, max_tokens=2000)` with lane `fast` or `deep`. Env: `METERLESS_BASE_URL`, `METERLESS_RUNTIME_TOKEN`, `METERLESS_MODEL_FAST/DEEP` (default `fast`/`deep`), `METERLESS_APP_FAST/DEEP` (default `veda-fast`/`veda-deep` — the `meterless-app` header; Nightshift pins routing mode per app). `get_llm(lane, agent)` gives the Meterless engine-style generator `generator(prompt, attachments, system_prompt, on_stream, abort_signal) -> {"text"}`.
- **Outputs:** `LLMResult` (text, parsed `data` in JSON mode, tool_calls, served_model, routed_mode, mode_coerced, pinned, attempts, latency, usage). One trace line per call with the model that actually answered; if Nightshift overrode the lane the line says "Lane NOT pinned …".
- **Failure behaviour:** unknown lane or any `auto` model → `ValueError`. 429/5xx/network → retry after 2/4/8 s (each retry traced), then `NightshiftError`. `empty_response` → one retry with double `max_tokens`. 401 → no retry, `NightshiftError` naming the env var. Invalid JSON → one repair request, then `NightshiftError`. `max_tokens` never below 200. In SAMPLE_MODE it refuses live calls (`NightshiftError`) until the SampleGenerator (B-18). The caller decides the fallback. The token is never logged.
