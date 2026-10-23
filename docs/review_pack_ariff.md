# VEDA — review pack for Dr Ariff

> **Start here (5 lines)**
> 1. **What VEDA is:** a helper that answers "is my place in Kelantan at risk of flooding in the next day or two, and what should we do?" in BM or English, using JPS river gauges, rain forecasts and MetMalaysia warnings.
> 2. **What you are checking:** the flood rules and numbers a person must sign off - which gauge speaks for which town, when a level means WATCH / PREPARE / ACT, how old a reading may be, what VEDA tells people to do.
> 3. **How to reply:** under each item write its ID and your answer - "A3: OK", or "A3: change to …", or "A3: ?" if you are unsure. A short note is enough.
> 4. **Order:** A, G, K first; then B to I. J is parked (no answer needed).
> 5. **Deadline:** Saturday 24 Oct, night.

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

**A5b.** (added 23 Oct, Husaini) **The straight-line projection itself - rising and falling cases.**
- *Falling:* on 23 Oct Pasir Mas ([JPS reading], falling) was projected to a range reaching about -2.3 m - a level below the river bed. VEDA
  now shows **"turun / falling - no level projected"** when both trends point down, and any range shown is **never
  below the gauge's lowest level in the past 7 days**.
- *Rising:* a steep rise overshoots (replay 27 Nov 19:30: 13.75-14.54 m projected, the real peak was ~11.4 m; see A5).
  Should a rising projection be capped (e.g. at the record peak + a margin), shortened (12 h), or shown only as
  "rising - may reach Danger in about X h"?
- *Since 23 Oct (Husaini, built):* the card shows a number range **only while the projected range stays below
  Danger**. A range that reaches Danger is shown as words only: **"dijangka melepasi paras Bahaya" / "expected to pass
  Danger"** (e.g. SYNTHETIC rising scene, Rantau Panjang: 8.1 m now, a straight line gave 14.03-14.1 m - now words).
  The straight-line method itself (A5) still needs your view.
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
## G. What VEDA tells people to do — ~10 min (added 22 Oct night, B-21)
Every answer starts with one fixed advice line for its verdict, written by code (never by the AI), in BM and English. Text set by Husaini on 22 Oct night, **tentative**.

| Verdict | English | Bahasa Melayu |
|---|---|---|
| NORMAL | No action needed. Keep an eye on JPS updates. | Tiada tindakan diperlukan. Terus pantau maklumat terkini JPS. |
| WATCH | Check again in 3 hours. Get important documents, medicines and a charged phone / power bank ready. | Semak semula dalam 3 jam. Sediakan dokumen penting, ubat-ubatan dan telefon yang dicas / power bank. |
| PREPARE | Pack an emergency bag. Move valuables and your vehicle to higher ground. Find your nearest PPS (ask the village head / JKKK). Check on elderly or sick neighbours. | Sediakan beg kecemasan. Alihkan barang berharga dan kenderaan ke tempat tinggi. Kenal pasti PPS terdekat (tanya ketua kampung / JKKK). Bantu jiran warga emas atau yang sakit. |
| ACT | Follow APM / police instructions and go to the PPS if told. Switch off the main power. Never walk or drive through floodwater. If trapped: stay on high ground, save phone battery, call 999 / 991. | Ikut arahan APM / polis dan pergi ke PPS jika diarahkan. Matikan suis utama elektrik. Jangan meredah air banjir, sama ada berjalan kaki atau memandu. Jika terkandas: kekal di tempat tinggi, jimatkan bateri telefon, hubungi 999 / 991. |
| INSUFFICIENT DATA | VEDA cannot confirm the river level right now. Check JPS Infobanjir; call 999 if you are in danger. | VEDA tidak dapat mengesahkan paras sungai sekarang. Semak JPS Infobanjir; hubungi 999 jika anda dalam bahaya. |

**G1.** Is each advice line right for its level, and safe? Anything missing (e.g. children, medicine, pets, documents in plastic bags)?
> Answer: ______

**G2.** "Check again in 3 hours" for WATCH — the right interval?
> Answer: ______

