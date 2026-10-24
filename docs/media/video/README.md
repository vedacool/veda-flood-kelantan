# Demo video clips

Made by `scripts/record_demo.py` (Playwright, Chromium headless) from VEDA's own web page, at 24 Oct 2026 12:15 MYT from commit
`61ddecd`. 1920x1080 (the page zoomed 1.5x, laid out as on a 1280x720 screen), webm and mp4 (H.264). Slow pacing: about 2 s on each
screen, smooth scrolling, a ring where the recorder taps. The pill at the bottom left of every frame names the data
the clip runs on; it is added by the recorder, not part of VEDA's page.

**Offline recordings (SAMPLE_MODE):** no network, no Zetaris, no Nightshift. So **no clip shows an AI explanation**
(the card is written and checked by code; offline the models are replaced by the agents' code fallbacks), and the
step timings are offline timings (a run takes about 0.1 s). The waiting screen is **held for 4 s by the
recorder** so it can be seen; a live run waits for real (up to 150 s). No JPS reading appears in any clip: every answer
is checked to carry the "Past flood replay" or "Made-up test scene" label, or the clip is dropped.

| Clip | Files | Length | What it shows | Data | Size |
|---|---|---|---|---|---|
| a | `a-replay-rantau-panjang.webm` / `a-replay-rantau-panjang.mp4` | 45 s | Home → tap Rantau Panjang → waiting → answer → Details → How VEDA worked this out | Past flood replay, Nov 2024 (readings reported in the news, cited), 27 Nov 19:30 | 19.5 MB |
| b | `b-live-log-replay-4x.webm` / `b-live-log-replay-4x.mp4` | 105 s | Live log replaying clip (a)'s run at 4× | Past flood replay, Nov 2024, 27 Nov 19:30 (the trace of clip a) | 72.6 MB |
| c | `c-rain-upstream-kota-bharu.webm` / `c-rain-upstream-kota-bharu.mp4` | 33 s | Made-up rain-upstream scene for Kota Bharu: answer + Details | Made-up test scene: SYNTHETIC river levels + real Open-Meteo archive rain, 27 Nov 2024 12:00 | 12.8 MB |
| d | `d-live-log-critic-data-request.webm` / `d-live-log-critic-data-request.mp4` | 70 s | Live log: the Critic asks the Data & Reconciler for a missing upstream reading (Pasir Mas) | Made-up test scene: SYNTHETIC silent upstream gauge, 15 Jun 2024 10:00 | 41.2 MB |
| e | `e-states-normal-cant-confirm.webm` / `e-states-normal-cant-confirm.mp4` | 55 s | Normal for now (Tumpat, calm day), then Can't confirm right now (Tumpat, 26 Nov 18:00) | Made-up test scene (calm day), then Past flood replay, Nov 2024 | 16.7 MB |
| f | `f-emergency.webm` / `f-emergency.mp4` | 28 s | Emergency: from the Can't-confirm answer, and from Home | Past flood replay, Nov 2024, 26 Nov 18:00; the Emergency screen itself uses no data | 4.8 MB |

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

**The video files are not in git** (`.gitignore`: about 167 MB together on 24 Oct, too heavy for the public repo).
They stay in this folder on the recording machine and are uploaded with the submission.
