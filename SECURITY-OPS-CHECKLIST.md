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
- [ ] **Going public = a NEW public repository from a cleaned copy** (B-75; plan changed by Husaini 23 Oct - this
      replaces the earlier force-push + delete-Actions-runs plan). Real run **Mon 26 Oct, before the first
      submission, only with Husaini's OK**:
      1. `github.com/vedacool/veda` stays **PRIVATE and untouched** - full history, push records and CI runs kept as
         evidence of build timing. **No force push, no deleted Actions runs** there.
      2. A fresh `git clone --mirror` of the private repo (scratch, never pushed) -> `git filter-repo`: every **old**
         version (not in today's tree) of the JPS page snapshot, `data/fixtures/`, `tests/fixtures/jps_*`,
         `data/replay/synthetic_anchors.csv`, `output_examples/` and `data/sample/live_traces/` stripped; in every
         other old blob each real reading in **any written form** becomes "[JPS reading]" (except lines unchanged in
         today's tree, cited replay values, thresholds / peaks, numbers that are not a level); `--prune-empty never`;
         authors and commit dates kept; today's files untouched. Script kept outside the repo
         (`veda-private/history-clean/public_dryrun.py`).
      3. A working clone of the cleaned mirror gets ONE new commit: `docs/history/commit-map.txt` (filter-repo's
         commit map, original ID -> public ID, IDs only), the README **"Repository history"** note (Husaini's text),
         and `.gitleaksignore` with its commit IDs translated through the map (otherwise the known made-up test
         values in the B-02 commit are reported again - measured in the dry run).
      4. Before publishing: CI green on the new repo; history search **0 unexplained**; the clean-clone test
         (fresh clone, empty `.env`, Zetaris and Nightshift stopped, SAMPLE_MODE); gitleaks over the full history.
      5. Create the new public repo (suggested name: **`vedacool/veda-kelantan`**), push, check CI, then record it in
         `docs/DECISIONS.md` and update links. **Link sweep (only after the public repo exists)**, in the public repo's
         working clone: `python scripts/public_links.py` (dry run: lists every CHANGE and every KEEP), check it, then
         `python scripts/public_links.py --apply`, `pytest -q`, commit (`docs: B-77 links point to the public repo`),
         push. It switches every link to `github.com/vedacool/veda` in tracked files - today: `docs/JUDGES.md` (both
         clone commands), `metadata.json`, the User-Agents in `app/ingest/jps.py`, `scripts/load_osm.py`,
         `spikes/s5_jps.py`, and line 29 here - and keeps the lines that name the private repo on purpose (this list,
         `docs/DECISIONS.md`, `docs/submission.md`). A different repo name: add `--to https://github.com/vedacool/<name>`.
         Then apply the same commit to the private repo's main so the two stay in step.
      **Dry run 23 Oct 18:25 MYT** (scratch only, nothing created on GitHub, private repo untouched): 122 -> 122
      commits, authors and dates unchanged, + 1 map commit = **123**; **first commit 22 Oct 2026 10:22:15 MYT
      (02:22:15 UTC)**, same ID as the original (nothing to strip in it); **commit map 122 lines** (+1 header); 226
      old blobs stripped, 105 old blobs rewritten; today's tree identical to the private HEAD; history search over
      196 real values in any form: 322 hits on lines unchanged in today's tree, 160 cited replay values, 1 not a
      level, **0 unexplained**; gitleaks v8.21.2 over the full history: **no leaks** (1 before translating
      `.gitleaksignore`); in the scratch repo with no `.env`: 746 tests pass, evals 24/24. Not tested in the dry run:
      CI on GitHub and the clean clone with Zetaris and Nightshift stopped (both on Monday).
      **Rehearsal 24 Oct 11:50 MYT (B-77, Session B)** - the real procedure on a fresh mirror of
      `github.com/vedacool/veda` at `ae55221`, stopped before creating anything on GitHub: `refs/pull/*` dropped
      (only `main` goes public); 160 -> 160 commits, authors and dates unchanged, + 1 map commit = **161**; first
      commit 22 Oct 2026 10:22:15 MYT; commit map 160 lines; 291 old blobs stripped, 156 rewritten; today's tree
      identical to the private HEAD; history search over 220 real values: 1591 hits on lines unchanged in today's
      tree, 163 cited replay values, 1 not a level, **0 unexplained**; gitleaks v8.21.2 over the full history: **no
      leaks** (156 commits with changes); in the cleaned clone with no `.env`, SAMPLE_MODE: 838 tests pass (13 live
      skipped), `test_no_jps_readings` 6/6, evals 30/30. The map commit now runs the project hooks (it did not in the
      dry run). Scripts: `veda-private/history-clean/public_clean.py` + `history_probe3.py` (+ `fr/`, `gitleaks/`
      beside them; they write to `work/` there). Monday, with Husaini's OK, from that folder:
      1. `python public_clean.py` then `python history_probe3.py work\veda-public` (must print 0 unexplained) and
         `gitleaks\gitleaks.exe detect --source work\veda-public --log-opts="--all" --redact`;
      2. in `work\veda-public`: `pytest -q` and `python scripts/run_evals.py` with an empty `.env`;
      3. `gh repo create vedacool/veda-kelantan --private`, `git remote add public <url>`, `git push public main`;
         wait for CI green, then `gh repo edit vedacool/veda-kelantan --visibility public
         --accept-visibility-change-consequences` and check it logged out (step 5 above).
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
- [x] A privacy notice in BM + EN under the question box: no names, IC, phone or address; the AI writes from the
      checked facts only, the question is not sent to any AI model and stays in local logs, phone / IC masked
      (Husaini 23 Oct wording; `tests/test_privacy_no_question_to_model.py`).
- [x] Phone, IC and email are masked in traces. The question is never sent to a model, and never written to the
      access log.
- [x] Only intent tags go into the World Model, never the question text.
- [ ] Log retention: `logs/` is never pruned yet (audit P3). Prune or state a period before any public deployment.
- [ ] This list is not legal advice; any real deployment needs the notice signed off (PDPA).
