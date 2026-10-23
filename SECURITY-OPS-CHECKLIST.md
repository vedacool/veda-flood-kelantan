# Security & ops checklist — VEDA

Written before the incident, not during it. VEDA runs on one machine (localhost, or one Docker container). It is
not a hosted service. Ticked lines are true today (23 Oct 2026); unticked lines are open, with where they are tracked
(`docs/OPEN.md` or the backlog ID).

## Secrets — where each one lives and how to rotate it
Every secret lives only in `.env` (gitignored) on the machine that runs VEDA. `.env.example` lists the keys with no
values. The trace logger masks secret values, Bearer / Basic auth and phone / IC / email before anything is written.

| Key | What it opens | Rotate by | Then |
|---|---|---|---|
| `ZETARIS_API_KEY` | the Zetaris API (all VEDA data) | Zetaris UI → Management → API Tokens: create a new one, delete the old | update `.env`, restart VEDA |
| `METERLESS_RUNTIME_TOKEN` | Nightshift (the only AI provider) | Nightshift app → regenerate the runtime token | update `.env`, restart VEDA |
| NVIDIA API key (`nvapi-…`) | Nemotron via Nightshift | build.nvidia.com → new key; paste it **only** into Nightshift → Providers | never in `.env` or the repo |
| `VEDA_PG_PASSWORD` | Postgres superuser on `veda-pg` (127.0.0.1:5433 only) | `ALTER ROLE postgres PASSWORD …` inside the container | update `.env` |
| `VEDA_PG_RO_PASSWORD` | role `veda_zetaris`, SELECT only, used by Zetaris | `ALTER ROLE veda_zetaris PASSWORD …` | update `.env` and re-register the `veda_pg` datasource in Zetaris (`python scripts/setup_pg.py`) |
| `VEDA_PG_WRITER_PASSWORD` | role `veda_writer`, INSERT / UPDATE on the ingest tables only | `ALTER ROLE veda_writer PASSWORD …` | update `.env`, restart the JPS collector |

- [x] No secrets in the repo or its history. gitleaks scans the full history on every push, and the commit hook
      blocks secret-looking strings and VEDA's own `.env` values.
- [x] Secrets stay on the server side. The web page receives no keys, and API errors are redacted.
- [x] Least privilege: Zetaris reads Postgres as a read-only role, and the collector writes as a narrow role.
      Postgres listens on 127.0.0.1 only. Agents can only run single read-only SELECTs through `run_sql()`.
- [x] Each secret has a documented rotation (table above); the owner is Husaini.

## Before the repo goes public (do all, in this order)
- [ ] `gitleaks detect` on the full history is clean. (CI does this on every push; check the latest run is green.)
- [x] No personal email in code: the JPS User-Agent is `VEDA-hackathon/0.1 (+https://github.com/vedacool/veda; …)`
      (was a personal address until 23 Oct).
- [x] No local machine paths in docs (a `E:\…` path removed from `docs/spikes.md`, 23 Oct). Re-check with
      `git grep -n -F ":\\"` before publishing.
- [ ] `CLAUDE.local.md`, `.env`, `logs/`, `data/world/` and `data/cache/` are not tracked: `git ls-files` shows none
      of them. (`.gitignore` covers all five.)
- [ ] Recorded traces (`data/sample/live_traces/`, `output_examples/`) hold no personal data. Their questions were
      written by the team; re-read them before publishing.
- [ ] `LICENSE` (MIT, Hujung Lab), `NOTICE` (Apache-2.0 Meterless ports) and the README credits are in place.
- [x] A **clean clone** (fresh `git clone`, empty `.env`, Zetaris and Nightshift stopped) runs SAMPLE_MODE: tests
      pass and `python run.py "…"` answers. Run 23 Oct 16:53 MYT at `70e31c3` (new venv from `requirements.txt`):
      698 tests pass, conformance 8/8, evals 20/20, CLI answers (bare question and Nov 2024 replay in BM), web
      `/health` and `POST /run` 200; every data read came from the offline scenes, no network call. Re-run before
      publishing.
- [x] JPS credit on the page and in the README: "Data: Jabatan Pengairan dan Saliran (JPS) Malaysia,
      publicinfobanjir.water.gov.my, used for non-commercial public-safety research". The collector stays at most once
      per 15 min.
- [x] No JPS readings in the repo (B-75): fixtures from JPS tables hold SYNTHETIC values, the JPS page snapshot is
      gone, recorded live traces are redacted; `tests/test_no_jps_readings.py` guards it.
