# VEDA full audit — 27 Oct 2026 — full sweep at `782f449` (Cowork)

**Profile:** web app + HTTP API, Python 3.11+/FastAPI, Postgres via Zetaris, SQLite World Model · data: no personal data collected (feedback box scrubs emails/phones; no IPs); JPS river readings are third-party data that must not be republished (B-75) · exposure: public demo on the internet (offline replay, no keys) + public GitHub repo; live mode on 127.0.0.1 only · deploy: Docker compose + nginx + Tailscale Funnel on one home server (Wyse), bundle `8a0b94c` · team: two people, no on-call.

**Dimensions run:** functional, security (STRIDE, injection, XSS, route lockdown, secrets, supply chain), data integrity + B-75 data rules, reliability (B-104 fallback, collector), accessibility (axe-core + manual), code quality, deployment. **Skipped:** data-protection regime (no personal data is stored; the feedback box is anonymous and scrubbed); performance load test (single-user demo; scene runs take 0.1–0.3 s).

**Method:** four read-only reviewers on a clean clone (security, functional, demo/data/ops, UX/quality); every P1 re-checked by Cowork on the code.

**Verdict: GO after the two P1s are fixed** (no P0). Both P1s are small and contained.

**Runs:** pytest 1,128 passed, 13 skipped · evals 47/47 (offline) · all 7 test scenes match their expectations in EN and BM (14 runs), also through the page's own path (/run/stream + /scenes/<id>/check) · axe-core: 0 WCAG 2.1 A/AA violations on every page at 375 and 1440 px · pip-audit clean · secret scan over all 304 commits: placeholders and test values only · demo mode under strace: zero outbound connections.

## P1 — fix before submitting

**A-P1-17 · A trapped person is told "Nothing to do now" on the answer screen and in the API** (rule: emergency questions get ACT advice)
- `app/view.py:969-970` builds `action` and `steps` only from the verdict; the ACT advice that `app/loop.py:197-199` puts into `card["action"]` is read only by the plain-text card (`app/card.py:590-597`). `app/api.py:110-111` builds `what_to_do` from the same view fields. The web page uses `emergency` only on the separate SOS screen (`app/web/index.html:1147`).
- Evidence (re-checked by Cowork): `python -m veda ask "I am trapped at Tumpat, water around my house" --scene synthetic_calm --json` → `emergency: True, level: NORMAL, what_to_do: ['Nothing to do now.', 'No action needed.', 'Keep an eye on JPS updates.']`. Same for "Saya terperangkap di Tumpat" and for WATCH ("I am stranded in Kota Bharu" on synthetic_rising). No test covers the view or API for an emergency question.
- Fix: in `view.build`, when `card.get("emergency")`, set `action` and `steps` to the ACT lines in both languages and show the "safety first" label; the verdict and river post still show the data. Tests for NORMAL and WATCH, EN and BM, view + API.

**A-P1-18 · Live JPS values in tracked files of the public repo** (B-75)
- `scripts/seed_peaks.py:114` (docstring) and its copy `docs/CODEMAP.md:573`: an absolute Rantau Panjang level in metres with a live 22 Oct 16:45 MYT time.
- Rise amounts and projection ranges worked out from live readings: `docs/EVIDENCE-live-24oct-evening.md:15,50,61`, `docs/review/ARIFF_MONDAY.md:22,24`, `docs/DECISIONS.md:178`, `docs/review_pack_ariff.md:45`.
- The guard `tests/test_no_jps_readings.py` only scans `data/sample/live_traces`.
- Fix: replace with made-up numbers or "[JPS reading]"/"[rise]", widen the guard to docs/ and scripts/ (allow-list cited thresholds, historic peaks and replay anchors), then sync to the public repo. The history keeps the old lines: accept that, don't rewrite tonight.

## P2

- **A-P2-25 · Screen-reader answer stays English after EN → BM.** `#sr-answer` is filled only by `announce()` (`app/web/index.html:684-690`); `applyLang()` (`:693-727`) doesn't refresh it while `<html lang>` becomes "ms". Fix: call `announce()` at the end of `applyLang()` when a result is shown.
- **A-P2-26 · Live Docker recipe publishes the port on every interface with real keys.** `README.md:409`, `Dockerfile:4` (`-p 8000:8000 --env-file .env`). Fix: `-p 127.0.0.1:8000:8000`.
- **A-P2-27 · A fresh controlling reading found on the Critic's request is never used** (live only, safe side: stays "Can't confirm"). `app/agents/data_agent.py:806-812` swaps the gauge but not `evidence["usable"]` (`:1022`) or `ctx["last_reading"]`; `forecast_agent.py:333` gates on `usable`. After the hackathon.
- **A-P2-28 · Demo rollback not documented; the tar step breaks on a second bundle.** `docs/DEPLOY_DEMO.md:43` `tar -xzf ~/veda-demo-*.tar.gz` fails with two bundles (tested: exit 2); step 7 says `git pull` but the Wyse has no git. Fix: exact file name, keep the old folder, rollback = `compose down` (not `--stop` mid-demo) + `setup_wyse.sh` from the old folder.

## P3

