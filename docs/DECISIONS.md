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
| 2026-10-22 | Trace line = FAQ fields + `run_id`, `step`, `decision`, `source`, `mode`, `duration_ms`, `details`; fixed status set; JSON in UTC, sentences in local time | B-02 |
| 2026-10-22 | Trace redacts secrets itself (patterns + env secret values) — callers never need to remember | B-02 |
| 2026-10-22 | Each lane has its own `meterless-app` header (`veda-fast`, `veda-deep`, from `.env`) | B-03 · receipt shows Nightshift binds routing mode per app (`app_policy.bound_mode`) |
| 2026-10-22 | Default `max_tokens` 2000; `empty_response` → one retry with double budget | B-03 probe: Lightning uses ~1.1–1.4k hidden tokens even with thinking off |
| 2026-10-22 | Adapter refuses live calls in SAMPLE_MODE until the SampleGenerator lands | B-03 → B-18 |
| 2026-10-22 | `run_sql` is SELECT/WITH only; DDL goes through `run_ddl` with an allow-list | B-04 |
| 2026-10-22 | Fixtures keyed by sha256 of whitespace-normalised SQL; store raw Zetaris text, coerce on read (live and replay identical) | B-04 |
| 2026-10-22 | Numbers coerced only without leading zeros, so station IDs like `0740121WL` / `0730671` stay text | B-04 |
| 2026-10-22 | Zetaris error kinds: auth · sql · source_unavailable · network · no_fixture · not_allowed; only network/5xx retried (2 s, 4 s) | B-04 |
| 2026-10-22 | Postgres tables (v3 scope): `stations`, `river_levels`, `places`, `historic_peaks`, `source_registry` — "schools" in the old backlog wording is now `places` (kind = school) | B-05 |
| 2026-10-22 | Read-only role `veda_zetaris` has its own password `VEDA_PG_RO_PASSWORD` | B-05 (spike 3 follow-up) |
| 2026-10-22 | `CREATE DATASOURCE` only via `run_ddl(setup=True)` from `scripts/`; guard rule bans it in agents | B-05 |
| 2026-10-22 | `source_registry` freshness SLAs / trust status **KIV** — Husaini + Dr Ariff still discussing; table stays empty, `freshness_sla_min` nullable | B-05 |
| 2026-10-22 | **Supersedes the spike-5 key decision:** `station_key` = JPS graph-link id (`…/wl-graph/?stationid=_DKBR0007`) — every row has one; it equals the data.gov.my `station_id` for 24/36 stations (spike measured 0 % because it compared the visible Station ID column) | B-06 |
| 2026-10-22 | JPS collector: ≤ 1 live fetch / 15 min, no override; raw snapshots in `data/cache/jps/` (ignored), selected ones committed to `data/snapshots/jps/` | B-06 |
| 2026-10-22 | Agents may not import DB drivers (`psycopg`, `sqlite3`) — guard rule, same as HTTP libraries | B-06 |
| 2026-10-22 | Lane pinning = per-app **lane allowlist** in Nightshift `app-policy.json` (`veda-fast` → `["fast"]`, `veda-deep` → `["deep"]`); app `mode` alone never pins a model (it is a core mode, not a lane) | B-66 · found in Nightshift engine code (select.js `modelOnAllowedLanes`); public docs silent |
| 2026-10-22 | Both Nightshift lanes stay `role = "race"`, `races = true`; `verify` role / `races = false` lanes never answer | B-66 |
| 2026-10-22 | Adapter `pinned` = lane honoured AND expected model answered (Lightning / Super VL, env-overridable); otherwise trace says "WRONG MODEL" | B-66 |
| 2026-10-22 | Shared settings live in `app/config.py` (flags, MYT, Postgres address, secret patterns) - no copies in modules or tests | audit 2026-10-22 |
| 2026-10-22 | `run_sql` read-only = SELECT/WITH start AND no write/DDL word or reflect/java_method outside quotes; comments are stripped, never joined into the query | audit P1 #1-2 |
| 2026-10-22 | Agents' DDL: only `CACHE TABLE` and REST tables on https `api.data.gov.my` / `api.open-meteo.com` / `flood-api.open-meteo.com`; everything else is `setup=True` (scripts only) | audit P2 |
| 2026-10-22 | JPS upsert never replaces a stored threshold/id with a missing one; ambiguous numbers (decimal comma, nan/inf, 9999, outside -50..1000 m) become NULL | audit P1 #3 / P2 |
| 2026-10-22 | `--loop` collector survives any failed cycle; only config errors stop it | audit P1 #4 |
| 2026-10-22 | veda-pg published on 127.0.0.1 only; ingest writes as `veda_writer` (own password), not the superuser; plausibility/FK constraints added by setup_pg | audit P2/P3 |
| 2026-10-22 | All human-facing times (trace sentences, run ids, snapshot names) in MYT regardless of machine time zone | audit P3 |
| 2026-10-22 | **Won't fix:** no automatic deletion of traces/snapshots (~3 MB/day; they are judging evidence) - revisit only if disk becomes a problem | audit P3 |
| 2026-10-22 | **Deferred to B-18:** committed SAMPLE_MODE fixtures (need the agents' real SQL first); `requirements-lock.txt` pins all deps but without hashes (no pip-tools available) | audit P2/P3 |
| 2026-10-22 | GitHub CI runs guard tests, codemap check, pip-audit and gitleaks on every push, so protection does not depend on local hooks | audit P3 |
