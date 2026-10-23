# VEDA — open items

Only two kinds of item live here (Husaini 23 Oct): **open audit findings** and **items waiting on Husaini**. The plan
(what to build, in what order) is the backlog in the private planning folder; IDs `B-xx` / `S-xx` point there.
Status lives here and in the backlog, never in Claude's memory. A finished item is deleted (git keeps the history).

Last updated: 23 Oct 2026 (evening: B-75 - W-8 closed with the organiser ruling; W-7 after the hackathon).

## Open audit findings (audit 2026-10-23, `docs/audit/2026-10-23-audit.md`)
IDs are never reused. Severity: P2 = schedule, P3 = polish. Husaini 23 Oct: all are **after the hackathon** except A-P2-1 and A-P2-3.

| ID | Sev | Finding | Where | Backlog | When |
|---|---|---|---|---|---|
| A-P2-1 | P2 | Two processes writing `world.sqlite` at once (API + CLI live) both fail | `app/engines/world_model/store.py:45` | B-65 | after Gate 1 |
| A-P2-2 | P2 | The whole World Model reloads on every run; facts scan is O(n) (fine today: 0.02 s) | `app/loop.py`, `world.py` | B-65 | after hackathon |
| A-P2-3 | P2 | A stalled Nightshift stream is only cut when the next line arrives (can pass its limit) | `app/adapters/nightshift.py:128` | B-03 | after Gate 1 |
| A-P2-4 | P2 | No backup of `veda-pg` / `world.sqlite`, no restore drill | `scripts/` | B-65 (software-start item 4) | after hackathon |
| A-P2-5 | P2 | `/health` does not check Postgres, the newest reading's age or open circuit breakers | `app/main.py:110` | B-19 | after hackathon |
| A-P2-7 | P2 | Unused model-planning code (`coordinator.plan` and helpers, `nightshift.get_llm`, `loop.STATES`) | `app/agents/coordinator.py` | B-65 | after hackathon |
| A-P2-9 | P2 | `load_dotenv` at import in `app/main.py` leaks the developer's `.env` into the test session | `app/main.py:32` | B-65 | after hackathon |
| A-P3-1 | P3 | Lockfile has no hashes (`--require-hashes`) | `requirements-lock.txt` | B-65 (software-start item 6) | after hackathon |
| A-P3-2 | P3 | No security headers (CSP, nosniff, frame-ancestors) | `app/main.py` | B-19 (software-start item 7) | after hackathon |
| A-P3-3 | P3 | `POST /run` accepts `text/plain`; `GET /run/stream` starts a run (CSRF) | `app/main.py` | B-19 | after hackathon |
| A-P3-4 | P3 | `logs/` and `data/cache/jps/` are never pruned (~3 MB/day) | `logs/` | B-65 | after hackathon |
| A-P3-5 | P3 | Small logic edges: aging reading still labelled "high"; date-only peaks parse to midnight; CLI `--at` not limited to the replay window; "None mm in 24 h" in a trigger reason | `app/agents/forecast_agent.py`, `run.py` | B-16 | after hackathon |
| A-P3-6 | P3 | Router: "Kampung" / "air" / "di" in an English question switch the answer to BM | `app/router.py` | B-21 | after hackathon |