- A-P3-23 · Home `?lang=` checked with `!UI[lang]` (`app/web/index.html:1238`) — use `Object.hasOwn` as judges/scenes do.
- A-P3-24 · A cut-off trace line turns that run into a 500: `result_json` catches only `OSError` (`app/main.py:182-184`); tested with a tiny tmpfs. Catch `ValueError`. Demo logs tmpfs (64 MB) holds ~1,900 runs and is never pruned (adds to A-P3-4).
- A-P3-25 · Emergency words missing: "stuck", "roof", "drowning", "tersekat", "terkepung", "bumbung", "lemas" (`app/router.py` EMERGENCY).
- A-P3-26 · A reading timestamped in the future counts as fresh (`app/agents/data_agent.py:80-85`); treat negative age as unknown with a few minutes' tolerance.
- A-P3-27 · Signs box: footer "River level not available." next to "Last river reading (14 h ago): Warning" reads as a contradiction — "No recent river level."; the box keys on the reason text (`app/view.py:1034,1056`), which also covers missing/rejected readings; rain sign uses the rounded sum (`view.py:1069`) while the rule uses the raw sum.
- A-P3-28 · Staleness limit defined twice (`app/main.py:356` vs `data_agent.py:34`).
- A-P3-29 · `Content-Type: text/plain;application/json` passes the JSON check on `/api/v1/ask` and `/run` (`app/main.py:398`) — concrete form of A-P3-8.
- A-P3-30 · Feedback box has no per-visitor cap: one visitor at the nginx limit fills the 20 MB file in ~5.5 h, then everyone gets 503 (`demo/feedback/feedback.py:42,205`). Check the export daily during judging.
- A-P3-31 · Rate-limit key is the last `X-Forwarded-For` entry (`demo/nginx.conf:24-27`); confirm from outside the tailnet that Funnel appends the real address (DEPLOY_DEMO step 6).
- A-P3-32 · Collector: a failed fetch writes no stamp, so a manual run during `--loop` can call JPS inside 15 min; no lock between two collectors (`app/ingest/jps.py:155-176`). `.dockerignore` misses `data/cache/` and `data/snapshots/` (real JPS pages copied into a locally built image; not published).
- A-P3-33 · `POST /api/v1/ask` takes no `at` time — scene peak moments can't be asked through the API (`app/api.py:152-178`).
- A-P3-34 · Docs: `docs/JUDGES.md:81` says 18 live runs (19 elsewhere); `SECURITY-OPS-CHECKLIST.md:66,96,97` old repo name; `output_examples/` missing newer fields and one outdated line (re-run `scripts/make_examples.py`; verdicts match).
- A-P3-35 · BM times written two ways ("7.30 malam" vs "7:30 malam", `/scenes`); duplicate OpenAPI operation id for `/scenes{tail:path}` (`app/main.py:505`, add `include_in_schema=False`); pyflakes: unused imports `app/scenes.py:20`, `veda/doctor.py:74`, unused `th` `app/view.py:327`; CLI prints raw level enums (`veda/__main__.py:45`).
- A-P3-36 · The tailnet name is in public history (commit a609c55, removed in 94d0edf). The Funnel URL is public by design; re-roll the tailnet DNS name after the hackathon if wanted.
- Deployed demo `8a0b94c` is behind HEAD on `app/web/judges.html` (old repo links, redirect works) — fixed by the redeploy after the P1s.

## Verified good (at 782f449)

- Safety rules: AI raise-only (cited ids, ≥ medium, ≤ 1 level unless a cited fact stands higher, never lowers, never changes "Can't confirm"); band boundaries (equal = at or above); stale > 180 min → "Can't confirm", never a safe verdict; MetMalaysia rule A; signs box from fresh data only, no metres; card always goes out on every Nightshift failure kind; no hard-coded outputs, no fault injection; language chosen by code.
- Demo lockdown: /admin (incl. encoded/case variants), /trace/run/*, /docs, /openapi.json, /redoc → 404; nginx closes the same; /api/openapi.json lists only /v1/*.
- Input caps (500 / 300 chars, 4 KB / 15 KB / 16 KB bodies); cross-site stream 403; path traversal blocked; no user text reaches SQL; all 51 innerHTML sinks escaped; no SSRF, shell, eval, pickle or verify=False; questions never appear on /live/stream.
- Feedback: cross-site 403, 413 on large bodies, PII scrubbed, CSV formula-escaped, no IPs.
- Headers: CSP, nosniff, DENY, no-referrer; nginx adds HSTS + Permissions-Policy. Containers read-only, cap_drop ALL, no-new-privileges, non-root, internal network with no route out, digest-pinned images, proxy on 127.0.0.1 only.
- Secrets: none in tree or history; `.env` ignored and excluded from the image; CI actions SHA-pinned with gitleaks. pip-audit clean; licences MIT/BSD/Apache/PSF + psycopg LGPL-3.0 (disclosed).
- B-104 fallback: no .env 1.1 s, Zetaris refused 0.5 s, Zetaris hanging 10.7 s (< 20 s cap), Nightshift missing → stays live with code-written cards; Postgres down → "cannot reach its river data", no 500.
- Installers: nothing piped from the internet, `.env` never overwritten, server on 127.0.0.1; fresh clone `install.sh --no-start` works offline.
- Accessibility: 0 axe violations; no overflow at 375 px; primary targets ≥ 44 px (known /live toggle 26 px); visible focus; `lang` switches; one H1 per page (answer screen known); levels are colour + icon + word; BM main flow polite and complete except A-P2-25.
- Numbers agree across README, submission.md and judges.html: over 1,000 tests, 47 evals, 6 of 9, 7 scenes.

## PRR gate
arch pass · monitoring pass (/health, traces) · emergency concern (A-P1-17) · capacity pass for judging (watch logs tmpfs + feedback file) · change-mgmt concern (A-P2-28, rollback folders exist on the Wyse) · performance pass · security pass · compliance concern (A-P1-18, B-75).
