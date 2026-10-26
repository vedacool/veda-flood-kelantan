# Submission text (B-42)

The text that goes into the HackOS form and the deck. The README is the canonical source for the sponsor technology
explanation and the pre-existing components (the organisers asked for both in the README and the deck, 23 Oct); this
file holds the form description and the short deck versions, and must say the same thing. Every number here is one
the README states with its date. Re-check the counts on the day of each submission.

Last checked against the product: 26 Oct 2026, main at `8dd5f8f` (over 1,000 tests and 47 safety evals; CI run 40278716334 at `12be2da`, only docs changed since).

## Form fields
| Field | Value |
|---|---|
| Track | Solving Fragmented Intelligence |
| Team | Hujung Lab (auto from HackOS) |
| Description | below (150-2000 characters) |
| Video | link to the 1-4 min demo video (B-53: test it logged out) |
| GitHub Solution | the public repo https://github.com/vedacool/veda-flood-kelantan (B-77) - never the private `vedacool/veda` |
| Pitch Deck | link or upload |

## Description (1,927 characters including the 8 line breaks - 1,935 if each break counts as 2; limit 2,000; paste as is)
```text
VEDA helps families in Kelantan, Malaysia, decide whether to act on a flood. Ask in English or Bahasa Melayu ("Rantau Panjang selamat ke malam ni?") and get one checked answer you can forward on WhatsApp: what to do now, a level (Normal, Keep watching, Get ready, Act now or Can't confirm) set from official JPS marks, a comparison with the 2014 flood, every source with its age, what was left out and why, and 999/991.

The problem is fragmented flood data: JPS river gauges, MetMalaysia warnings, Open-Meteo rain and OpenStreetMap sit in different places with no shared station IDs, and one official flood feed has been frozen since Feb 2024 while looking live. No single source tells a family what to do.

Separate agents check each other. A Coordinator picks a quick or full path; a Data & Reconciler reads every source through Zetaris, drops stale ones and works around silent gauges; a Forecast agent applies readable rules to the river, upstream gauges, rain and warnings; a Critic re-checks the facts in Zetaris, can ask the Data agent for a missing upstream reading, and has NVIDIA Nemotron 3.5 Super VL (via Meterless Nightshift) review the answer. Nemotron may raise the level only when it cites real facts, never lower it. The Meterless World Model is their shared memory; a safety gate checks every answer last. VEDA also found 20 JPS gauges it had not mapped and waits for a person to approve each.

It fails honestly. When the JPS site went down on 24 Oct, VEDA kept the last good data, said "Can't confirm" instead of guessing, and still showed the warning signs it could trust.

Judges can check it themselves: a public demo with the Nov 2024 replay, 7 test scenes that show the data and the expected answer before you run them, a public API, a live log where every AI call names the model that answered, and a one-command install that runs offline with no keys. Over 1,000 tests and 47 safety evals run in CI.
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
- **NVIDIA Nemotron 3.5 Super VL - three jobs.** Writes the 1-2 sentence explanation in the user's language; is
  the Critic's AI reviewer (does the explanation contradict, exaggerate or downplay a fact?); and gives its own
  judgement of the level, citing up to 2 facts. VEDA uses that judgement only to RAISE the level - cited real
  facts, at least medium confidence, at most one level (unless a cited fact itself stands higher) - never to lower
  it, and it never changes "Can't confirm". Live, 24 Oct night: Nemotron judged 6 of 9 runs and agreed every
  time; when the explanation call timed out, a facts-only judgement took over
  ([`docs/EVIDENCE-live-24oct-night.md`](EVIDENCE-live-24oct-night.md)).
- **What is unique:** the rules set a safe floor and the model can only raise it, citing facts. Code reads, checks
  and reconciles the data and sets the verdict with rules a person can read; the model explains; a second call
  checks that explanation against the facts; a safety gate checks every answer last; the served model is verified
  on every call; a replay cuts every source at the replay time, so nothing from later leaks in.

## Pre-existing components (deck / form version; full text: README "Pre-existing components")
- **The historic flood peak table** - all of `data/historic_peaks.csv` (15 rows) - was **compiled before 22 Oct
  2026**. Each row's source: **8 rows** - the Dec 2014 peaks from JPS "Laporan Catatan Aras Air Tertinggi 01-12-2014
  to 10-02-2015" (as published in USM CGSS slides); **2 Kosmo rows** (27 Nov 2024): the Dec 2014 peak as Kosmo
  reported it, and a Nov 2024 reading (27 Nov, 7:30 pm); **3 Malay Mail rows** (29 Nov 2024): Nov 2024 peaks; **2 NST
  rows**: the Nov 2024 peak (29 Nov 2024, citing JPS) and the Dec 2023 peak (26 Dec 2023). Every row keeps its source
  and URL; the sources are listed under **Data sources and licences**.
- **Meterless World Model code (Apache-2.0):** `resolve.py` and `stable_ids.py` are Python ports of the Meterless
  reference, and the conformance tests port its runner (attribution in `NOTICE`).
- Design notes summarised in `docs/BUILD_BRIEF.md` (written 20-22 Oct 2026). All other code was written inside the
  build window; the public repo's first commit is 22 Oct 2026 02:22 UTC.
- The `jps2014_*` columns of `data/stations_mapping.csv` come from the same pre-existing 2014 compilation. The other
  data tables were built inside the window from public sources (data.gov.my, JPS publicinfobanjir, Open-Meteo /
  GeoNames, OpenStreetMap, cited news reports) - list in the README.
