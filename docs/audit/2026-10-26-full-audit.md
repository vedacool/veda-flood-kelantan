# VEDA audit — 26 Oct 2026 — full sweep at 83aa552 (changes since 0f12eaa, 91 commits)

Profile: web app + API + CLI (FastAPI, Python 3.13) · multi-agent flood-risk advice · public offline demo (Tailscale Funnel, nginx) + local live mode · solo operator.
Dimensions: Security, Functional/Safety, Reliability, Code quality, Deploy/ops, Accessibility/UX, Claims accuracy. Skipped: Compliance (no personal data collected; unchanged), Performance (one run at a time; SSE load checked under Reliability).
Method: clean Linux clone of 83aa552 from a bundle; full suite **1095 passed, 13 skipped**; evals **41/41**; four parallel reviewers with throwaway harnesses (fake Nightshift server, TestClient + uvicorn in demo mode, Playwright at 375/1440 EN/BM, fresh-clone install runs). Every P1 re-verified by reproduction.

**Verdict: GO for submission once the five P1s below are fixed.** No P0.

## P1 — fix before submission
1. **[Reliability] A dropped Nightshift stream crashes the whole run.** `app/adapters/nightshift.py:264` catches only `ConnectionError`/`Timeout`; a connection closed mid-stream raises `requests.exceptions.ChunkedEncodingError`, which escapes Coordinator/Critic and `loop.run` (`loop.py:270`). Repro (fake Nightshift, nov2024 replay, Rantau Panjang): draft ok + Critic drop → run raises; facts-only judgement drop → raises; no `nightshift.chat` trace line. Effect (live only): no answer, no safety gate, no 999/991 advice; `/run/stream` error, `/api/v1/ask` 500. Fix: catch `requests.RequestException` in `_call` → outcome "failed" + trace line; safety net in `loop.run`: any exception from an AI step → code-only card.
2. **[Safety] The B-105 signs box can use a reading VEDA itself rejected.** `app/agents/data_agent.py:456` sets `ctx["last_reading"]` for any reading that fails `_fresh_ok`, including FRESH but unhealthy ones (implausible jump/out of range); `app/view.py:1055-1063` gates on "no fresh, healthy reading". Repro: a 10-min-old reading rejected as implausible → box shows "Last river reading (10 min ago): Danger" + "Treat this as serious"; a rejected Normal + heavy rain → "Last river reading (10 min ago): Normal" (false reassurance from a broken sensor). Fix: only set/show the last reading when it is stale-but-healthy; never from a rejected reading.
3. **[Judge path] Private repo links and a broken `cd`.** `app/web/judges.html:179,188,189,209`, `docs/JUDGES.md:20,29`, `metadata.json:10` point at the private repo (404 for judges). `scripts/public_links.py --apply` rewrites the URLs but not `cd veda` (JUDGES.md 21, 30). Fix at freeze: run the sweep AND clone into a named folder (`git clone … veda`) or fix the `cd`.
4. **[Claims] Form text has old numbers.** `docs/submission.md:8,28` say "989 tests and 35 safety scenarios" (now over 1,000 tests, 41 evals). Use "over 1,000 tests and 41 safety evals".
5. **[UX/judge path] Dead "Tell us" link on scene results when run locally.** `app/web/scenes.html:269` always links `/feedback`, which is 404 without VEDA_DEMO (the offline path judges use). Hide it outside the public demo, as `index.html:1243` does.

