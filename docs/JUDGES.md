# Try VEDA in 10 minutes

VEDA answers one question for families in Kelantan, Malaysia: *is my place at risk of flooding, and what should we do
now?* This page runs it **offline** on your own computer: no keys, no accounts, no Zetaris, no Nightshift, **no Docker
needed**. Offline (SAMPLE_MODE) runs VEDA's real agents and rules on recorded scenes: the November 2024 flood replay
(river readings reported in the news, each cited) or a made-up test scene (labelled on every answer).

**Coverage:** 9 places. The 4 on the Home screen (Rantau Panjang, Pasir Mas, Kota Bharu, Tumpat) work offline and
live; 5 more work by typing their name in live mode (Kuala Krai, Tanah Merah, Dabong, Wakaf Bharu, Pasir Pekan). Which
JPS gauges each place reads is tentative for all 9 until Dr Ariff (our hydrology reviewer) checks them. Any other
Kelantan place gets "not covered yet" and a button for the nearest covered place.

## 1. Start it (about 3 minutes)
You need **Python 3.11 or newer (3.13 recommended)** and **git**. (Tested 24 Oct 2026 on Windows with Python 3.11,
3.12 and 3.13: install, the tests - 853 then - the safety scenarios and every row below. At `0ed62be` (26 Oct): over 1,000 tests and
47 safety evals, run by CI on Python 3.13.) In a terminal:

**Windows (PowerShell)**
```
git clone https://github.com/vedacool/veda-kelantan.git veda
cd veda
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:SAMPLE_MODE="true"; .venv\Scripts\python -m app.main
```

**macOS / Linux**
```
git clone https://github.com/vedacool/veda-kelantan.git veda
cd veda
python3 -m venv .venv          # python3 --version must say 3.11 or newer
.venv/bin/python -m pip install -r requirements.txt
SAMPLE_MODE=true .venv/bin/python -m app.main
```

Leave it running and open **http://127.0.0.1:8000**. (Port 8000 taken? Start it with `VEDA_PORT=8001` as well -
PowerShell: `$env:VEDA_PORT="8001"` - and use 8001 in the links below.) Prefer Docker? `docker build -t veda .` then
`docker run --rm -p 8000:8000 -e SAMPLE_MODE=true veda`.

## 2. Try these (about 5 minutes)
Each link opens the page on one scene; then tap the town named. A grey label above the answer always says which data
it used: **Replay · 27 Nov 2024, 7:30 pm · Change** (the moment of the past flood replay) or **Made-up test scene ·
<scene>**. In the Nov 2024 replay only Rantau Panjang has cited river readings all evening; the other towns honestly
show **Can't confirm**.

