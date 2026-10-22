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