- [ ] **History clean** (B-75, Husaini's option b) - just before going public, in this order:
      1. a private local **mirror backup** (`git clone --mirror`), kept on this machine and never pushed;
      2. `git filter-repo` stripping only the **old blob versions** (today's synthetic / redacted files at the same
         paths stay): `--strip-blobs-with-ids` with the list built from history (every old version of the JPS page
         snapshot, of `data/fixtures/`, of `tests/fixtures/jps_*`, of `data/replay/synthetic_anchors.csv`, of
         `output_examples/` and of `data/sample/live_traces/`), plus a blob callback that, in every other **old**
         blob, turns each real reading value in **any written form** (N.NN, N.N, N, "N m", "N.NNm", JSON, table cells,
         quotes) into "[JPS reading]" - except lines still unchanged in today's tree, cited Nov 2024 replay values,
         official thresholds / historic peaks, and numbers that are not a level (other unit, a parameter) - and
         `--prune-empty never` so every commit, date and author stays. Today's blobs are never touched.
         Dry run v2, 23 Oct, on a fresh private mirror clone (108 commits): 223 old blobs stripped, 104 old blobs
         rewritten (7 distinct lines, all readings quoted in docs and one docstring example), 108 -> 108 commits with
         authors and dates unchanged, today's tree identical, 0 snapshot commits, 0 stripped blobs left. History
         search for 196 real values (snapshot, JPS-table fixtures, the private unredacted traces) in any form:
         309 hits on lines unchanged in today's tree (synthetic / cited / redacted, guarded by
         `tests/test_no_jps_readings.py`), 160 cited Nov 2024 replay values, 1 not a level, **0 unexplained**;
      3. CI green on the rewritten history; **one** force push;
      4. a history search (`git log -p --all | grep` for the removed files and known reading values) finds nothing;
      5. record it in `docs/DECISIONS.md`.
- [ ] The repo stays private until B-75 steps 3-4 and the history clean are done.
- [ ] JPS written consent - only if VEDA continues after the hackathon (`docs/OPEN.md` W-7).

## Running it
- [x] Tests run on every push (CI); nothing deploys automatically, so there is no deploy gate to bypass.
- [x] CI builds the Docker image and runs a SAMPLE_MODE smoke test in it (23 Oct).
- [x] One run at a time (`429` while busy). The default bind is 127.0.0.1; `VEDA_HOST=0.0.0.0` only inside the container.
- [ ] Security headers (CSP, nosniff, frame-ancestors) — after Gate 1 (`docs/OPEN.md`).
- [ ] Lockfile with hashes (`pip install --require-hashes`) — after Gate 1 (`docs/OPEN.md`).

## Backup & recovery
- [ ] Backups of `veda-pg` (`pg_dump`) and `data/world/world.sqlite` (SQLite `.backup`) — after Gate 1
      (`docs/OPEN.md`).
- [ ] A restore drill actually run into a scratch database (date: ____) — after Gate 1.
- [x] Losing the data is survivable. The JPS levels are re-collected every 15 min, the curated CSVs and the replay
      anchors are in git, and the World Model rebuilds from Zetaris on the next run. Only history is lost.

## When something breaks (runbook)
| Symptom | Likely cause | Do this |
|---|---|---|
| Answers say "VEDA cannot reach its river data right now" | Zetaris down or `ZETARIS_*` not set | `docker ps` for the Zetaris containers; check `.env`. For an offline demo, run with `SAMPLE_MODE=true` |
| Cards with no AI explanation; trace shows `empty response` / 502 | Nightshift / NVIDIA side (cut at ~60 s) | Nothing to fix in VEDA: the code-checked card still goes out. Check the Nightshift app is running |
| "data.gov.my /flood-warning … Not checked" | data.gov.my rate limit (HTTP 429) or outage | Wait 15 min (the breaker and the 15-min memory handle it) |
| JPS reading "too old to use" | JPS collector stopped | Restart it from VEDA Start, or run `python -m app.ingest.jps --loop` |
| `veda-pg` unreachable | container stopped | `docker start veda-pg`. Never run `docker compose down -v` on the Zetaris stack |
| A secret was committed | human error | **Rotate it first** (table above), then purge history; removing it from the tree is not enough |

## Data protection (questions users type)
- [x] A privacy notice in BM + EN under the question box: no names, IC, phone or address; an AI model (NVIDIA
      Nemotron via Nightshift) reads the question; it is kept in local logs.
- [x] Phone, IC and email are masked in traces. The question is never sent to a model, and never written to the
      access log.
- [x] Only intent tags go into the World Model, never the question text.
- [ ] Log retention: `logs/` is never pruned yet (audit P3). Prune or state a period before any public deployment.
- [ ] This list is not legal advice; any real deployment needs the notice signed off (PDPA).