## P2
- **[Safety/UX] AI raise on "MetMalaysia warning, no river reading" accepted then dropped** (`critic.py:458`, `forecast_agent.py:317-343`): Details says "Final: Act now", badge says "Get ready". Make `judge` refuse that path (consistent with rain-only lock) or honour `ai_minimum`.
- **[Claims] Trail can say "Sent the answer back" when the Critic approved** (`scenes.py:178` keeps 12 lines per step; trail reads the last review among them). Read the final review.
- **[Safety] Never-into-water regex misses phrasings** (`critic.py:59-82`): "fine to walk … through the flooded lane", "can pass the flooded road", "feel free to enter the floodwater", BM "boleh lalu jalan itu", and "avoid" negating across a clause. AI review mitigates; add patterns + evals.
- **[Reliability] Call budget overrun by first-byte wait** (`nightshift.py:244-246`): stop time set after the POST returns (budget 6 s → 10 s). Start the clock at the attempt.
- **[Reliability] Smart-quoted key crashes start-up instead of falling back** (`UnicodeEncodeError`; `_zetaris_status`, `doctor.zetaris_check`). Catch `Exception`, report type.
- **[Claims] CLI doesn't use the B-104 rule** (`veda/__main__.py:_mode_line`): goes "live" with Zetaris keys only; README says it switches by itself. Reuse `main.offline_reason()`.
- **[Ops] Pre-push docs-only skip bypassable by rename** (`scripts/precommit.py:66,71`): `git mv app/loop.py app/loop.md` → skipped. Use `--no-renames`.
- **[Claims] EVIDENCE/JUDGES numbers behind** (989/35; missing 24 Oct night rows and the planted-error run; "harness not published" is now false). README "41 of 41 in CI at 943441f" — CI there had 40.
- **[UX] "How VEDA worked this out" screen shows raw terms** (SAMPLE_MODE, confidence decimals, "0 problem", duplicate fallback lines) outside "Show technical log".
- **[UX] /live and /sources in BM**: `<html lang>` stays `en`; /live labels "Who is working", "VEDA · live log", "Word for word from the trace (logs/…)" untranslated.

## P3 (log only)
Malformed JSON types → 500 instead of 400 (`api.py:73,75`, `main.py:148`, `scenes.check`) · `/api/docs` Swagger from jsDelivr unpinned, blank offline · `?lang=constructor` breaks a page (`Object.hasOwn`) · outside link `/?place=` starts a run (share feature; accept) · tailnet name in git history (covered by the private history clean) · safety-fix count always "1" in trail · uneven ages ("2.0 h", "-5 min") · "aging" upstream (≤180 min) counted as fresh for signs · "Nemotron judged lower" wording when AI says can't-confirm · empty `/scenes/check` body marks "not NORMAL" ✓ · offline screens say "10 data queries through Zetaris" (replayed) · run id "223209" and "Super" vs "Super VL" on /how-it-works · README CLI sample omits a line · home map label cut at 375 px · ZIP download (no .git): 7 tests need git · feedback footer links to itself · JSON-repair path lacks B-93 fields · missing-token path no trace line · `/health` "ok" after silent fallback · live `/health` can exceed Docker healthcheck timeout · duplicate OpenAPI operation id (`include_in_schema=False`) · trail tied to English progress strings · dead `view.share_text` · logs/snapshots never pruned; demo tmpfs fills after ~1,800 runs · `.dockerignore` lacks data/cache, data/snapshots/jps · doctor writes one stamp file though "read-only" · CLI prints disclaimer twice · feedback container has no healthcheck.

## Verified good
- Demo lock-down (admin, trace, /docs, /redoc, /openapi.json, path tricks) → 404; `/api/openapi.json` lists only v1; no open redirects; body/size/type limits; cross-site `/run/stream` 403.
- Questions never reach /live or the model (incl. the new facts-only call); recorded runs redacted.
- B-104: mode decided once at start; reason never shows key values; outage keeps live. B-104 start with slow Zetaris + down Nightshift → offline in 15.9 s.
- AI judgement end-to-end with mocked Nemotron: lower/uncited/fake-id/low-confidence/malformed ignored; +2 capped at +1; INSUFFICIENT_DATA never changed.
- Safety gate rule 1 + disclaimer on every path; replay has no hindsight across 5 times; API = web answer (EN/BM); all 7 scenes ✓ on real runs.
- Every AI call outcome traced with model/receipt/outcome/fallback (ok, empty, invalid JSON, 500, 504, refused, silent stream, slow first byte).
- JPS outage handling (SSLError/404 → keep last good, retry, no `verify=False`).
- SSE load: 20 watchers cap + 503; 1 run at a time + 429; `/health` 2–3 ms under load.
- Installers/doctor: no key values printed, `.env` never overwritten, no sudo/deletes/downloads, bind 127.0.0.1, idempotent; fresh-clone offline demo works.
- Docker/compose hardening; bundle = git archive + secret check + JPS guard; CI pinned actions, pip-audit, gitleaks.
- UX on every screen 375/1440 EN/BM: no sideways scroll, text ≥16 px, contrast ≥4.5:1, taps ≥44 px, ≤1 filled button, ≤1 feedback link, no console errors (except /api/docs offline), alt text, focus visible.
- Claims checked: test/eval counts, conformance 8/8, 15 peak rows, first commit 22 Oct 02:22 UTC, 19 traces, Cursor log counts, JUDGES "try these" rows, internal links, no real tailnet host in the tree.
