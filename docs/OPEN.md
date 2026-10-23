# VEDA — open items

Only two kinds of item live here (Husaini 23 Oct): **open audit findings** and **items waiting on Husaini**. The plan
(what to build, in what order) is the backlog in the private planning folder; IDs `B-xx` / `S-xx` point there.
Status lives here and in the backlog, never in Claude's memory. A finished item is deleted (git keeps the history).

Last updated: 23 Oct 2026 (evening: B-75 - W-8 closed with the organiser ruling; W-7 after the hackathon).

## Open audit findings (audit 2026-10-23, `docs/audit/2026-10-23-audit.md`)
IDs are never reused. Severity: P2 = schedule, P3 = polish. Husaini 23 Oct: all are **after the hackathon** except A-P2-1 (A-P2-3 fixed in B-85: stalled streams are cut on time).

| ID | Sev | Finding | Where | Backlog | When |
|---|---|---|---|---|---|
| A-P2-1 | P2 | Two processes writing `world.sqlite` at once (API + CLI live) both fail | `app/engines/world_model/store.py:45` | B-65 | after Gate 1 |
| A-P2-2 | P2 | The whole World Model reloads on every run; facts scan is O(n) (fine today: 0.02 s) | `app/loop.py`, `world.py` | B-65 | after hackathon |
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
| W-9 | **Model problem fixed by B-85 (Super VL by name):** 10 live full runs, 23 Oct 22:47-23:07 MYT: explanation shown 8/10, Critic AI review 8/10, every answer within 150 s, every call served by nvidia/nemotron-3.5-super-vl-120b-a12b (Lightning had stopped answering in time that evening; history in DECISIONS and the README). **Still open:** the 27 Nov 19:30 replay screenshots (EN + BM) with the AI explanation - first delete Nightshift's VEDA memory records again (5 regrew during the runs; same backup procedure), then take them. Meterless #help posted by Husaini (enable_thinking on Lightning; H-MEM off switch) | 23 Oct | tomorrow morning: memory deletion -> screenshots -> B-71 | B-76 / B-85 |
| W-7 | JPS written consent, **only if VEDA continues after the hackathon** (organiser ruling 23 Oct: credit does not replace consent; until then JPS readings are fetched live at runtime only and never redistributed - B-75) | 23 Oct | email JPS (Bahagian Pengurusan Banjir / Infobanjir) after the hackathon if VEDA continues | - |
