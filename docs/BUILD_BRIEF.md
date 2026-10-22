# VEDA — Build Brief
_Design summary for the team and for AI coding assistants. Written 20–22 Oct 2026 as planning notes (declared pre-existing in README); code is written only inside the hackathon window. Synced with the plan change log of 22 Oct night (reconciliation with the code)._

## 1. What VEDA is
**VEDA (Vast Earth Data Analyser)** is a multi-agent system that cross-checks fragmented, sometimes stale or disagreeing public flood data and gives **one plain, forwardable answer** to anyone asking about a place in flood-prone Kelantan, Malaysia.

**User:** anyone asking about a place — a resident (e.g. "Mak Som in Pasir Mas") or her family far away.
**Question (the one decision):** *"Is my place at risk in the next 24–48 hours, and what should we do now?"*
**Input:** one place name. v1 covers towns: Pasir Mas, Rantau Panjang, Kota Bharu, Tumpat (with aliases); kampung / school names later.
**Output:** verdict `NORMAL | WATCH | PREPARE | ACT | INSUFFICIENT_DATA` + range + confidence + what to do now + every claim's source and data age + `conflicts_unresolved` (flag, don't guess) + "not an official warning — follow JPS / APM".
Track: **Solving Fragmented Intelligence** (GenAI Works Open Agent Hackathon 2026).

## 2. Coverage
- Downstream: **Pasir Mas, Tumpat, Kota Bharu**. Upstream early warning: **Kuala Krai, Dabong**.
- Gauges: 16 curated JPS gauges (B-67, tentative until Dr Ariff), core: Sg Golok @ Rantau Panjang · Sg Kelantan @ Tambatan Diraja · @ Kusial (Guillemard) · @ Kuala Krai · Sg Galas @ Dabong.
- Any other place → polite "not covered yet". Never crash, never invent.
- Design must be **Malaysia-ready**: state is configuration, station list is generic.

## 3. Agents (4) — a loop, not a pipeline
| Agent | Kind | Model | Job |
|---|---|---|---|
| Coordinator | LLM | Nightshift lane `fast` (Nemotron 3.5 Lightning) | Tag intent + user type + area → write a **plan** (sources, methods, effort) → delegate → draft answer → revise after Critic |
| Data & Reconciler agent | code | — | Fetch **only via Zetaris SQL**; health-check each source (fresh / schema / plausible / agreement); self-healing ladder; write facts to World Model |
| Forecast agent | code | — | Trend, upstream→downstream lag, "bigger than the 2014 flood?", verdict rules → range + confidence |
| Critic | LLM | Nightshift lane `deep` (Nemotron 3.5 Super VL) | Does evidence support the draft? stale/conflicting data flagged? advice safe? Re-query Zetaris to verify. May **reject** (max 2), then answer becomes low-confidence / INSUFFICIENT_DATA |

Caps: Critic ≤ 2 rejections · bounded retries with backoff (Nightshift 3, Zetaris 2) · per-call timeouts Zetaris 30 s / Nightshift 60 s · answer budget **quick ≤ 30 s / full ≤ 90 s** · 10-minute hard deadline · temperature 0.2 · agents exchange structured JSON, not chat history.

Loop: plain Python state machine `plan → gather → forecast → draft → critique → (revise → critique) → done` (no LangGraph). The **quick path really skips steps** (fewer sources, no forecast refresh/cross-check); the full path runs everything.

## 4. Sponsor technology (all load-bearing)
- **Zetaris** — the only data path. Lightning REST tables (`om_rain`, `mygov_forecast`, `mygov_warning`, `mygov_flood`) + Postgres registered as a datasource (`stations`, `station_links`, `river_levels`, `places`, `historic_peaks`) + views (`place_risk_inputs` and friends). One tool: `run_sql()`. Sources are World Model contexts with per-run health records (no `source_registry` table). **Agents never create or replace views** (setup-only; guard test) — growth = new REST tables + World Model candidates.
- **Meterless World Model engine** — shared state: entities (stations, rivers, places, districts, sources), hand-checked relations (`controlled_by`, `also_controlled_by`, `sentinel_for`, `upstream_of`, `travel_time` with min–max lag, `on_river`, `in_district` — not nearest-distance), timeline facts, `stale`/`conflict` records. Conflicts: **reliability first, then recency**; unresolved ones go to `conflicts_unresolved`. Every agent reads/writes it. Conformance tests + a feature test.
- **Meterless Nightshift** — the only AI provider: `http://127.0.0.1:8088/v1`; model routes `meterless/fast` and `meterless/deep` (Setup Guide 4.6: pin a `meterless/*` route), each lane with its own app name (`veda-fast`, `veda-deep`) pinned to its own lane; never `meterless/auto`. **No direct NVIDIA calls, not even as a fallback.**
- **NVIDIA Nemotron** — powers both LLM agents through Nightshift.
- **Cursor** — the IDE. Claude Code (inside Cursor) leads; the Cursor CLI agent takes small delegated jobs, logged in `docs/cursor-log.md`.

