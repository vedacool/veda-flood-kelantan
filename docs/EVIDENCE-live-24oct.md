# Live reliability - 24 Oct 2026, 12:19-13:14 MYT (build 586d05a)

10 live runs through `POST /run` on this machine (live mode, port 8000): real JPS river levels via the collector,
Open-Meteo / MetMalaysia through Zetaris, Nemotron 3.5 Super VL through Nightshift (lane `deep`, requested by name).
Questions = the web page's town buttons (EN "Is <town> at risk of flooding right now?" / BM "Adakah <town> berisiko
banjir sekarang?"), towns rotating, EN and BM alternating so every town got both. One run every ~6 minutes. No code
change during the runs. Nightshift's VEDA memory was deleted before and after (0 records both times; backups outside
the repo). No screenshots.

**JPS readings:** this summary was built from copies of the 10 traces redacted with `scripts/publish_trace.py`
(B-75: JPS readings are not redistributed); it contains no river levels. The unredacted traces stay in `logs/`
on this machine.

## Rates

| What | Result |
|---|---|
| Runs answered | **10 of 10** (HTTP 200, no error) |
| Path chosen by code | 3 quick (Rantau Panjang: gauges below Alert and steady, data fresh) · 7 full |
| Time | quick 5.5-6.4 s · full **27.6-80.4 s, median 36.1 s** · all within the 150 s budget |
| AI explanation shown (full path) | **6 of 7** (86 %) - 6 of 10 overall; the quick path is code-only by design |
| Critic's AI review done (full path) | **6 of 7** - run 10 had no AI-written text to review (code check only) |
| AI calls | draft 9: 7 answered, 2 failed (`empty response` after ~26 s, one try only) · Critic 6 of 6 answered (4.3-19.2 s) |
| Model that answered | **every successful call: nvidia/nemotron-3.5-super-vl-120b-a12b** (requested by name, lane `deep`) |
| AI fallbacks marked | 2 (runs 3 and 10: "Coordinator: code-only card, explanation dropped") - run 3 then got its explanation on the second draft after the Critic's request |
| Verdicts | Rantau Panjang NORMAL (3) · Pasir Mas / Kota Bharu / Tumpat WATCH (7) - every WATCH set by the B-88 rule `upstream-rain` (heavy rain at Dabong and Kusial); no verdict changed when the Critic's request made it recompute |

## Runs

| # | Start (MYT) | Town | Lang | Path | Total s | Verdict | Explanation shown | Critic AI review | Draft calls | Critic calls | AI fallback | Model that answered | Nightshift receipts |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 12:19 | Rantau Panjang | EN | quick | 6.4 | NORMAL | no | no | - | - | - | - (no AI call) | - |
| 2 | 12:25 | Pasir Mas | BM | full | 80.4 | WATCH | yes | yes | success 19.0 s, success 43.9 s | success 4.6 s | - | nvidia/nemotron-3.5-super-vl-120b-a12b | req_tjh2xcyc, req_4ny9hlmg, req_yddhhr8k |
| 3 | 12:31 | Kota Bharu | EN | full | 62.2 | WATCH | yes | yes | failed 26.1 s, success 18.8 s | success 4.5 s | Coordinator: code-only card, explanation dropped | nvidia/nemotron-3.5-super-vl-120b-a12b | req_ocl7pbcy, req_n0wx6w3e |
| 4 | 12:37 | Tumpat | BM | full | 32.0 | WATCH | yes | yes | success 19.5 s | success 4.3 s | - | nvidia/nemotron-3.5-super-vl-120b-a12b | req_qmrs95iz, req_fcl50v94 |
| 5 | 12:43 | Rantau Panjang | BM | quick | 5.6 | NORMAL | no | no | - | - | - | - (no AI call) | - |
| 6 | 12:49 | Pasir Mas | EN | full | 32.7 | WATCH | yes | yes | success 14.5 s | success 7.4 s | - | nvidia/nemotron-3.5-super-vl-120b-a12b | req_039dyxa0, req_1ulx6cae |
| 7 | 12:55 | Kota Bharu | BM | full | 61.4 | WATCH | yes | yes | success 13.7 s, success 15.5 s | success 19.2 s | - | nvidia/nemotron-3.5-super-vl-120b-a12b | req_6vupn3t9, req_8s2p34nu, req_hqvu1g0w |
| 8 | 13:01 | Tumpat | EN | full | 27.6 | WATCH | yes | yes | success 13.4 s | success 6.4 s | - | nvidia/nemotron-3.5-super-vl-120b-a12b | req_l6pdurk7, req_jx870rvz |
| 9 | 13:07 | Rantau Panjang | EN | quick | 5.5 | NORMAL | no | no | - | - | - | - (no AI call) | - |
| 10 | 13:13 | Pasir Mas | BM | full | 36.1 | WATCH | no | no | failed 25.7 s | - | Coordinator: code-only card, explanation dropped | - (none answered) | - |

Two draft calls in one run (2, 3, 7): the Critic asked the Data & Reconciler for a fresher upstream reading (Kuala
Krai / Kusial readings were ~13 h old), the verdict was recomputed with the new source and the answer redrafted.

## Notes

- **Both failures** were Nightshift returning an empty response after ~26 s on the draft call; the draft makes one
  try (B-85), so the code-checked card went out without the explanation and the fallback was marked in the trace.
- **Upstream gauges ~13 h old** (Kuala Krai, Kusial) in every full run - the JPS feed for those stations, not VEDA;
  the Critic's request found fresh alternatives (Kusial Baru, Air Mulih) in 3 runs.
- Run ids `20261024-121941-0899` ... `20261024-131339-5b87`; redacted copies can be published with
  `python scripts/publish_trace.py logs/trace-<run_id>.jsonl --label live-24oct`.