Closed with a decision: **W-8** - organiser ruling on JPS data (23 Oct, human admin): no disqualification; build accurately - credit does not replace consent, recorded copies only if the terms allow redistribution (they don't), so JPS is fetched live at runtime only; SAMPLE_MODE / demo use synthetic or openly licensed data; all third-party data declared in the README. Done in B-75.

Fixed since the audit (deleted from this list): the 10 P1s, BM verdict words + months, card length, masking gaps,
answer language, flipped-comparison check, Critic replay re-check, CI builds the Docker image, `VEDA_FAULTS` removed (A-P2-6), BUILD_BRIEF / CLAUDE.md brought up to date (A-P2-8).

## Waiting on Husaini
| ID | Item | Raised | Recommendation | Backlog |
|---|---|---|---|---|
| W-1 | Dr Ariff's review pack (`docs/review_pack_ariff.md`, sections A-H incl. A5b projection, G3-G5 words + stranded advice, H backup gauges) - Husaini sends it | 22 Oct | send as is; nothing in VEDA waits on it for Gate 1 | B-67 |
| W-2 | Backup gauges for Rantau Panjang / Kota Bharu / Pasir Mas: candidates proposed, not wired until Dr Ariff answers H1-H3 | 23 Oct | wire the first candidate per town after his answer | B-15 |
| W-5 | Meterless: can the ~45-60 s cut-off on Nemotron calls be raised? (affects how often the AI explanation arrives) | 22 Oct | keep asking; VEDA works without it | D-09 |
| W-9 | Nemotron Lightning returns empty answers for the draft (measured 23 Oct 16:57-17:10 MYT: 6 of 6 app runs failed (3 web page, 3 probe), plus 4 raw calls at 1000 / 2000 / 8000 tokens, with and without JSON mode, all `nvidia/nemotron-3.5-lightning-30b-a3b_empty_response` after 17-120 s; a one-line "reply OK" call answered in 2.2 s). The same request worked in 8 of 10 runs at 12:29-13:29. Cards still go out, code-written. Deck screenshots wait for this. **Measured 23 Oct 18:58-19:03 MYT (3 raw draft calls, 8000 tokens, streamed with usage):** 2 answered after 86.1 s / 88.4 s with 146 / 106 characters of text but 6541 / 6181 completion tokens (prompt 1012) - hidden reasoning (no reasoning field in the stream, despite `enable_thinking: false`; the text arrives in one chunk at the end); the 3rd returned `empty_response` after 96.2 s. Earlier successful drafts took 32-60 s, so they now land past VEDA's 60 s cap. VEDA's traces do not record token usage, so it is not known whether the reasoning got longer or the provider slower. **Variants, 23 Oct 20:44-20:57 MYT (3 calls each):** `/no_think` first line 1/3 answered (65 s, 7,724 tokens, 131 chars); current flag 1/3 (137 s, 8,000 tokens, 30 chars); JSON only at 2000 tokens 0/3 (empty after 22-25 s) - none reliable under 60 s, so no default changes. Meterless #help message drafted (enable_thinking ignored? H-MEM off switch?). **Fallback agreed (Husaini 23 Oct): if W-9 is not fixed by Sat 24 Oct 09:30 MYT, the deck and video use the "Recorded live run" traces, labelled as such, and the README states the current behaviour with dates.** **After deleting Nightshift's 18 VEDA memory records (21:37 MYT; no memory attached to these calls):** Lightning draft 3/5 answered, 95-113 s, 5,267-7,582 tokens for 109-124 chars, 2/5 empty after 146-167 s; small Critic 1/5 (27 s, 1,870 tokens), 4/5 empty after 21-56 s -> the memory hypothesis is ruled out. **Super VL requested by name (veda-deep app, deep lane), 3 draft calls:** 3/3 answered, served by nvidia/nemotron-3.5-super-vl-120b-a12b, 23 / 96 / 25 s, 1,622-2,058 tokens, 126-147 chars. Memory regrows at once: the first Super VL answer was stored (veda-deep) and attached to the next two calls | 23 Oct | Husaini 23 Oct: screenshots NOT committed (kept outside the repo). 24 Oct morning, in this order: (1) W-9 retest; (2) the live cut-off question (23 Oct 18:05 it already answered live with the bridge line, but without the AI explanation - W-9); (3) the 27 Nov 19:30 replay screenshots (EN + BM) with the AI explanation, once a test call works. If it still fails, draft a short Meterless #help message for Husaini (no keys, no Console / Providers screenshots) | B-76 |
| W-7 | JPS written consent, **only if VEDA continues after the hackathon** (organiser ruling 23 Oct: credit does not replace consent; until then JPS readings are fetched live at runtime only and never redistributed - B-75) | 23 Oct | email JPS (Bahagian Pengurusan Banjir / Infobanjir) after the hackathon if VEDA continues | - |
