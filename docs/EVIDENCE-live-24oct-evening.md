# Live test - 24 Oct 2026 evening (monitored)

_Redacted for the repo (B-75): no river readings; changes over 1 h / 3 h are kept._

Live mode, port 8000, HEAD `717d044`; Nightshift's VEDA memory deleted before (0 records; backup outside the repo). Husaini tested from the browser (`/`, `/live`, `/admin`). Monitor: `/health` every 15 s (103 samples, 18:50:33 - 19:16:03 MYT). Built from the 3 traces of this session, `monitor.jsonl` and `server.log`. **The questions are not copied here.**

## Runs

| # | Start (MYT) | Place | Lang | Path | Verdict | Total s | plan | gather | forecast | draft | critique | Served model | AI explanation shown | Critic AI review | Retries | Empty | Fallbacks | Critic decision | Errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 18:51:31 | Rantau Panjang | ms | full | NORMAL | 50.4 | 14.6 | 0.0 | 0.0 | 24.6 | 11.1 | nvidia/nemotron-3.5-super-vl-120b-a12b | yes | yes | 0 | 0 | - | approve: 0 problem(s) | - |
| 2 | 18:54:46 | Rantau Panjang | ms | full | NORMAL | 85.1 | 5.8 | 0.0 | 0.0 | 32.0 | 47.2 | nvidia/nemotron-3.5-super-vl-120b-a12b | no | no | 0 | 0 | Critic: critic code + Zetaris only, AI review unavailable; System: explanation dropped, not reviewed by AI | approve: 0 problem(s) | nightshift.chat |
| 3 | 19:00:25 | not covered (no place recognised) | - | - | - | 0.1 | 0.0 | None | None | None | None | - (no AI call) | no | no | 0 | 0 | - | - | - |

Why the code chose the path: run 1: Sg. Golok di Kg. Jenob (F1) is rising ([rise] in 1 h, [rise] in 3 h) · run 2: Sg. Golok di Kg. Jenob (F1) is rising ([rise] in 1 h, [rise] in 3 h) · run 3: -

## Totals

- **Answered within 150 s: 3 of 3** (all runs answered).
- Time: median **50.4 s**, slowest **85.1 s**; full path 50.4-85.1 s
- **AI explanation shown: 1 of 2 full-path runs**; **Critic AI review done: 1 of 2**.
- Empty model responses: **0**; retries: 0; AI fallbacks: 1.
- Served model: - (no AI call), nvidia/nemotron-3.5-super-vl-120b-a12b.

## Anything broken

- **server.log:** 0 exception / error line(s); 0 HTTP 5xx response(s).
  Requests by path and status: `/` 200: 3, `/health` 200: 107, `/live` 200: 1, `/run/stream` 200: 3, `/trace/recorded` 200: 1, `/trace/run/20261024-185446-7606` 200: 1, `/ui/words` 200: 3.
- **Health:** 0 of 103 samples not ok; Zetaris / Nightshift / Postgres not ok: 0; `/health` took 2090-2275 ms.
- **Circuit breakers opened:** none
- **JPS data age:** newest reading 15-30 min old; stale samples: 0.
- **Failed trace steps:** run 2: nightshift.chat

## The 3 slowest steps

- **45.0 s** - Critic `nightshift.chat` (failed), run 2
- **32.0 s** - Coordinator `nightshift.chat` (success), run 2
- **24.6 s** - Coordinator `nightshift.chat` (success), run 1

JPS collector fetches during the test (not questions): 19:00 27 new readings (jps-live); 19:15 28 new readings (jps-live).

Run ids: 20261024-185131-1184, 20261024-185446-7606, 20261024-190025-d2bf.

## Notes (read from the traces)

- **Run 1 - "sedang turun" while the river had risen (safety, Batch A1):** the approved BM explanation said the river
  at Rantau Panjang was "sedang turun" (falling). The model repeated VEDA's own fact: the card's trend word was
  "turun" because the 1-hour change was -2 cm, while the 3-hour change was +4 cm
  and the answer screen (same two rates, average under 0.5 cm/h) called it steady. Kg. Jenob upstream was rising
  [rise] in 3 h. The code checks and the Critic's AI review both passed it, because it matched the card. Fixed in A1.
- **Run 2 - the Critic's AI review timed out:** the draft took 32.0 s, then the review was cut at its 45 s cap
  (critique 47.2 s, network timeout). As designed, the unreviewed explanation was dropped and the code-checked card
  went out; both fallbacks are marked in the trace.
- **Run 3 - "Pasir Pekan" was not recognised (Batch A6):** the place finder normalised the question to "pasir ...",
  dropping "pekan", so no place matched and no nearest covered town was offered.
- **Plan took 14.6 s in run 1:** the Open-Meteo table had not been refreshed for 513 min, so it was refreshed during
  planning (5.8 s in run 2).
- **After the not-covered answer (run 3)** the background prefetch still ran its Zetaris queries for ~3 s; harmless,
  but unnecessary.
- **`/admin` was not opened** in this session (no request in `server.log`); `/live` and a run's step-by-step view were.
- **Rantau Panjang showed NORMAL, confidence high,** while Kg. Jenob rose [rise] in 3 h - see Batch A3 (report only).
