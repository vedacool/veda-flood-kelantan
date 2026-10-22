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
| 2026-10-22 | CI actions on Node 24 (checkout v7.0.1, setup-python v7.0.0, gitleaks-action v3.0.0), pinned to commit SHAs; runner pinned to ubuntu-24.04; Dependabot proposes weekly updates (PRs only) | dependency review 2026-10-22 (Node 20 removed from runners) |
| 2026-10-22 | Dependency age policy: prefer releases ≥ ~2 weeks old unless it is a security fix; exception: certifi (CA list should be current). Applied: soupsieve 3.0.4 → 2.10, pluggy 1.7.0 → 1.6.0; local pip 25.1.1 (6 advisories) → 26.2.1 | dependency review 2026-10-22 |
| 2026-10-22 | Curated network = 16 gauges (5 core + upstream sentinels on Galas/Lebir/Golok + controlling gauges for Pasir Mas, Kota Bharu, Tumpat); all 36 still collected. Every chain order / town-control assumption is "tentative - needs Dr Ariff" until reviewed | B-67 · Husaini 22 Oct (option A) |
| 2026-10-22 | `data/stations_mapping.csv` is the single source of truth for the mapping; review it, then re-run `scripts/seed_stations.py` | B-67 |
| 2026-10-22 | Lags stored as ranges, "reported, tentative": Kuala Krai→Kusial 6–9 h, Kuala Krai→Tambatan Diraja 9–17 h, Dabong→Kuala Krai ~23 h (single event, low confidence); all others empty | B-67 · Husaini 22 Oct |
| 2026-10-22 | Threshold cross-check uses the 2014 JPS table, not data.gov.my: data.gov.my's frozen `warning_level` repeats the normal level for most gauges | B-67 |
| 2026-10-22 | Python connects to veda-pg at `127.0.0.1`, not `localhost` (Windows tried IPv6 first: ~10 s per connection) | B-67 |
| 2026-10-22 | Plan to freeze (Husaini OK): merge World Model items (B-10/11/57), safety (B-41→B-58), SAMPLE_MODE (B-39→B-18), healing (B-45→B-15), entry points (B-40→B-19), bootstrap (setup scripts→B-38), go-public (B-25/48/49→B-53), docs (B-23/52→B-24); defer B-22, B-31, B-33–36, B-44, B-46, B-60, B-62, B-63, B-68; record SAMPLE_MODE fixtures as each agent is built; recommend a plain Python agent loop over LangGraph (decision pending) | backlog review 22 Oct |
| 2026-10-22 | B-07 slim: rain at 5 core gauges + Galas and Lebir upstream points; Thai-side Golok rain deferred (README gap) | backlog review 22 Oct |
| 2026-10-22 | All Open-Meteo rain points in ONE REST table (multi-location request; Zetaris returns one row per point); read `COALESCE(location_id, 0)` | B-07 probe |
| 2026-10-22 | Coordinates kept at full precision in CSVs (a builder bug had rounded them to 6 significant digits, ~40 m) | B-07 |
| 2026-10-22 | Historic peaks: official JPS 2014 table (USM CGSS slides URL) + verified news figures only, each row with its own URL; conflicting sources kept side by side, official wins; unverified 10.97 m dropped | B-55 · source check by research agent + spot-check |
| 2026-10-22 | Any "current level" sentence shows the reading time (MYT) - never "now" - until freshness limits are agreed | B-55 |
| 2026-10-22 | Agent orchestration: plain Python loop as an explicit state machine plan → gather → forecast → draft → critique → revise → done; no LangGraph | Husaini 22 Oct (VEDA_PLAN §4, B-17) |
| 2026-10-22 | B-09 first places: Pasir Mas town, Rantau Panjang (needed for the B-70 Nov 2024 replay), Kota Bharu, Tumpat — with aliases/spelling variants and a "Did you mean…?" reply | Husaini 22 Oct |
| 2026-10-22 | Freshness defaults (tentative — Dr Ariff to review): JPS levels fresh ≤1 h / aging 1–3 h / stale >3 h · Open-Meteo forecast ≤6 h / 6–12 h / >12 h · MET warnings ≤12 h / 12–24 h / >24 h; aging lowers confidence, stale = not used | Husaini 22 Oct (supersedes the B-05 KIV) |
| 2026-10-22 | All open "needs Dr Ariff" items collected in `docs/review_pack_ariff.md` (~1 h, priority order) | Husaini 22 Oct |
| 2026-10-22 | Views carry facts (age, band, change, rain sums); freshness and verdicts are judged in Python, so tentative limits live in one place | B-08 |
| 2026-10-22 | `rain_points` copied into veda-pg by setup_wx so views can name each Open-Meteo row; `place_risk_inputs` waits for the B-09 gazetteer (B-08 marked done then) | B-08 |
| 2026-10-22 | Open-Meteo fetch time is not visible to views (cache keeps no timestamp) → B-13 records refresh times for forecast freshness | B-08 |
| 2026-10-22 | Gazetteer never guesses: close spellings get "Did you mean…?", unknown names get "not covered yet" with the covered list; known-Kelantan names come from the MetMalaysia forecast list (data, not a hard-coded list) | B-09 |
| 2026-10-22 | Tumpat: Kg Kok Majid (Sg Kelantan) is the primary controlling gauge, Kuala Jambu (Sg Golok) secondary; kampung/school names not covered in v1 | Husaini 22 Oct (B-09) |
| 2026-10-22 | First committed SAMPLE_MODE fixtures = the gazetteer's two queries; offline gazetteer tests replay them in CI | B-09 (start of B-18) |
| 2026-10-22 | World Model = Python implementation following the Meterless reference semantics; conformance = one-for-one Python port of the 8 official checks (same ids/inputs/thresholds), labelled as a port; Meterless asked (D-09, Husaini) whether that is accepted | B-10/B-11 |
| 2026-10-22 | World Model storage: append-only SQLite event log, state rebuilt from events; timestamps from provenance, never the wall clock (reproducible re-runs) | B-10 |
| 2026-10-22 | Edges that may exist several times from one node (e.g. a gauge that is a sentinel for several places) carry the place as `context`, because a same-(from, type, context) edge supersedes the old one | B-10 |
| 2026-10-22 | Enrichment queue, control plane and supervisor agent are listed as dormant in `manifest()` (spec's wired-vs-helper honesty) | B-10 |
| 2026-10-22 | World Model facts are stamped with the time the DATA refers to (gauge reading time, forecast window, forecast date), not the query time - keeps ingest idempotent and ages honest; unchanged upserts write no event | B-10 |
| 2026-10-22 | B-57 (trace shows agents reading/writing the World Model) stays open until the agents exist (B-12/B-13) | B-10 |
| 2026-10-22 | Agents may `UNCACHE TABLE veda_wx.<table>` (nothing else) so the Data agent can refresh an old forecast and record when; all other UNCACHE stays setup-only | B-13 |
| 2026-10-22 | MetMalaysia town forecast uses the MET limits (≤12 h fresh / ≤24 h aging); forecast age = time since the Data agent's last recorded refresh, "unknown" when none (status degraded) | B-13 |
| 2026-10-22 | Plausibility limits (tentative, Dr Ariff): level −5…120 m, ≤15 m above danger, ≤3 m change in 1 h, ≤1000 mm rain in 24 h; failing readings are kept with confidence 0.2, never silently dropped | B-13 |
| 2026-10-22 | data.gov.my `/flood-warning` shares JPS station ids → the Data agent's agreement check compares them and excludes the frozen source, recording why in the World Model | B-13 |
| 2026-10-22 | The Data agent's clock is Zetaris's `current_timestamp()` — live = now, SAMPLE_MODE = recording time — so replayed ages are consistent | B-13 |
| 2026-10-22 | Coordinator: the model proposes, code decides — place only from the gazetteer, allowed values enforced, corrections traced; drafts are checked (no invented decimals, no verdict words) and the safety line is added by code | B-12 |
| 2026-10-22 | Until B-18, SAMPLE_MODE (and any Nightshift outage) uses the code-written plan and answer — real logic over the same evidence, traced as `fallback` | B-12 |
| 2026-10-22 | Loop skeleton logs forecast / critique as "skipped — not built yet"; without the Forecast agent the answer gives no verdict | B-12 |
| 2026-10-22 | Question radar stores intent tags only (a run context in the World Model), never the question text | B-12 |
| 2026-10-22 | Plan change log (22 Oct night, reconciliation with the code) adopted in the repo — the rows below | Husaini 22 Oct |
| 2026-10-22 | The code agent is called **"Data & Reconciler"** in traces and docs; the file stays `app/agents/data_agent.py` | Husaini 22 Oct |
| 2026-10-22 | The quick path must really skip steps (not just be labelled quick) | Husaini 22 Oct → B-17 |
| 2026-10-22 | Time budget: quick ≤ 30 s, full ≤ 90 s; per-call timeouts Zetaris 30 s, Nightshift 60 s (were 120 s / 180 s) | Husaini 22 Oct → B-17 |
| 2026-10-22 | B-70 replay uses the verified Rantau Panjang peak 10.94 m (27 Nov 2024 19:30), never the unverified 10.97 m | Husaini 22 Oct |
| 2026-10-22 | Agents never create or replace Zetaris views (guard stays); self-growing = new REST tables + World Model candidates | Husaini 22 Oct |
| 2026-10-22 | Phone and IC (MyKad) numbers are masked in every trace line (`[phone]`, `[IC]`) | Husaini 22 Oct (B-56) |
| 2026-10-22 | Conflicts between sources: reliability first, then recency; anything unresolved goes to `conflicts_unresolved` in the evidence and the answer | Husaini 22 Oct → B-14/B-21 |
| 2026-10-22 | Cursor delegation follows CLAUDE.md rule 13 (`--trust`, no `--force`, `cursor-agent(B-xx): …`) — supersedes plan §11 wording | Husaini 22 Oct |
| 2026-10-22 | No direct NVIDIA fallback — Nightshift is the only AI path | Husaini 22 Oct |
| 2026-10-22 | Python 3.13 everywhere, Dockerfile on `python:3.13-slim` | Husaini 22 Oct → B-19 |
| 2026-10-22 | Place→gauge links are hand-checked edges (`controlled_by`, `also_controlled_by`, `sentinel_for`, `upstream_of`, `travel_time`), not nearest-distance | Husaini 22 Oct |
| 2026-10-22 | Forecast agent applies D-06 in code (tentative); "projected to reach" uses the earliest time of a two-rate range (safety first); projections stop at 24 h (straight-line trends are meaningless further out), so 24–48 h comes from upstream gauges and rain only | B-16 |
| 2026-10-22 | Tide-influenced gauges are judged on their level only (no projection, no "rising fast"): Tambatan Diraja (mapping) and Kok Majid (marked tentative after Tumpat came out WATCH from a tidal rise) | B-16 |
| 2026-10-22 | Historic peaks live in the World Model as one `historic_peaks` fact per gauge; the Forecast agent reads them there and writes its verdict back as a `forecast` fact (B-57: Coordinator, Data & Reconciler and Forecast now read/write the WM) | B-16 |
| 2026-10-22 | The Coordinator's draft must state the Forecast agent's verdict and no other; quick plans get a "now" verdict (current levels only) until B-17 shortens the whole path | B-16 |
| 2026-10-22 | Source reliability (tentative, Dr Ariff) lives on the World Model source contexts: JPS 0.9, data.gov.my flood-warning 0.9, MET warnings 0.9, MET forecast 0.8, Open-Meteo 0.6; reconciliation = reliability, then recency, else `conflicts_unresolved`; the answer must mention every unresolved conflict | B-14 |
| 2026-10-22 | Critic = code checks (cannot be overruled) + its own raw Zetaris re-queries + deep-lane model review; any code/Zetaris problem rejects even if the model approves | B-14 |
| 2026-10-22 | Critic runs with thinking OFF: measured 36 s vs 56 s with thinking on, same decision and reasons (time budget, B-17) | B-14 |
| 2026-10-22 | Unsafe-advice check is a word list (EN + BM) per sentence; a sentence with don't/never/avoid/jangan/elak counts as a warning, not advice | B-14 |
| 2026-10-22 | After 2 rejections the answer is the code-written summary labelled "Low confidence" (built from facts only, so it passes the code checks); rejections are never staged - a forced one would only come from the documented VEDA_FAULTS flag (B-45) | B-14 |
| 2026-10-22 | B-57 closed by B-14: all four agents read and write the World Model in the trace (run context, readings/health, forecast, critic_review + stale_confirmed) | B-14 |
| 2026-10-22 | Speed: the 10 world queries run in parallel (28 s → 6 s measured) and start in a background thread while the Coordinator plans; forecast refresh happens there too (no plan needed) | B-17 |
| 2026-10-22 | Lightning calls use max_tokens 4000 (measured: at 2000, 2 of 3 plan calls came back empty and were retried, 51–57 s; at 4000, 0 of 3, 12–34 s) | B-17 |
| 2026-10-22 | Budget enforcement: no model call starts with < 10 s of the budget left; the step falls back to code (answer by code / review by code + Zetaris) and a `budget` trace line says so; planning call capped at 30 s | B-17 |
| 2026-10-22 | Quick path = river levels + MET forecast, no cross-check/reconciliation, "now" forecast, Critic code checks only (no deep-lane call, no re-query) | B-17 |
| 2026-10-22 | `trace.bind` runs each call in its own context copy (the old version crashed when one bound function ran in two threads) | B-17 |
| 2026-10-22 | Every model call keeps 2 s in reserve for the steps after it; the Critic's model gets only what is left after its own re-query; with < 6 s left the re-query is skipped too (the Data & Reconciler agent has already excluded the stale source) | B-17 |
| 2026-10-22 | Measured live 22 Oct: gather 0.1–1.7 s (was 35–45 s); quick 23–28 s within 30 s but the answer is code-written (Lightning plan 11–22 s leaves too little for a draft); full 92–95 s - Lightning drafts vary 12–69 s and the deep review 45–80 s, so under 90 s the AI review often cannot run. Budget numbers to be re-decided by Husaini | B-17 |