| Try | Open, then tap | What you should see |
|---|---|---|
| The real Nov 2024 flood at its worst | [127.0.0.1:8000/?replay=nov2024&at=2024-11-27%2019:30](http://127.0.0.1:8000/?replay=nov2024&at=2024-11-27%2019:30) → **Rantau Panjang** | Red **Act now**: "The river is 1.94 m above the danger level and still rising", what to do now, the river 10.94 m at 19:30 (reported in the news). Tap **Details** for why, the level bar and every source with its age (and what was left out, and why) |
| A calm day | [127.0.0.1:8000/?replay=synthetic_calm&at=2024-06-15%2010:00](http://127.0.0.1:8000/?replay=synthetic_calm&at=2024-06-15%2010:00) → **Tumpat** | Green **Normal for now** (a made-up calm river) |
| Rain, not the river, raises the alarm | [127.0.0.1:8000/?replay=synthetic_upstream_rain&at=2024-11-27%2012:00](http://127.0.0.1:8000/?replay=synthetic_upstream_rain&at=2024-11-27%2012:00) → **Kota Bharu** | Orange **Get ready** while the river itself is Normal: heavy real archive rain upstream (Kuala Krai, may reach Kota Bharu in 9-17 h) while it rains hard in town |
| A broken source | [127.0.0.1:8000/?replay=nov2024&at=2024-11-27%2008:00](http://127.0.0.1:8000/?replay=nov2024&at=2024-11-27%2008:00) → **Rantau Panjang** | Grey **Can't confirm right now** and the **I'm stranded / in danger** button: the last verified reading is 14 h old, so VEDA will not guess (never "Normal" on missing data) |
| How the agents worked it out | on any answer: **Details** → **See how VEDA worked this out** | One row per step: which agent, seconds, how many Zetaris queries, word-for-word outputs; steps without AI say "Code only". Offline the AI steps (writing and checking the answer) show an amber fallback line, because no model is called |
| The agents talking, step by step | from that screen: **Replay these steps live** (or open [127.0.0.1:8000/live](http://127.0.0.1:8000/live) in a second tab *before* tapping a town) | The live log: every trace line as a chat bubble, who is working, the Critic's checks |
| The Critic asking for more data | [127.0.0.1:8000/?replay=synthetic_silent_upstream&at=2024-06-15%2010:00](http://127.0.0.1:8000/?replay=synthetic_silent_upstream&at=2024-06-15%2010:00) → **Pasir Mas**, then Details → See how VEDA worked this out → Replay these steps live | Blue **request** bubbles: the Critic asks the Data & Reconciler for a missing upstream reading, it finds Kg. Temangan, and the verdict is recomputed from Normal to **Keep watching** |
| A place VEDA does not cover | on any page above, type `Is Bachok safe?` in **Or type a question** → **Ask** | "Not covered yet", the covered places, and a big **Check Kota Bharu (20 km away)** button that asks about the nearest covered town |
| Bahasa Melayu | tap **BM** at the top right (or add `&lang=ms` to any link) | The whole page and the answer in Malay; tap **EN** to go back |

No browser? The same agents answer on the command line and over HTTP. In a **second** terminal, in the `veda` folder:

**Windows (PowerShell)**
```
$env:SAMPLE_MODE="true"; .venv\Scripts\python run.py --replay nov2024 --at "2024-11-27 19:30" "Rantau Panjang selamat ke?"
curl.exe -X POST http://127.0.0.1:8000/run -H "Content-Type: application/json" -d "@input_examples/02_rising_river_act.json"
```
**macOS / Linux**
```
SAMPLE_MODE=true .venv/bin/python run.py --replay nov2024 --at "2024-11-27 19:30" "Rantau Panjang selamat ke?"
curl -X POST http://127.0.0.1:8000/run -H "Content-Type: application/json" -d @input_examples/02_rising_river_act.json
```
Six ready-made inputs are in `input_examples/`, with VEDA's real answers and traces in `output_examples/`.

## 3. Where to see the agents (about 2 minutes)
- **How it works** ([127.0.0.1:8000/how-it-works](http://127.0.0.1:8000/how-it-works), in the top bar of every page;
  /judges redirects to it): the agents (the four agents, Zetaris, Nemotron through Nightshift, the World Model - and what each one
  decides), then the 19 recorded live runs (23-24 Oct 2026) replayed step by step on the page at 1× or 4×: each
  agent's steps, every Zetaris query, every Nemotron call with the model that answered and its receipt, and **Show
  raw** for the exact trace line. First: the live run of 24 Oct 20:10 (Wakaf Bharu), where the Critic finds a stale
  upstream reading and asks the Data agent for another gauge. JPS readings in them are redacted.
- **The live log** (`/live`) and **How VEDA worked this out**, above: the run you just made, step by step.
- **Its trace file:** every agent step, Zetaris query and model call is one JSON line in `logs/trace-<run_id>.jsonl`.
- **Recorded live runs with Nemotron:** `data/sample/live_traces/` - 18 real live runs from 23 Oct 2026 with the AI
  explanation, the Critic's AI review, the model that actually answered and the Nightshift receipt (JPS readings
  redacted). Replay one at 4× in the live log: [127.0.0.1:8000/live](http://127.0.0.1:8000/live) → *Replay a recorded
  run…* → pick one → **4×**.
- **Every test and measurement**, with dates and how to reproduce them: [`docs/EVIDENCE.md`](EVIDENCE.md).
- `python -m pytest -q` (over 1,000 offline tests at `0ed62be`) and `python scripts/run_evals.py` (47 safety evals).

## What only works live, and why
| Live only | Why it is not in offline mode |
|---|---|
| **Today's JPS river levels** | JPS readings are fetched live at runtime only and never stored in this repo (organiser ruling, 23 Oct 2026). Offline uses the cited Nov 2024 replay and made-up scenes instead |
| **Nemotron's explanation and the Critic's AI review** | They need Meterless Nightshift with an NVIDIA key. Offline no model is called, so the answer card is the code-written one (it is always checked by code; the AI only adds 1-2 sentences). The recorded live traces above show the AI steps |
| **`/admin`** in full (source health, circuit breakers, the growth strip, gauges VEDA found that wait for a person's approval) | They come from the World Model that live runs build up on disk. Offline each run has its own in-memory World Model, so `/admin` opens but shows only the list of recent answers; approving a gauge is live only and needs a named person |
| **Kuala Krai, Tanah Merah, Dabong, Wakaf Bharu, Pasir Pekan** | Added 24 Oct for live mode, read from today's JPS gauges; the offline scenes are set up for the 4 Home towns only, so offline these 5 get "not covered yet" with the nearest covered town |
| **MetMalaysia warnings and forecasts for today** | Read live from data.gov.my; the replay dates have no recorded warnings |

Live setup (Zetaris + Nightshift): see the README, *Live setup*. Not an official flood warning: follow JPS / APM / police
instructions. Emergency 999 · APM 991.
