# Submission text (B-42)

The text that goes into the HackOS form and the deck. The README is the canonical source for the sponsor technology
explanation and the pre-existing components (the organisers asked for both in the README and the deck, 23 Oct); this
file holds the form description and the short deck versions, and must say the same thing. Every number here is one
the README states with its date. Re-check the counts on the day of each submission.

Last checked against the product: 24 Oct 2026, main at `8f51777` (989 tests, 35 safety scenarios; CI run 40092646506).

## Form fields
| Field | Value |
|---|---|
| Track | Solving Fragmented Intelligence |
| Team | Hujung Lab (auto from HackOS) |
| Description | below (150-2000 characters) |
| Video | link to the 1-4 min demo video (B-53: test it logged out) |
| GitHub Solution | the new public repo (`vedacool/veda-kelantan` suggested, B-77) - never the private `vedacool/veda` |
| Pitch Deck | link or upload |

## Description (1,985 characters including the 6 line breaks - 1,991 if each break counts as 2; limit 2,000; paste as is)
```text
VEDA helps families in Kelantan, Malaysia, decide whether to act on a flood. Ask in English or Bahasa Melayu ("Rantau Panjang selamat ke malam ni?") and VEDA returns one checked answer you can forward on WhatsApp: what to do now, a verdict (Normal, Keep watching, Get ready, Act now or Can't confirm) with the official JPS level and what set it, a comparison with the 2014 flood, every source with its age, what was left out and why, and the 999/991 numbers. It covers 9 places: 4 on Home, 5 more by typing (live); their gauge links await expert review.

The problem is fragmented flood data. JPS river gauges, MetMalaysia warnings, Open-Meteo rain and OpenStreetMap live in different places with no shared station IDs, and one official flood feed has been frozen since Feb 2024 while looking live. On Nov 2024 archive rain, VEDA's rain rule raised Rantau Panjang to Keep watching from 21 Nov (heavy rain on the Thai side of Sg. Golok), five days before the first cited river report (26 Nov) found the river above Warning.

Four agents work in one loop. A Coordinator picks a quick or full path; a Data & Reconciler reads every source through Zetaris, drops stale ones and works around broken gauges; a Forecast agent applies readable rules to the river, upstream gauges, rain upstream and in town, and MetMalaysia rain warnings; and a Critic re-checks the facts in Zetaris, can ask the Data agent for a missing upstream reading, and asks NVIDIA Nemotron (via Meterless Nightshift) whether the explanation contradicts the data. The Meterless World Model is their shared memory, with every fact's source. A safety gate checks every answer last. VEDA also found 20 JPS gauges it had not mapped and proposes where each fits; one is used, as context only, after a person approves.

A live log shows each step; every AI call names the model that answered. Judges can run it offline with no keys (the Nov 2024 replay and labelled made-up scenes); 989 tests and 35 safety scenarios run in CI.
```

## Sponsor technology explanation (deck version; full text: README "Sponsor technology explanation")
- **Zetaris - the one data layer.** Every agent reads data only through `run_sql()`: VEDA's Postgres (gauges and
  JPS thresholds, live JPS levels every 15 min, places, 2014 peaks, replay readings, OpenStreetMap), Zetaris REST
  tables over Open-Meteo (9 rain points, 2 on the Thai side of Sg. Golok) and data.gov.my, and views that join them.
  Every query is in the answer's trace; the Critic re-reads the controlling gauge through Zetaris itself.
- **Meterless World Model - the agents' shared memory.** Every reading, verdict and review with its source and time;
  source health, circuit breakers, the 15-min source memory, and JPS gauges VEDA found but has not mapped yet
  (waiting for a person). Test: the 8 ported Meterless conformance checks + 9 engine tests pass (24 Oct 2026).
- **Meterless Nightshift - the only AI provider.** OpenAI-format calls with app id `veda-deep`, the model asked for
  by name, streamed under a hard time limit; every call's trace line names the model that actually answered and the
  Nightshift receipt; a fallback is marked `ai.fallback`.
- **NVIDIA Nemotron 3.5 Super VL - two jobs.** Writes the 1-2 sentence explanation in the user's language, and is
  the Critic's reviewer (does it contradict, exaggerate or downplay a fact?). Live, 24 Oct 12:19–13:14: 10 of 10
  answered within 150 s; AI explanation in 6 of 7 full-path runs; Critic AI review 6 of 7; every call that answered
  was served by Super VL ([`docs/EVIDENCE-live-24oct.md`](EVIDENCE-live-24oct.md)).
- **What is unique:** the model never decides. Code reads, checks and reconciles the data and sets the verdict with
  rules a person can read; the model explains; a second call checks that explanation against the facts; a safety
  gate checks every answer last; the served model is verified on every call; a replay cuts every source at the
  replay time, so nothing from later leaks in.

## Pre-existing components (deck / form version; full text: README "Pre-existing components")
- The **2014 flood peak table** (`data/historic_peaks.csv`, Dec 2014 rows), compiled before 22 Oct 2026 from the JPS
  2014-2015 highest-level report (as published in USM CGSS slides) and news reports; each row keeps its source URL.
- **Meterless World Model code (Apache-2.0):** `resolve.py` and `stable_ids.py` are Python ports of the Meterless
  reference, and the conformance tests port its runner (attribution in `NOTICE`).
- Design notes summarised in `docs/BUILD_BRIEF.md` (written 20-22 Oct 2026). All other code was written inside the
  build window; the public repo's first commit is 22 Oct 2026 02:22 UTC.
