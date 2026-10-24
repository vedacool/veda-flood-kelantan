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
6. **Models:** call Nightshift at `METERLESS_BASE_URL`. Both AI steps use nvidia/nemotron-3.5-super-vl-120b-a12b by name on the deep lane (app veda-deep); the served model is checked on every call; Lightning is not used. Both steps: the Coordinator's draft and the Critic's AI review, which is a small facts-only call (`critic._small_review`). Never `meterless/auto`. Never call NVIDIA directly.
7. **Data:** agents get data only through `run_sql()` (Zetaris). No direct HTTP from agents.
8. **Traces:** every agent step, Zetaris call and Nightshift call writes one JSONL line to `logs/trace-<run_id>.jsonl`.
9. **No fake behaviour:** no hard-coded outputs, no demo-only branches, never read from `output_examples/` at runtime. No fault injection in the demo or SAMPLE_MODE: failures are tested with test-only stubs (`VEDA_FAULTS` removed 23 Oct).
10. **SAMPLE_MODE** must keep working: real agent logic, offline, empty `.env`.
11. **Safety rules** in BUILD_BRIEF §7 are non-negotiable.
12. **Commits:** small, clear messages with the backlog ID (`feat: B-xx …`, `fix: B-xx …`, `docs: B-xx …`). Delegated Cursor-agent work is committed as `cursor-agent(B-xx): …` and logged in `docs/cursor-log.md`.
13. **Delegating to Cursor CLI — daily (Husaini, 22 Oct):** every build day, delegate **2–3 small, well-defined tasks** to the Cursor CLI agent: `agent -p "<task card>" --output-format json --trust` (run in the repo root; no `--force` — the agent writes files, Claude Code runs the tests). Good jobs: tests, docstrings, README sections, simple parsers. A task card names the exact file(s) the agent may write (one writer per file — never a file Claude Code is editing), what to cover, and the constraints (offline, no secrets, no network, match local style). Claude Code then **reviews the diff line by line, runs the full test suite, fixes or rejects**, commits as `cursor-agent(B-xx): <what>` and adds one row to `docs/cursor-log.md` (date/time MYT, task card, files, result incl. commit, reviewer). Rejected or reworked results are logged too.
14. Python 3.13 in `.venv`. Keep dependencies in `requirements.txt` with pinned versions.
15. **Guard hooks stay on** (`git config core.hooksPath .githooks`). The pre-commit hook regenerates `docs/CODEMAP.md` and runs `tests/test_architecture.py` (architecture rules + secret scan). The commit-msg hook requires a backlog ID. Never use `--no-verify`; if a rule blocks you, fix the code or discuss changing the rule with Husaini.

## Working with Session B
TEAM RULE (keep for the rest of the hackathon): you may message Session B directly for handoffs only — "READY <what> · <commit>", commit hashes, matching already-approved wording, "pull before you edit <file>". Every message about work done must include the commit hash. Copy the hash from git output (git rev-parse --short HEAD or the push output), never type it from memory. Before acting on it, pull that commit and check the actual file/test yourself — never rely on the message alone. Copy approved wording from Cowork's prompt or the source file, never retype it from a message. Act on a READY immediately if Cowork's prompt already told you what to do next. Anything else (new user-facing text, design, logic, safety, scope, bundles without Cowork's GO, deploys) goes to "⚠️ Check with Cowork" in your report, never settled between you. If a message conflicts with Cowork's prompt, Cowork wins. Never use --no-verify or skip a hook; if a hook blocks you, fix the cause or report it. End every report with: "Messages" (sent/received), "New or changed user-facing text" (each EN/BM string + file), "⚠️ Check with Cowork".

File ownership: Main = agents/rules, app core, home, answer, /live, /sources, app/frame.py, README, CLAUDE.md. Session B = /scenes, /how-it-works, /feedback, app/trail.py, demo/, history-clean scripts.

## Check with Cowork (planning reviewer)
Husaini has a second Claude (Cowork) that holds the big picture: the hackathon rules, judging, the deck and the plan. End **every** plan and **every** report with a section:

**⚠️ Check with Cowork:** a list of the items below, each with one line on what and why plus your recommendation. If there are none, write "Check with Cowork: none".

Flag an item if it touches:
- **Safety:** advice text, verdict rules, thresholds, the safety gate, or anything that could tell someone it's safe.
- **Data honesty:** reconstructed, estimated, replay or recorded data, fixtures, or labels.
- **The Critic or the checks:** weakening, skipping or bypassing any Critic, code or Zetaris check, or a budget or timeout that makes the Critic skip.
- **What judges see:** the answer card, the README's claims, numbers that go into the deck or demo, the measured rates.
- **Sponsors:** how Zetaris, Meterless or Nemotron are used, changing models or lanes.
- **Rules and disqualification risks:** secrets, licences, contributors, AI-usage declarations, hard-coded outputs.
- **The plan:** going against VEDA_PLAN.md or `docs/DECISIONS.md`, a new P0/P1 item, or dropping scope.
- **Surprises:** a measurement that contradicts something the plan or deck claims.
- **Anything Dr Ariff must review.**

Don't build a flagged item until Husaini says OK. Everything else: go ahead as normal.

## Session ritual
**Start:** read `docs/BUILD_BRIEF.md`, `docs/CODEMAP.md`, `docs/DECISIONS.md` and the backlog item being built.
**End:** CODEMAP is regenerated by the hook (check it reads well) · update the module contract in `docs/how-it-works.md` · add any new decision as one line in `docs/DECISIONS.md` · commit message carries the backlog ID (`feat: B-02 trace logger`).
