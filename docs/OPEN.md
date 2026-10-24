# VEDA — open items

Only two kinds of item live here (Husaini 23 Oct): **open audit findings** and **items waiting on Husaini**. The plan
(what to build, in what order) is the backlog in the private planning folder; IDs `B-xx` / `S-xx` point there.
Status lives here and in the backlog, never in Claude's memory. A finished item is deleted (git keeps the history).

Last updated: 24 Oct 2026 (after B-71, B-86, A-P2-7, the new web page, the live log, how-it-worked, admin, the answer states, the accessibility pass, publish_trace and the B-88 rain rule). Tests: **903 pass** (13 skipped: live services). Evals: **33 of 33, ×3 (local pass^3 24 Oct; CI runs them 3 times)** (the Docker job runs them 3 times; 24 Oct 09:04 MYT: job 30 s, green).

## Open audit findings (audit 2026-10-23, `docs/audit/2026-10-23-audit.md`)
IDs are never reused. Severity: P2 = schedule, P3 = polish. Husaini 23 Oct: all are **after the hackathon** except A-P2-1 (A-P2-3 fixed in B-85: stalled streams are cut on time).

| ID | Sev | Finding | Where | Backlog | When |
|---|---|---|---|---|---|
| A-P2-1 | P2 | Two processes writing `world.sqlite` at once (API + CLI live) both fail | `app/engines/world_model/store.py:45` | B-65 | after Gate 1 |
| A-P2-2 | P2 | The whole World Model reloads on every run; facts scan is O(n) (fine today: 0.02 s) | `app/loop.py`, `world.py` | B-65 | after hackathon |
| A-P2-4 | P2 | No backup of `veda-pg` / `world.sqlite`, no restore drill | `scripts/` | B-65 (software-start item 4) | after hackathon |
| A-P2-9 | P2 | `load_dotenv` at import in `app/main.py` leaks the developer's `.env` into the test session | `app/main.py:32` | B-65 | after hackathon |
| A-P3-1 | P3 | Lockfile has no hashes (`--require-hashes`) | `requirements-lock.txt` | B-65 (software-start item 6) | after hackathon |
| A-P3-4 | P3 | `logs/` and `data/cache/jps/` are never pruned (~3 MB/day) | `logs/` | B-65 | after hackathon |

Closed with a decision: **W-8** - organiser ruling on JPS data (23 Oct, human admin): no disqualification; build accurately - credit does not replace consent, recorded copies only if the terms allow redistribution (they don't), so JPS is fetched live at runtime only; SAMPLE_MODE / demo use synthetic or openly licensed data; all third-party data declared in the README. Done in B-75.

Fixed since the audit (deleted from this list): the 10 P1s, BM verdict words + months, card length, masking gaps,
answer language, flipped-comparison check, Critic replay re-check, CI builds the Docker image, `VEDA_FAULTS` removed (A-P2-6), /health checks veda-pg, the newest reading's age and open breakers (A-P2-5, 24 Oct), security headers + no cross-site run (A-P3-2, A-P3-3, 24 Oct: CSP, nosniff, frame-ancestors 'none', no-referrer; POST /run JSON only; /run/stream refuses a request a browser marks cross-site), the answer language from the whole question (A-P3-6, 24 Oct: 'Kampung' / 'air' / 'di' in an English question stay English; a tie follows the page's EN | BM toggle), the small logic edges fixed (A-P3-5, 24 Oct: aging reading never 'high' confidence, date-only peaks known from the end of the day, CLI --at checked like the API, no 'None mm'), the unused model-planning path deleted (A-P2-7, 24 Oct: it would have sent the question to the model), BUILD_BRIEF / CLAUDE.md brought up to date (A-P2-8).

## Waiting on Husaini
| ID | Item | Raised | Recommendation | Backlog |
|---|---|---|---|---|
| W-1 | Dr Ariff's review pack (`docs/review_pack_ariff.md`, sections A-H incl. A5b projection, G3-G5 words + stranded advice, H backup gauges) - Husaini sends it | 22 Oct | send as is; nothing in VEDA waits on it for Gate 1 | B-67 |
| W-2 | Backup gauges for Rantau Panjang / Kota Bharu / Pasir Mas: candidates proposed, not wired until Dr Ariff answers H1-H3 | 23 Oct | wire the first candidate per town after his answer | B-15 |
| W-5 | Meterless: can the ~45-60 s cut-off on Nemotron calls be raised? (affects how often the AI explanation arrives) | 22 Oct | keep asking; VEDA works without it | D-09 |
| W-9 | **Model problem fixed by B-85 (Super VL by name):** 10 live full runs, 23 Oct 22:47-23:07 MYT: explanation shown 8/10, Critic AI review 8/10, every answer within 150 s, every call served by nvidia/nemotron-3.5-super-vl-120b-a12b (Lightning had stopped answering in time that evening; history in DECISIONS and the README). **Still open:** the 27 Nov 19:30 replay screenshots (EN + BM) with the AI explanation - first delete Nightshift's VEDA memory records again (5 regrew during the runs; same backup procedure), then take them. Meterless #help posted by Husaini (enable_thinking on Lightning; H-MEM off switch) | 23 Oct | tomorrow morning: memory deletion -> screenshots -> B-71 | B-76 / B-85 |
| W-10 | Dr Ariff's K2 answers (roles of the 20 discovered gauges): record each as "role confirmed, used after the hackathon" - no code change before the submission; all stay context only | 24 Oct | record his answers here + DECISIONS when they come | B-71 |
| W-7 | JPS written consent, **only if VEDA continues after the hackathon** (organiser ruling 23 Oct: credit does not replace consent; until then JPS readings are fetched live at runtime only and never redistributed - B-75) | 23 Oct | email JPS (Bahagian Pengurusan Banjir / Infobanjir) after the hackathon if VEDA continues | - |
