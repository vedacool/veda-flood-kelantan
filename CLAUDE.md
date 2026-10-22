# CLAUDE.md — how to work on VEDA

Read `docs/BUILD_BRIEF.md` first. It is the source of truth for scope, agents, data and safety.

## Who you are working with
Husaini leads the build. He is an engineer but not a day-to-day coder: he vibe-codes and must be able to **explain how VEDA works** to judges. Optimise for clarity, not cleverness.

## Working rules
1. **Plan first, then build.** For each backlog item, write a short plain-English plan (what files, what changes, how we test) and wait for Husaini's OK before writing code.
2. **One backlog item per session.** Thin slices: build → run → read the trace → commit. Never stack untested changes.
3. **Explain every change** in 2–5 plain sentences after finishing (what, why, how to check).
4. **Module contracts:** every module has inputs → outputs → failure behaviour written in `docs/how-it-works.md`. Update it when you change a module.
5. **Secrets:** never write keys or tokens into code, logs, fixtures, docs or commit messages. Read everything from environment variables; keep `.env.example` with placeholders only. Redact auth headers in logs.
6. **Models:** call Nightshift at `METERLESS_BASE_URL` with model `fast` (Coordinator) or `deep` (Critic). Never `meterless/auto`. Never call NVIDIA directly.
7. **Data:** agents get data only through `run_sql()` (Zetaris). No direct HTTP from agents.
8. **Traces:** every agent step, Zetaris call and Nightshift call writes one JSONL line to `logs/trace-<run_id>.jsonl`.
9. **No fake behaviour:** no hard-coded outputs, no demo-only branches, never read from `output_examples/` at runtime. Fault injection only via the documented `VEDA_FAULTS` flag, logged as `injected_fault`.
10. **SAMPLE_MODE** must keep working: real agent logic, offline, empty `.env`.
11. **Safety rules** in BUILD_BRIEF §7 are non-negotiable.
12. **Commits:** small, clear messages (`feat: …`, `fix: …`, `docs: …`). Delegated Cursor-agent work is committed as `cursor-agent: …` and logged in `docs/cursor-log.md`.
13. **Delegating to Cursor CLI** (`agent -p "<task card>" --output-format json`): only small, well-specified jobs (tests, docstrings, README sections, simple parsers). One writer per file. Review the result before committing.
14. Python 3.13 in `.venv`. Keep dependencies in `requirements.txt` with pinned versions.
