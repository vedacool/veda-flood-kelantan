# Submission text (B-42)

The text that goes into the HackOS form and the deck. The README is the canonical source for the sponsor technology
explanation and the pre-existing components (the organisers asked for both in the README and the deck, 23 Oct); this
file holds the form description and the short deck versions, and must say the same thing. Every number here is one
the README states with its date. Re-check the counts on the day of each submission.

Last checked against the product: 24 Oct 2026, main at `586d05a` (853 tests, 33 safety scenarios).

## Form fields
| Field | Value |
|---|---|
| Track | Solving Fragmented Intelligence |
| Team | Hujung Lab (auto from HackOS) |
| Description | below (150-2000 characters) |
| Video | link to the 1-4 min demo video (B-53: test it logged out) |
| GitHub Solution | the new public repo (`vedacool/veda-kelantan` suggested, B-77) - never the private `vedacool/veda` |
| Pitch Deck | link or upload |

## Description (1,896 characters including line breaks; limit 2,000; paste as is)
```text
VEDA helps families in Kelantan, Malaysia, decide whether to act on a flood. Ask about a place in English or Bahasa Melayu ("Rantau Panjang selamat ke malam ni? Mak saya tinggal sana.") and VEDA returns one checked answer you can forward on WhatsApp: what to do now, a verdict (Normal, Keep watching, Get ready, Act now, or Can't confirm) with the official JPS level and what set it, how today compares with the 2014 flood, every source with its age, what was left out and why, and the 999/991 emergency numbers.

The problem is fragmented flood data. JPS river gauges, MetMalaysia warnings, Open-Meteo rain and OpenStreetMap live in different places and don't share station IDs, and one official flood feed has been frozen since February 2024 while still looking live. In our November 2024 replay, Rantau Panjang was at Warning while the upstream gauge was at Danger; together they meant Get ready, and the river passed the 2014 peak the next evening.

Four agents work in one loop. A Coordinator picks a quick or full path from the data; a Data & Reconciler reads every source through Zetaris, drops stale ones and works around broken gauges; a Forecast agent applies readable rules to the river, the upstream gauges the rain upstream and in town (including the Thai side of Sg. Golok) and MetMalaysia rain warnings; and a Critic re-checks the facts in Zetaris, can ask the Data agent for a missing upstream reading, and asks NVIDIA Nemotron (through Meterless Nightshift) whether the explanation contradicts the data. The Meterless World Model is the agents' shared memory, with the source of every fact. A safety gate checks every answer last.

A live log shows each step as it happens, and every AI call names the model that answered. Judges can run it offline with no keys (SAMPLE_MODE: the Nov 2024 replay plus clearly labelled made-up scenes); 853 tests and 33 safety scenarios run in CI.
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
  the Critic's reviewer (does it contradict, exaggerate or downplay a fact?). Live, 10 full runs, 23 Oct 2026
  22:47-23:07 MYT: explanation shown 8 of 10, review completed 8 of 10, every call served by Super VL.
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
