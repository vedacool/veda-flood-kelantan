# Decisions log
_One line per decision: date · decision · why / where. Newest at the bottom. Add a line whenever a session decides something a later session must not undo._

| Date | Decision | Why / where |
|---|---|---|
| 2026-10-22 | Python 3.13 in `.venv`, pinned `requirements.txt` | B-01 · CLAUDE.md rule 14 |
| 2026-10-22 | `run_sql()` converts types — Zetaris returns every value as a string | B-64 spike 1 |
| 2026-10-22 | Expect ~2–3 s per Zetaris call; prefer a few fused views over many small queries | B-64 spike 1 (2.1 s floor) |
| 2026-10-22 | data.gov.my URLs use the trailing slash (`/weather/forecast/?…`) | B-64 spike 2 (no slash → 301) |
| 2026-10-22 | `CACHE TABLE` every data.gov.my REST table on creation, re-cache ≤ every 15 min; 429 → cached/backup, never crash | B-64 spike 2 (429 on 3rd uncached read) |
| 2026-10-22 | Zetaris reaches Postgres at `veda-pg:5432` on `zetaris_default`; `host.docker.internal:5433` is the fallback | B-64 spike 3 (both work) |
| 2026-10-22 | Zetaris reads Postgres as read-only role `veda_zetaris`; Python writes directly | B-64 spike 3 |
| 2026-10-22 | Nightshift adapter logs `served_model` + `meterless.mode` from every response | B-64 spike 4 (lanes report `mode: auto`; fix tracked in B-66) |
| 2026-10-22 | Critic may use `tools` through Nightshift; JSON + Pydantic stays the fallback | B-64 spike 4 (tool calls pass through) |
| 2026-10-22 | Nightshift calls keep `max_tokens ≥ 200` | B-64 spike 4 (small budget + thinking → empty response) |
| 2026-10-22 | VEDA's own `stations` table is the station key (`jps_id` nullable, `mygov_id`, normalised name); hand-curated mapping for our 5 stations | B-64 spike 5 (ID match 0 %, 8/36 JPS IDs blank) |
| 2026-10-22 | DDL allow-list treats "already exists" as success; SchemaStore containers are created once in setup (no SQL drop) | B-64 spike 6 |
| 2026-10-22 | Trace logger lives at `app/trace.py`; every agent imports it (guard rule) | B-65 |
| 2026-10-22 | Guard rules in `tests/test_architecture.py` run on every commit; secret scan uses a small Python scanner (no gitleaks for now) and covers every tracked file incl. `spikes/` | B-65 |
| 2026-10-22 | Every commit message carries a backlog ID (`B-xx` / `S-xx`) | B-65 (commit-msg hook) |