## 5. Data sources
| Need | Source | Notes |
|---|---|---|
| Live river levels + thresholds (normal/alert/warning/danger) | JPS Public Infobanjir — `https://publicinfobanjir.water.gov.my/aras-air/data-paras-air/aras-air-data/?state=KEL&district=ALL&station=ALL&lang=en` | HTML table (`data-th` attributes). Scrape ≤ 1×/15 min, cache, identify ourselves. Keep snapshots; SAMPLE_MODE replays them (B-18) |
| Rain past + forecast | Open-Meteo `/v1/forecast` | No key, CC BY 4.0. One multi-location table, 7 points (core gauges + upstream arms); Thai-side Golok points deferred |
| District forecast + official warnings | data.gov.my `/weather/forecast`, `/weather/warning` | `?meta=true`; 4 req/min → cache |
| **Stale source (must be caught)** | data.gov.my `/flood-warning` | Frozen since 23 Feb 2024 — the Critic must detect and exclude it |
| Historic peaks | JPS 2014 peak table + 2023/2024 reported peaks | Each row with source URL; only verified figures (e.g. Rantau Panjang Nov 2024 = 10.94 m at 27 Nov 19:30, not the unverified 10.97 m) |
| River-flow forecast (stretch) | GloFAS via Open-Meteo Flood API | Starts as `candidate` source → `trusted` only after checks + human approval |
Links shown in answers (not pulled): JKM InfoBencana, MyIBJKM, NADMA portal, 999, 991.

## 6. Self-healing / self-organising / self-growing
- **Healing ladder:** retry with backoff → backup source (JPS live → last good snapshot → Open-Meteo/GloFAS) → lower confidence → INSUFFICIENT_DATA. Circuit breaker: 3 failures → skip source for 15 min. The answer says what happened in plain words.
- **Plan per question:** quick path for simple questions (really fewer steps, ≤ 30 s), full path (all sources, forecast, Critic, ≤ 90 s) when rivers are rising or people may need to move.
- **Growth (with human gates):** lessons memory from Critic rejections (stretch); source promotion candidate → trusted; question radar (log + intent tag every question, no personal data).
- VEDA never rewrites its own code or prompts.

## 7. Safety rules (non-negotiable)
1. Never output NORMAL when key data is missing or stale → INSUFFICIENT_DATA.
2. Never advise walking or driving through floodwater.
3. Always: "Not an official warning. Follow JPS / APM / police instructions." + 999 / 991.
4. Show ranges and confidence, never a single precise number.
5. Replays of past floods are labelled **reconstructed** when built from reported figures.
6. No personal data stored (phone / IC numbers are masked in traces; the question radar keeps intent tags only); no secrets in repo, logs, screenshots or video.

## 8. Hackathon hard rules the code must satisfy
- Runs for judges: `SAMPLE_MODE=true` runs the **real agent logic** offline with an empty `.env` (Zetaris replay + recorded model responses or a labelled rule-based stand-in).
- Traces: `logs/trace-<run_id>.jsonl` — one line per step (agent, action, input summary, output, source, time, decision); ≥ 2 named agents, handoffs, ≥ 1 critique/retry visible. Never hand-written.
- No hard-coded outputs, no demo-only branches; outputs never read from `output_examples/`; unseen inputs must work.
- Entry points: CLI `python run.py "<place>"` and FastAPI `POST /run`, `GET /health`.
- Public repo at submission; README covers setup, usage, dependencies, agent roles, data sources & licences, AI usage, limitations.
- Python 3.13 everywhere (`.venv`, CI, Dockerfile on `python:3.13-slim`).
- Cursor delegation per CLAUDE.md rule 13 (`--trust`, no `--force`; commits `cursor-agent(B-xx): …`).
