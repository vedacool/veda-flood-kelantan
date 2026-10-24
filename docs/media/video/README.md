# Demo video clips

Made by `scripts/record_demo.py` (Playwright, Chromium headless) from VEDA's own web page, at 24 Oct 2026 20:51 MYT from commit
`086ea9a`. Two sizes: **375 px** (a phone, 375x812; the mp4 scaled 2x, about 750x1624) and **1440 px** (a desktop,
1440x900: the two-column layout), webm and mp4 (H.264).

**Recording style (the same as the live clips):** a visible pointer (a dark dot with a light ring) glides to each
target and shows a ripple on the click; a typed question appears letter by letter (80 ms a key) with a 2 s pause
before Ask; 1.5 s after every tap; slow smooth scrolling (~300 px/s); about 3 s on the map, the
verdict, WHAT TO DO, the gauge post, the upstream strip and Details; clip (a) switches the answer to BM for 3 s
and back. The pointer and the pill at the bottom left (naming the data the clip runs on) are added by the recorder; they
are not part of VEDA's page.

**Offline recordings (SAMPLE_MODE):** no network, no Zetaris, no Nightshift. So **no clip shows an AI explanation**
(the card is written and checked by code; offline the models are replaced by the agents' code fallbacks), and the
step timings are offline timings (a run takes about 0.1 s). **While each question runs, the recorder slows the
browser's download to 2000 bytes a second**, so the real step lines arrive one by one in "See what VEDA is
doing" (opened right after Ask) and the answer comes in about 10 s; a live run waits for real (up to 150 s). No JPS
reading appears in any clip: every answer is checked to carry the "Past flood replay" or "Made-up test scene" label,
or the clip is dropped.

| Clip | Screen | Files | Length | What it shows | Data | Size |
|---|---|---|---|---|---|---|
| a | 375 px | `a-replay-rantau-panjang-375.webm` / `a-replay-rantau-panjang-375.mp4` | 90 s | Home → the map → tap Rantau Panjang → waiting → answer → Details → How VEDA worked this out | Past flood replay, Nov 2024 (readings reported in the news, cited), 27 Nov 19:30 | 33.3 MB |
| a | 1440 px | `a-replay-rantau-panjang-1440.webm` / `a-replay-rantau-panjang-1440.mp4` | 65 s | Home → the map → tap Rantau Panjang → waiting → answer → Details → How VEDA worked this out | Past flood replay, Nov 2024 (readings reported in the news, cited), 27 Nov 19:30 | 21.2 MB |
| b | 375 px | `b-live-log-replay-4x-375.webm` / `b-live-log-replay-4x-375.mp4` | 89 s | Live log replaying clip (a)'s run at 4× | Past flood replay, Nov 2024, 27 Nov 19:30 (the trace of clip a) | 45.7 MB |
| b | 1440 px | `b-live-log-replay-4x-1440.webm` / `b-live-log-replay-4x-1440.mp4` | 77 s | Live log replaying clip (a)'s run at 4× | Past flood replay, Nov 2024, 27 Nov 19:30 (the trace of clip a) | 42.9 MB |
| c | 375 px | `c-rain-upstream-kota-bharu-375.webm` / `c-rain-upstream-kota-bharu-375.mp4` | 68 s | Made-up rain-upstream scene for Kota Bharu: answer + Details | Made-up test scene: SYNTHETIC river levels + real Open-Meteo archive rain, 27 Nov 2024 12:00 | 21.9 MB |
| c | 1440 px | `c-rain-upstream-kota-bharu-1440.webm` / `c-rain-upstream-kota-bharu-1440.mp4` | 53 s | Made-up rain-upstream scene for Kota Bharu: answer + Details | Made-up test scene: SYNTHETIC river levels + real Open-Meteo archive rain, 27 Nov 2024 12:00 | 14.7 MB |
| d | 375 px | `d-live-log-critic-data-request-375.webm` / `d-live-log-critic-data-request-375.mp4` | 105 s | Live log: the Critic asks the Data & Reconciler for a missing upstream reading (Pasir Mas) | Made-up test scene: SYNTHETIC silent upstream gauge, 15 Jun 2024 10:00 | 56.1 MB |
| d | 1440 px | `d-live-log-critic-data-request-1440.webm` / `d-live-log-critic-data-request-1440.mp4` | 97 s | Live log: the Critic asks the Data & Reconciler for a missing upstream reading (Pasir Mas) | Made-up test scene: SYNTHETIC silent upstream gauge, 15 Jun 2024 10:00 | 52.3 MB |
| e | 375 px | `e-states-normal-cant-confirm-375.webm` / `e-states-normal-cant-confirm-375.mp4` | 72 s | Normal for now (Tumpat, calm day), then Can't confirm right now (Tumpat, 26 Nov 18:00) | Made-up test scene (calm day), then Past flood replay, Nov 2024 | 23.0 MB |
| e | 1440 px | `e-states-normal-cant-confirm-1440.webm` / `e-states-normal-cant-confirm-1440.mp4` | 60 s | Normal for now (Tumpat, calm day), then Can't confirm right now (Tumpat, 26 Nov 18:00) | Made-up test scene (calm day), then Past flood replay, Nov 2024 | 16.9 MB |
| f | 375 px | `f-emergency-375.webm` / `f-emergency-375.mp4` | 34 s | Emergency: from the Can't-confirm answer, and from Home | Past flood replay, Nov 2024, 26 Nov 18:00; the Emergency screen itself uses no data | 12.2 MB |
| f | 1440 px | `f-emergency-1440.webm` / `f-emergency-1440.mp4` | 27 s | Emergency: from the Can't-confirm answer, and from Home | Past flood replay, Nov 2024, 26 Nov 18:00; the Emergency screen itself uses no data | 7.8 MB |

## To re-record live (with the AI explanation) - Session A / Husaini
Live = Zetaris + Nightshift running, Nemotron 3.5 Super VL by name, still on the **Nov 2024 replay** (never live JPS
data; delete Nightshift's VEDA memory records first, as for the 24 Oct screenshots):
- **a** - the answer's "In plain words" (AI explanation) and "How VEDA worked this out" with the served model,
  Nightshift receipt and real seconds; the waiting screen with a real wait.
- **b** - the live log with real "Waiting for Nemotron" bubbles and the two Nightshift calls (draft + Critic review).
- **c**, **d** - optional: the same scenes with the AI explanation (both are made-up scenes, labelled).
- **e**, **f** - no need: Normal (quick path) and Can't confirm use no AI, and Emergency makes no engine call.

## Making the clips again
Dev only (judges do not need this):
```
pip install -r requirements-dev.txt                 # VEDA's requirements + Playwright
python -m playwright install chromium               # the headless browser, once (~120 MB download)
SAMPLE_MODE=true VEDA_PORT=8001 python -m app.main  # in its own terminal (PowerShell: $env:SAMPLE_MODE="true" ...)
python scripts/record_demo.py                        # all clips; --only a,b for some
```
ffmpeg on PATH adds the mp4 copies and the lengths in this table.

**The video files are not in git** (`.gitignore`: too heavy for the public repo; the README table gives each size).
They stay in this folder on the recording machine and are uploaded with the submission.
