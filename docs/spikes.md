# Day-1 spike tests (B-64) — results
_Run 22 Oct 2026, 10:34–10:50 MYT, against the real local Zetaris, Nightshift and live public sources.
Scripts: `spikes/s1…s6` (throwaway — not VEDA code). Raw evidence: `logs/spike-*.jsonl` (gitignored)._

## Summary
| # | Spike | Result | Key numbers |
|---|---|---|---|
| 1 | Open-Meteo REST table + `CACHE TABLE` | ✅ PASS | 72 hourly rows. Uncached 2.5–2.9 s, cached 2.2 s; cache persists across separate API calls |
| 2 | data.gov.my ×3 via Zetaris (`meta=true`) | ✅ PASS | forecast 70 Kelantan rows · warning 5 rows · flood-warning 52 Kelantan stations, **newest 2024-02-23 14:45** (still frozen) · **429 on the 3rd uncached read**; 6/6 OK once cached |
| 3 | Postgres (`veda-pg`) as Zetaris datasource | ✅ PASS | Python writes → Zetaris reads back. **Both addresses work** (see below) |
| 4 | Nightshift `fast`/`deep` from Windows Python | ✅ PASS (⚠ routing) | ~0.5–2 s per call. JSON, `extra_body`, `response_format`, `tools` all pass through. **Lanes are not pinned — every call reports `mode: auto`** |
| 5 | JPS parse + snapshot + station-id match | ✅ PASS (⚠ IDs) | 200 OK, 28.5 KB, 36 stations, snapshot saved. **ID match with data.gov.my = 0 %**; name match 25/52 |
| 6 | Runtime DDL via API key | ✅ PASS | create / replace view / drop all work; exact error texts captured |
| 7 | Cursor CLI `agent -p` (optional) | ⏸ BLOCKED | Installed; needs one-time workspace trust (Husaini's call) |

## Details and decisions

### 1. REST table + cache
- `DESCRIBE BY "…"` accepts only letters, digits, `_ . - ,` — **no spaces or brackets** (first attempt failed on this).
- Every Zetaris API call has a **~2.1 s floor**, even `SELECT 1`. Budget ~2–3 s per `run_sql()`; a run with 15 queries is ~40 s.
- Rows come back as **lists of strings** (`[['2026-10-22T00:00', '0.0'], …]`) → `run_sql()` must convert types.
- → **Decision:** B-04 `run_sql()` converts types. The Data agent batches fused views instead of issuing many small queries.

### 2. data.gov.my
- Without a trailing slash, data.gov.my answers **301**. Use `/weather/forecast/?meta=true…`, not `/weather/forecast?meta=true…`.
- `ifilter=kelantan@state` works inside the REST table URL (server-side filter).
- **429 after 2 uncached reads in a burst.** `CACHE TABLE` fixes it (6/6 OK).
- `/flood-warning` is still frozen at **2024-02-23** — good: the staleness check has a real target.
- → **Decision:** `CACHE TABLE` every data.gov.my table right after creating it. Re-cache at most every 15 min. Treat 429 as "use cached / backup", never a crash.

### 3. Postgres datasource — which address works
| Option | JDBC URL | Result |
|---|---|---|
| A | `jdbc:postgresql://host.docker.internal:5433/veda` (veda-pg not on Zetaris network) | ✅ works |
| B | `jdbc:postgresql://veda-pg:5432/veda` after `docker network connect zetaris_default veda-pg` | ✅ works |
- JDBC driver `org.postgresql.Driver` is bundled with Zetaris.
- `veda-pg` = `postgres:16-alpine`, host port **5433**, volume `veda-pg-data`, `--restart unless-stopped`. Zetaris logs in as the **read-only** role `veda_zetaris`; Python writes as `postgres`. Password comes only from `.env` (`VEDA_PG_PASSWORD`); it is redacted in logs (verified: 0 occurrences).
- → **Decision:** use **B (`veda-pg:5432` on `zetaris_default`)**. It doesn't depend on Docker Desktop's host bridge. A stays the documented fallback. ⚠ The network join is lost if `veda-pg` is re-created → put it in the setup script.
- Timestamps come back without a time zone → store UTC and label it.
- Follow-up: the read-only role currently shares the superuser password. Give it its own `VEDA_PG_RO_PASSWORD` when the real schema is built.

### 4. Nightshift
- `GET /v1/models` lists 76 routes, including `meterless/fast`, `meterless/deep` and all Nemotron IDs.
- `fast` and `deep` both answered correctly. JSON with thinking off was **valid on both lanes**. `response_format: json_object` is accepted.
- **Tool calling passes through** on both lanes (correct `run_sql` tool_calls returned).
- `reasoning_content` is **not returned**, even with thinking on.
- `max_tokens` that is too small with thinking on gives `provider_error … _empty_response` → keep `max_tokens ≥ 200`.
- ⚠ **Routing:** every request — `fast`, `deep`, `meterless/fast`, even `nvidia/nemotron-3.5-lightning-30b-a3b` — comes back with `meterless.mode = "auto"`, `provider_model = "meterless/auto"`. 5/5 were served by **Super VL**. Lightning served only one tool call. It is always Nemotron, so the award is not at risk, but the lanes aren't pinned.
- → **Action (Husaini):** in the Nightshift Cockpit (NIGHT → LANES), check whether a global *Auto*/race mode overrides lanes. Pin `fast` = Lightning and `deep` = Super VL, then re-run `spikes/s4_nightshift.py`.
- → **Decision:** B-03 adapter logs `served_model` and `meterless.mode` from every response (proof for judges). Use `tools` for the Critic's re-query. JSON + Pydantic stays the fallback.

### 5. JPS + station-id match
- The page parses cleanly via `data-th` columns: `Station ID, Station Name, District, Main Basin, Sub River Basin, Last Update, wl, Normal, Alert, Warning, Danger`.
- Snapshot: `data/snapshots/jps/kel-20261022-1040.html`. The script reuses a snapshot < 15 min old (scrape rule) and identifies itself with a User-Agent.
- Our 5 stations:
  | Brief name | JPS row | Station ID |
  |---|---|---|
  | Golok @ Rantau Panjang | Sg. Golok di Rantau Panjang (F1) | 0740121WL |
  | Kelantan @ Tambatan Diraja | Sg. Kelantan di Tambatan D'Raja (F1) | 0730671WL |
  | Kelantan @ Tangga Krai | **Sg. Kelantan di Kuala Krai (F1)** | *(blank)* |
  | Galas @ Dabong | Sg. Galas di Dabong (F1) | *(blank)* |
  | Kelantan @ Jambatan Guillemard | **not named** — likely Sg. Kelantan di Kusial (0731371WL) or Kusial Baru (blank) | ? |
- **8 of 36 JPS rows have no Station ID**, including 2 of ours.
- **Correction (B-06):** each JPS row also has a graph-link id (`…/wl-graph/?stationid=_DKBR0007`). It is never blank and equals the data.gov.my `station_id` for **24/36** stations, including 4 of our 5 core ones. VEDA uses it as `station_key`. The 0 % below compared only the visible Station ID column.
- **ID match JPS ↔ data.gov.my `/flood-warning`: 0 / 52 (0 %).** JPS now uses new IDs (`0730671WL`). data.gov.my keeps the old ones (`_DKBR0007`, `5320038_DKKI0003`, station_code `DKBR0007`/`DABONG`).
- **Name match** (lower-case, brackets and punctuation removed): 25/52 data.gov.my stations match a JPS station (24/36 JPS stations covered).
- → **Decision:** our own `stations` table is the key. It holds a VEDA `station_key`, plus `jps_id` (nullable), `mygov_id`/`mygov_code` and the normalised name. The scraper joins on `jps_id` when present, otherwise on the normalised name. The cross-source mapping for our 5 stations is curated by hand.
- → **Ask Dr Ariff:** which Kusial row is the "Jambatan Guillemard" station, and is "Kuala Krai" the Tangga Krai gauge?

### 6. Runtime DDL
| Statement | Result |
|---|---|
| `CREATE LIGHTNING REST TABLE …` | ✅ |
| same again | ❌ `A table named "om_ddl_test" already exists in database "VEDA_SPIKE".` |
| `CREATE SCHEMASTORE CONTAINER` / `VIEW … WITH CONTAINER` / `CREATE OR REPLACE SCHEMASTORE VIEW` | ✅ |
| `DROP SCHEMASTORE VIEW <v> FROM <container>` | ✅ (`… WITH CONTAINER` is a parse error) |
| `DROP LIGHTNING DATABASE TABLE DB.t` | ✅ · again → `Table: om_ddl_test doesn't exist` |
| `DROP LIGHTNING DATABASE <db>` · `DROP DATASOURCE <ds>` | ✅ |
| `DROP SCHEMASTORE CONTAINER` | ❌ not supported in SQL |
- → **Decision:** the Healer's DDL allow-list treats "already exists" as success. **Create SchemaStore containers once, in setup only**, because they can't be dropped by SQL.

### 7. Cursor CLI
- `agent` is installed at `%LOCALAPPDATA%\cursor-agent`. The first run stops at **Workspace Trust Required**.
- → **Action (Husaini):** run `agent` once interactively in the repo folder and trust it. After that, `agent -p "…" --output-format json` will work for delegated jobs.

## Clean-up state after the spikes
- Zetaris: `VEDA_SPIKE` DB, all REST tables, the view and both test datasources dropped. **Left over:** empty SchemaStore container `veda_spike_views` (can't be dropped via SQL — delete in the Zetaris UI if wanted; harmless).
- `veda-pg`: running and joined to `zetaris_default`. Role `veda_zetaris` exists. Test table dropped.
- `data/cache/spike_mygov_flood_stations.json` (gitignored) — station list used for the ID match.
