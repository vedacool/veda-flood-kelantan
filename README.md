# VEDA — Vast Earth Data Analyser

**Team Hujung Lab** · GenAI Works Open Agent Hackathon 2026 · Track: Solving Fragmented Intelligence

VEDA is a multi-agent system that cross-checks fragmented flood data for Kelantan, Malaysia, and tells anyone asking about a place whether it is at risk in the next 24–48 hours and what to do now — with every claim traced to its source.

> 🚧 Work in progress (build window 22–27 Oct 2026). Setup, usage, agent roles, data sources and licences will be documented here.

> ⚠️ Not an official flood warning. Always follow JPS, APM and police instructions. Emergency: 999 · APM: 991.

## Developer setup — guard hooks
After cloning, turn on the repo's git hooks once:
```
git config core.hooksPath .githooks
```
Every commit then regenerates `docs/CODEMAP.md` and runs `tests/test_architecture.py` (agents get data only via Zetaris, no `meterless/auto`, no reads of `output_examples/`, every agent traces, secret scan). Commit messages must carry a backlog ID (`B-xx`). Decisions are logged in `docs/DECISIONS.md`.

## Pre-existing materials
Design notes summarised in `docs/BUILD_BRIEF.md` were written 20–22 Oct 2026, before the build window. All code in this repository was written inside the window.

## AI usage
Built in Cursor with Claude Code (Anthropic) and the Cursor agent as coding assistants. Delegated agent work is logged in `docs/cursor-log.md`. The team designed, reviewed and can explain every module.
