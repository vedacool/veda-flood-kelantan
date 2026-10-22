# VEDA — review pack for Dr Ariff
_Prepared 22 Oct 2026 (evening). Everything VEDA currently treats as **"tentative — needs Dr Ariff"**, in one place. Estimated time: **about 1 hour**. Sections are in priority order — if time runs out, A–C matter most._

**How to answer:** for each item write **Yes** (assumption correct) or **Correct to: …** on the answer line (a short note is enough). Husaini or Claude will update the data files and re-seed. The underlying files, if you want to look: `data/stations_mapping.csv` (gauges + links, with map links), `data/rain_points.csv`, `data/historic_peaks.csv`.

Nothing here is used as an official warning; VEDA always says "not an official warning — follow JPS / APM". But these numbers decide what VEDA tells people, so they should be yours, not ours.

---

## A. Verdict rules (D-06) — ~15 min · highest priority
VEDA gives one verdict per place for the next 24–48 h. Current rule set (from the team's research, approved in principle on 22 Oct "with Dr Ariff to check"). "Controlling gauge" = the gauge that represents the place (see C6).

| Verdict | Current rule (any one triggers) |
|---|---|
| NORMAL | controlling gauge below Alert, nothing else triggered |
| WATCH | controlling gauge ≥ Alert · or forecast to reach Alert within 48 h · or an upstream sentinel ≥ Alert · or MET "Waspada" warning for the district |
| PREPARE | controlling gauge ≥ Warning · or forecast to reach Danger in 24–48 h · or upstream sentinel ≥ Danger (e.g. Kuala Krai ≥ 25 m → Pasir Mas / Kota Bharu) · or MET "Buruk/Bahaya" |
| ACT | controlling gauge ≥ Danger · or forecast to reach Danger within 12 h · or an official warning/evacuation order |
| INSUFFICIENT DATA | key data missing or stale (see B) — **never NORMAL when data is missing** |

**A1.** Are the four levels and triggers above right as a starting point?
> Answer: ______

**A2.** "Rising fast" = more than **0.3 m per hour**, or more than **1 m in 6 hours**, at the controlling gauge. Used to move up one level early. Reasonable?
> Answer: ______

**A3.** Step down (e.g. PREPARE → WATCH) only after the level has been **below the threshold and falling for 12–24 h**. Reasonable, and if so 12 h or 24 h?
> Answer: ______

**A4.** Rain-only triggers (when gauges are calm): WATCH if **3-day rain ≥ 100 mm on wet ground**; PREPARE if **3-day ≥ 200 mm or 1-day ≥ 150 mm**; "wet ground" = 7-day rain ≥ 150 mm. Keep, change, or drop for the hackathon?
> Answer: ______

**A5.** (added 22 Oct, B-16) Projections are straight-line from the last 1 h and 3 h, and stop at **24 h**; so the code uses "reaches Alert within 24 h" (WATCH) and "Danger within 24 h" (PREPARE) instead of 48 h. Beyond 24 h only upstream gauges and rain count. OK for the hackathon?
> Answer: ______

**A6.** (added 22 Oct, B-16) **Tidal gauges** are judged on their level only (a rise of a few hours may just be the tide). Marked tidal: Tambatan Diraja, and **Kg Kok Majid (tentative)**. Is Kok Majid tide-influenced? Is **Kuala Jambu** (Sg Golok near its mouth) tide-influenced too?
> Answer: ______

---

## B. Freshness limits — ~5 min
How old a reading may be before VEDA trusts it less. Set by Husaini on 22 Oct as defaults, **tentative**. "Aging" lowers confidence; "stale" means the source is not used (and may lead to INSUFFICIENT DATA).

| Source | Fresh | Aging (lower confidence) | Stale (not used) |
|---|---|---|---|
| JPS river levels | ≤ 1 h | 1–3 h | > 3 h |
| Open-Meteo rain forecast | ≤ 6 h | 6–12 h | > 12 h |
| MET Malaysia warnings | ≤ 12 h | 12–24 h | > 24 h |

Context: today some JPS gauges simply stopped reporting for hours (Kuala Krai last reading 02:00, Kusial 23:30 the night before), so this rule will fire in real life.

**B1.** Are these limits right? (In particular: is 3 h too strict for JPS during a flood, or too loose?)
> Answer: ______

**B2.** (added 22 Oct, B-13) VEDA treats a reading as **broken** (kept, but not trusted) when the level is outside −5…120 m, more than 15 m above the gauge's danger level, or changed more than **3 m in one hour**. Is 3 m/h a sensible "impossible jump" for Kelantan gauges in a big flood (e.g. Kuala Krai, Dec 2014)?
> Answer: ______

---

## C. Gauge network and which gauge represents which town (B-67) — ~20 min
VEDA understands 16 of the 36 Kelantan JPS gauges (all 36 are collected). Order along each river was inferred from district names and coordinates — **please check the order**. Map links for each gauge are in `data/stations_mapping.csv` (column `map_link`).

**C1. Sg Galas arm (upstream → downstream):** Limau Kasturi → Dabong → (joins at) Kuala Krai. Correct?
> Answer: ______

**C2. Sg Lebir arm:** Kg Tualang → Kg Manik Urai → (joins at) Kuala Krai. Correct?
> Answer: ______

**C3. Sg Kelantan main river:** Kuala Krai → Kg Temangan → Kusial Baru → Kusial (Guillemard Bridge) → Air Mulih → Jambatan Tendong → Kg Salor → Tambatan Diraja (Kota Bharu) → Kg Kok Majid (Tumpat). Correct order? Anything missing that matters?
> Answer: ______

**C4. Kg Salor:** JPS lists its sub-river as "Sg. Salor" — is this gauge on the main Sg Kelantan or on a tributary? (If tributary, we drop it from the main chain.)
> Answer: ______

**C5. Sg Golok:** Kg Jenob → Rantau Panjang → Kuala Jambu. Correct? (The Thai side upstream is not in JPS — we state this as a known gap.)
> Answer: ______

**C6. Which gauge represents each town** (controlling gauge, plus an upstream "sentinel" for early warning):

| Town | Controlling gauge | Sentinel(s) |
|---|---|---|
| Pasir Mas (town) | Jambatan Tendong | Air Mulih; further up Kusial, Kuala Krai |
| Rantau Panjang | Rantau Panjang (Sg Golok) | Kg Jenob |
| Kota Bharu | Tambatan Diraja (tide-influenced) | Kg Salor; further up Kusial, Kuala Krai |
| Tumpat | Kg Kok Majid (Kelantan side) and Kuala Jambu (Golok side) | Tambatan Diraja / Rantau Panjang |
| Kuala Krai | Kuala Krai | Dabong (Galas), Kg Tualang / Manik Urai (Lebir) |
| Tanah Merah | Kusial | Kuala Krai |
| Machang | Kg Temangan | Kuala Krai |
| Dabong | Dabong | Limau Kasturi |

Correct? (Pasir Mas town, Rantau Panjang, Kota Bharu and Tumpat are built first, so those four rows matter most.)
> Answer: ______

**C7. "Tangga Krai" = the JPS gauge "Sg. Kelantan di Kuala Krai".** Husaini thinks so; its thresholds today (17 / 20 / 22.5 / 25) match the 2014 "Tangga Krai" row exactly. Confirm?
> Answer: ______

**C8. Missing coordinates:** data.gov.my publishes no location for **Kg Manik Urai, Kg Temangan, Air Mulih, Kg Kok Majid**. Can you give approximate coordinates (or a place to look)? If not, VEDA works without them.
> Answer: ______

---

## D. Travel times between gauges — ~5 min
Stored as ranges, labelled "reported, tentative". From the Dec 2014 flood (team notes and the JPS peak times: Kuala Krai 25 Dec 15:00 → Guillemard and Tambatan Diraja 26 Dec 00:00).

| From → to | Range | Basis |
|---|---|---|
| Kuala Krai → Kusial (Guillemard) | 6–9 h | Dec 2014 |
| Kuala Krai → Tambatan Diraja (Kota Bharu) | 9–17 h | Dec 2014 |
| Dabong → Kuala Krai | ~23 h | single event, low confidence |

All other pairs are empty (unknown).

**D1.** Are these ranges reasonable to use? Should any be widened, or should Dabong → Kuala Krai be dropped?
> Answer: ______

**D2.** Do you know a travel time for **Kg Jenob → Rantau Panjang** (Sg Golok)? Even a rough range helps.
> Answer: ______

---

## E. Rain forecast points — ~5 min
VEDA reads Open-Meteo rain (past 7 + next 7 days) at 7 points: the 5 core gauges (Dabong, Kuala Krai, Kusial, Tambatan Diraja, Rantau Panjang) plus one point on each upstream arm (Limau Kasturi on Sg Galas, Kg Tualang on Sg Lebir). Thai-side Golok rain (e.g. Sukhirin, Waeng) is **not** included yet — stated as a known gap.

**E1.** Are these 7 points a reasonable picture of the rain that matters? Is the missing Thai side acceptable for the hackathon, or should one Thai point be added?
> Answer: ______

---

## F. Data questions found while checking sources — ~10 min
**F1. Kg Jenob 2014 peak date.** The JPS 2014 table prints "1/12/2014 2:00" for Jenob (24.93 m). All other dates in that table are written month/day/year, which would make this 12 Jan 2014 — outside the report period (1 Dec 2014 – 10 Feb 2015). We assume it means **1 Dec 2014**. Correct?
> Answer: ______

**F2. Kg Jenob datum.** On 29 Nov 2024 Malay Mail reported Jenob at **28.99 m** — far above its 2014 peak (24.93 m) and its danger level (23.5 m). Did the gauge datum change, or was Nov 2024 really that much higher at Jenob?
> Answer: ______

**F3. Pasir Puteh thresholds changed.** Sg Semerak at Pasir Puteh: 2014 table 0.40 / 2.00 / 2.30 / 3.00; JPS today 2.0 / 2.5 / 3.0 / 3.2. We use **today's** JPS thresholds. Correct?
> Answer: ______

**F4. Dabong and Kg Tualang thresholds raised since 2014.** Dabong alert/warning 32 / 35 (2014) → 35 / 37 (today); Tualang 27 / 31 → 30 / 34. Danger unchanged. We use **today's** thresholds. Correct?
> Answer: ______

**F5. Kusial "normal" level.** JPS today shows normal 7.0 m; the 2014 table and data.gov.my show 10.0 m (alert/warning/danger 12 / 14 / 16 agree). Only matters for "below normal" wording. Which is right?
> Answer: ______

**F6. Rantau Panjang 2014 peak — sources disagree.** JPS table and NST: **10.84 m**; Kosmo (2023 and 2024 articles): **10.52 m**. VEDA uses the official 10.84 m and shows both. Agree?
> Answer: ______

---
_After your answers: we update the three CSV files, re-run `scripts/seed_stations.py` / `seed_peaks.py`, and change each status from "tentative" to "verified — Dr Ariff, <date>"._
