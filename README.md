# VEDA — Vast Earth Data Analyser

**Team Hujung Lab** · GenAI Works Open Agent Hackathon 2026 · Track: Solving Fragmented Intelligence

VEDA is a multi-agent system that cross-checks fragmented flood data for Kelantan, Malaysia, and tells anyone asking about a place whether it is at risk in the next 24–48 hours and what to do now — with every claim traced to its source.

> 🚧 Work in progress (build window 22–27 Oct 2026). Setup, usage, agent roles, data sources and licences will be documented here.

> ⚠️ Not an official flood warning. Always follow JPS, APM and police instructions. Emergency: 999 · APM: 991.

## Developer setup — first time
Python 3.13. From the repo folder:
```
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env             # macOS/Linux: cp .env.example .env  - then fill in the values
python -m pytest -q                # offline tests; live ones run with VEDA_LIVE=1
```

## Developer setup — guard hooks
After cloning, turn on the repo's git hooks once:
```
git config core.hooksPath .githooks
```
Every commit then regenerates `docs/CODEMAP.md` and runs `tests/test_architecture.py` (agents get data only via Zetaris, no `meterless/auto`, no reads of `output_examples/`, every agent traces, secret scan, no invisible control characters). Commit messages must carry a backlog ID (`B-xx`). GitHub CI (`.github/workflows/ci.yml`) runs the same checks plus a dependency vulnerability scan and a secret scan of the whole history on every push. Decisions are logged in `docs/DECISIONS.md`.

## Developer setup — Postgres store (live mode)
With Zetaris running and `.env` filled (`VEDA_PG_PASSWORD`, `VEDA_PG_RO_PASSWORD`, `VEDA_PG_WRITER_PASSWORD`, `ZETARIS_*`; role passwords 16+ letters/digits):
```
python scripts/setup_pg.py
```
Creates/starts the `veda-pg` container (127.0.0.1:5433 only), joins it to the Zetaris network, creates the read-only and writer roles, applies `db/schema.sql` and its constraints, and registers it in Zetaris as datasource `veda_pg`. Safe to re-run. Not needed in SAMPLE_MODE.

## Collecting river levels (live mode)
```
python -m app.ingest.jps --loop     # JPS Kelantan levels every 15 minutes into veda-pg (Ctrl+C to stop)
python -m app.ingest.jps --from-file data/snapshots/jps/kel-20261022-1040.html   # load a saved snapshot
```
At most one request to JPS per 15 minutes, identified by our User-Agent. Agents read the stored levels only through Zetaris.

## Pre-existing materials
Design notes summarised in `docs/BUILD_BRIEF.md` were written 20–22 Oct 2026, before the build window. All code in this repository was written inside the window.

## AI usage
Built in Cursor with Claude Code (Anthropic) and the Cursor agent as coding assistants. Delegated agent work is logged in `docs/cursor-log.md`. The team designed, reviewed and can explain every module.