**G3.** (added 23 Oct) The verdict in BM cards: NORMAL / **BERJAGA-JAGA** (WATCH) / **BERSEDIA** (PREPARE) / **BERTINDAK** (ACT) / **DATA TIDAK MENCUKUPI**. We avoided Waspada / Amaran / Bahaya because those are JPS's own level names, shown next to the verdict ("BERSEDIA - paras JPS Amaran"). Clear for residents?
> Answer: ______

**G4.** (added 23 Oct) VEDA's code rejects an AI explanation in BM that contains these **Indonesian words** (then the
AI rewrites it once; if it still fails, the card goes out without the explanation): *alarm, aturan, kondisi, terpicu,
bisa, mengungsi, pengungsian, siaga, rumah sakit, ponsel, kabupaten, banget, telepon, tingkat air* (the phrase - BM says *paras air*; *tingkat* alone is fine). Deliberately **not** on the list: *aman*
(normal BM), *sehingga* (normal BM for "until") and *Waspada* (a JPS level name). Anything to add or remove?
> Answer: ______

**G5.** (added 23 Oct, Husaini) **Someone says they are trapped / stranded** (terkandas, terperangkap, tak boleh
keluar, air keliling rumah, trapped, stranded ...). VEDA then puts safety first, whatever the river data says:
1. "Anda terkandas: utamakan keselamatan." / "You said you're stranded: safety first."
2. The ACT advice (as in the table above, ending "Jika terkandas: kekal di tempat tinggi, jimatkan bateri telefon,
   hubungi 999 / 991").
3. The river verdict as usual; when it is NORMAL, also: "Paras sungai normal, tetapi banjir setempat masih boleh
   memerangkap anda." / "River level is normal, but local flooding can still trap you."
Without a place name, VEDA gives 1 and 2, then asks for the place. Is this the right advice for someone already
trapped? Anything to add (e.g. a rescue number other than 999 / 991, or "go to the highest floor / roof")?
> Answer: ______

---

## H. Backup gauges for Rantau Panjang, Kota Bharu and Pasir Mas — ~10 min (added 23 Oct, B-15)
When a town's controlling gauge goes silent, VEDA can use a **backup gauge** at medium confidence. Today only
Guillemard (Kusial) has one (Kusial Baru, 738 m away, verified). For the three towns below VEDA has **no backup**, so a
silent gauge means "last reading for context only" and **INSUFFICIENT DATA**. These are the candidates from our own
gauge chain: the nearest gauge on the same river, up and down. Kok Majid (downstream of Kota Bharu) is left out: it is
tide-influenced (Husaini 23 Oct). **Tentative, and not used by VEDA until you answer.**

A backup gauge would never be compared in metres with the town's thresholds (datums differ). VEDA would use the
backup's **own JPS band** (Normal / Alert / Warning / Danger) and its trend, and say so on the card.

| Town (controlling gauge) | Candidate | River, position | Straight-line distance | Travel time (lag) | Notes |
|---|---|---|---|---|---|
| Rantau Panjang (Sg. Golok di Rantau Panjang, `_DPMS0003`, Alert 7 / Danger 9 m) | **H-RP1** Sg. Golok di Kg. Jenob (`_DTMH0008`) | Golok, upstream | 23.5 km | unknown | Already its upstream sentinel. Alert 21.5 / Danger 23.5 m (different datum). Upstream: rises first, so it warns early but may over-state the town |
| | **H-RP2** Sg. Golok di Kuala Jambu (`_DPMS0008`) | Golok, downstream | 19.1 km | unknown | Controls Tumpat (Golok side). Alert 2 / Danger 3 m. Near the mouth, may be tidal (see A6) |
| Kota Bharu (Sg. Kelantan di Tambatan D'Raja, `_DKBR0007`, tide-influenced) | **H-KB1** Sg. Kelantan di Kg. Salor (`_DKBR0002`) | Kelantan, upstream | 10.9 km | unknown (Kuala Krai → Tambatan is 9–17 h, D) | Already its sentinel. Tide effect not known to us. Alert 9 / Danger 10.6 m |
| Pasir Mas (Sg. Kelantan di Jambatan Tendong, `27133`) | **H-PM1** Sg. Kelantan di Kg. Salor (`_DKBR0002`) | Kelantan, downstream | 2.1 km | unknown (probably < 1 h) | Very close; also Kota Bharu's sentinel |
| | **H-PM2** Sg. Kelantan di Air Mulih (`6021065_DPMS0001`) | Kelantan, upstream | no coordinates on file | unknown | Already Pasir Mas's sentinel. Alert 9 / Danger 10.65 m |

**H1.** For each town, which candidate (if any) should VEDA use as its backup, and in which order?
> Answer: ______

**H2.** Is the **band** of the backup gauge a fair stand-in for the town (e.g. Salor at Alert ≈ Pasir Mas at Alert)? Or should a backup only lower confidence, never give the verdict?
> Answer: ______

**H3.** Any travel times you know for Jenob → Rantau Panjang, Salor → Tambatan D'Raja, Air Mulih → Tendong?
> Answer: ______

## I. Bridges and "will my road be cut off?" — ~10 min (added 23 Oct, B-73)

Since 23 Oct, a question such as "jalan ke Rantau Panjang terputus ke?" gets **facts only** from OpenStreetMap: each
road bridge within 10 km that crosses a named river, its distance, and the JPS level at the nearest JPS gauge on that
river (only a gauge within 10 km of the bridge, only a fresh reading). Example: *"Jambatan X merentasi Sg Golok
(2.1 km); paras sungai di situ: Bahaya."* plus *"Kawasan rendah tidak dinilai."* VEDA says nothing about whether the
road will be cut off. Husaini 23 Oct: no "boleh terputus" / "may be cut off" until you approve a rule.

**Proposed rule (TENTATIVE - not built):** when the nearest JPS gauge on the bridge's river (within 10 km) is at
**Warning or above**, the bridge line adds *"jalan di sini boleh terputus - jangan merentas jika air di atas jalan"* /
*"this crossing may be cut off - never cross water over the road"*. At Alert: no extra words.

**I1.** Is "Warning or above at the nearest gauge on the same river" a fair trigger for "may be cut off"? Or Danger
only? Or should a bridge never get a prediction, only the level?
> Answer: ______

**I2.** Is 10 km between the bridge and the gauge too far for "paras sungai di situ" (river level there)? Should the
line name the gauge and its distance instead (e.g. "stesen Rantau Panjang, 0.5 km: Bahaya")?
> Answer: ______

**I3.** Low-lying roads away from rivers (e.g. roads that flood from rain or backwater) are not assessed (no
elevation data). Is the line "Kawasan rendah tidak dinilai" enough, or should VEDA point to a source (JKR road
closure notices)?
> Answer: ______

---

_After your answers: we update the three CSV files, re-run `scripts/seed_stations.py` / `seed_peaks.py`, and change each status from "tentative" to "verified — Dr Ariff, <date>"._


## K. Gauges VEDA asks for or finds by itself (B-71) — ~10 min (added 24 Oct)

**K1.** When the gauge upstream of a town has no fresh reading, VEDA's checker (the Critic) asks the data part of
VEDA for another fresh gauge **further up the same river**. It never replaces the town's own gauge. If one is found,
the risk level is worked out again with the same rules. Example (made-up test scene): Pasir Mas - the upstream gauge
at Kuala Krai is silent -> the data part finds Kg. Temangan at Warning (Amaran) -> Pasir Mas goes from NORMAL to
WATCH. If nothing fresh is found, the answer says which gauge is missing. Is this acceptable?
> Reply: OK, or your correction: ______

**K2.** JPS publishes 20 Kelantan gauges that VEDA does not use yet. VEDA notices them on every question and lists
them as "discovered"; it never uses one unless a person approves it, and then only as extra information on the answer,
never in the risk level. Please give each a **Role**: *town gauge* (speaks for a town), *upstream warning* (an early
sign for a town downstream - say which), or *context only*. Until you fill this in, **all stay context only**.
"Nearest town" = a town VEDA covers in the same district (— = none).

| Key | Station name | River | District | Nearest town | Role |
|---|---|---|---|---|---|
| _DPMS0419 | Empangan Bukit Kwong (F1) | Sg. Golok | Pasir Mas | Pasir Mas | |
| _DGMG0023 | Sg. Aring di Jalan Felda Aring (F1) | Sg. Lebir | Gua Musang | — | |
| 26292 | Sg. Buaya Ikat di Kg. Pulau Lima (F2) | Sg. Buaya Ikat | Pasir Puteh | — | |
| _DGMG0045 | Sg. Galas di Kg. Lembaga (F1) | Sg. Galas | Gua Musang | — | |
| _DGMG0014 | Sg. Galas di Kg. Pulai (F1) | Sg. Galas | Gua Musang | — | |
| _DKBR0010 | Sg. Kelantan di Kuala Besar (F1) | Sg. Kelantan | Kota Bharu | Kota Bharu | |
| _DJLI0011 | Sg. Lanas di Air Lanas (F1) | Sg. Lanas | Jeli | — | |
| _DKKI0082 | Sg. Lebir di Kg. Karangan (F1) | Sg. Lebir | Kuala Krai | — | |
| 4824001_DGMG0021 | Sg. Lebir di Kuala Koh (F1) | Sg. Lebir | Gua Musang | — | |
| 26296 | Sg. Melor di Jambatan Melor (F2) | Sg. Melor | Bachok | — | |
| _DKKI0015 | Sg. Nal di Kg. Sungai Nal (F1) | Sg. Nal | Kuala Krai | — | |
| _DGMG0002 | Sg. Nenggiri di Belatop (F1) | Sg. Nenggiri | Gua Musang | — | |
| _DGMG0011 | Sg. Nenggiri di Bertam (F1) | Sg. Nenggiri | Gua Musang | — | |
| _DKKI0109 | Sg. Pahi di Kg. Pahi (F1) | Sg. Lebir | Kuala Krai | — | |
| _DJLI0002 | Sg. Pergau di Air Bol (F1) | Sg. Pergau | Jeli | — | |
| _DJLI0005 | Sg. Pergau di Jambatan Jerimbong, Kuala Balah (F1) | Sg. Pergau | Jeli | — | |
| _DJLI0007 | Sg. Pergau di Kg. Lawar (F1) | Sg. Pergau | Jeli | — | |
| _DPPH0001 | Sg. Semerak di Pasir Puteh (F1) | Sg. Semerak | Pasir Puteh | — | |
| 26289 | Sg. Semerak di Tok Bali (F2) | Sg. Semerak | Pasir Puteh | — | |
| _DTMH0004 | Sg. Sokor di Kg. Sokor (F1) | Sg. Kelantan | Tanah Merah | — | |

> Reply: OK, or your correction (fill the Role column, or write e.g. "_DKBR0010: upstream warning for Kota Bharu"): ______

## J. Ground height (B-74, PARKED until after the hackathon - for later, no answer needed now)

Idea: a ground height per place from an open elevation model (Copernicus DEM GLO-90 via Open-Meteo, CC BY 4.0), as
context only, never changing a verdict. Parked (Husaini 23 Oct): JPS river readings are measured against each
gauge's own reference point, not sea level, so a ground height on the same card invites a wrong comparison ("the
river is 9 m, my house is 5 m up"). If it comes back later, it needs a **no-comparison rule**: VEDA never puts a river
level and a ground height in one sentence, and a code check rejects any text that compares them.

**J1 (later).** Do the JPS gauges in Kelantan have published datum heights (gauge zero above sea level) that would make
a correct comparison possible?
> Answer: ______
---

## Sunday recording checklist (video / demo) - for Husaini, not Dr Ariff
1. **Delete Nightshift's VEDA memory records right before recording** (Husaini 23 Oct): Nightshift keeps model
   answers per app and re-sends them into new prompts. Close Nightshift (both `meterless*` processes), back up
   `%LOCALAPPDATA%\ai.meterless.runtime\state\engine-kv.json` outside the repo, remove the records whose namespace
   starts with `veda` from `rt-hmemKnowledge.v1`, start Nightshift again, check 0 VEDA records. Every answered call
   adds records again, so do this last before pressing record.
2. *(next steps to be added with Cowork)*
