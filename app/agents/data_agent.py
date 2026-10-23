"""Data & Reconciler agent (B-13): gathers the evidence for one plan - only through Zetaris (run_sql) - checks its health and
writes it to the World Model. Plain code, no LLM.

    evidence = data_agent.gather(plan, world)

Health checks (limits are TENTATIVE, 22 Oct - Dr Ariff to review, see docs/review_pack_ariff.md):
    fresh      age of the data vs FRESHNESS: fresh / aging (lower confidence) / stale (never used as "now")
    schema     each row has the fields the agents use, with the right types
    plausible  level in a sane range for its gauge; no jump bigger than MAX_JUMP_1H_M in one hour
    agreement  data.gov.my /flood-warning vs JPS for the same gauges. That source is frozen since Feb 2024, so
               the agent flags it stale and excludes it - and the World Model records why.
Reconciliation: when two sources give the same quantity, the more reliable one wins (reliability is on each source's
World Model context, tentative); on a tie the newer reading wins; if neither decides, the quantity goes into
`conflicts_unresolved` - flagged, never guessed.
Before reading, it refreshes a cached forecast table (Open-Meteo, MetMalaysia) when the World Model says the last
refresh is older than the 'fresh' limit or unknown, and records when it refreshed - so forecast age is known.
Nothing here crashes the run: every source ends with a status (ok | degraded | stale | failed | skipped) and a
plain note, and `usable` says whether the controlling gauge can be trusted for "now".
"""
import re
from datetime import datetime, timedelta, timezone

from app import config, trace
from app.adapters import zetaris
from app.engines.world_model.context import ContextBuilder
from app.engines.world_model.stable_ids import external_id
from app.engines.world_model import veda_ingest
from app.engines.world_model.veda_ingest import (MIN_7D_SQL, NETWORK_SQL, PURPOSES, READINGS_SQL, build_network, fetch_all,
                                                 ingest_readings, ingest_replay, place_id, replay_sqls, station_id)

AGENT = "Data & Reconciler"
SOURCES = ("jps_levels", "open_meteo", "mygov_forecast", "mygov_warning")   # what a plan may ask for
FRESHNESS = {  # minutes: (fresh up to, aging up to); older = stale. Tentative, Dr Ariff to review.
    "jps_levels": (60, 180),
    "open_meteo": (360, 720),
    "mygov_forecast": (720, 1440),
    "mygov_warning": (720, 1440),
}
REFRESHABLE = {"open_meteo": "veda_wx.om_rain", "mygov_forecast": "veda_wx.mygov_forecast"}
REFRESH_BUDGET_S = 10      # one UNCACHE / CACHE call, all tries included (audit 23 Oct)
REFRESH_RETRY_MIN = 15     # after a failed refresh, don't try again for this long (same as the circuit breaker)
LABEL = {"jps_levels": "JPS river levels", "open_meteo": "Open-Meteo rain forecast",
         "mygov_forecast": "MetMalaysia forecast", "mygov_warning": "MetMalaysia warnings"}
LEVEL_RANGE_M = (-5.0, 120.0)     # every Kelantan gauge datum fits (Gua Musang reads ~50 m); outside = broken
ABOVE_DANGER_MAX_M = 15.0         # Dec 2014: Kuala Krai peaked ~9 m above danger; 15 m above = not believable
MAX_JUMP_1H_M = 3.0               # tentative: a bigger rise or fall in one hour is treated as a bad reading
MAX_RAIN_24H_MM = 1000.0
AGREE_M = 0.05                    # two sources within 5 cm of each other agree
NOT_IN_REPLAY = "not available in replay: data.gov.my keeps no 2024 archive"
NOT_READ = "not checked: data.gov.my could not be read"     # Husaini 23 Oct: say so, still answer

CLOCK_SQL = "SELECT current_timestamp() AS now_utc"
FLOOD_WARNING_SQL = ("SELECT s.station_id, s.station_name, s.water_level_current, s.water_level_update_datetime "
                     "FROM veda_wx.mygov_flood LATERAL VIEW explode(data) AS s")
WARNING_SQL = ("SELECT w.heading_en, w.text_en, w.text_bm, w.valid_from, w.valid_to, w.warning_issue.issued AS issued "
               "FROM veda_wx.mygov_warning LATERAL VIEW explode(data) AS w")
# B-73: OpenStreetMap features near each place (possible PPS, bridges over rivers), loaded once by scripts/load_osm.py
OSM_SQL = ("SELECT place_id, kind, osm_ref, name, category, river, km, station_key, gauge_km, loaded_at "
           "FROM veda_pg.osm_place_features")
OSM_INTENTS = ("evacuation", "cut_off")            # the questions that get OSM lines on the card
PPS_RANK = {"school": 0, "community_hall": 0, "masjid": 1, "surau": 1}   # Husaini 23 Oct: schools / halls first
PURPOSES.update({FLOOD_WARNING_SQL: "cross-check: data.gov.my /flood-warning", CLOCK_SQL: "data clock",
                 WARNING_SQL: "MetMalaysia warnings", OSM_SQL: "OpenStreetMap: possible PPS + bridges (B-73)"})
# Which breaker guards which query (B-15). The rain + MET forecast view is one query (place_risk_inputs).
JPS_CORE = set(READINGS_SQL[:2])                       # gauge reading times + gauge status
# Husaini 23 Oct: one breaker per SOURCE, so a data.gov.my outage never trips Open-Meteo. place_risk_inputs joins
# Open-Meteo rain and the data.gov.my forecast: it sits behind data.gov.my, and when it fails the rain is read on its
# own (veda_ingest.PLACE_RAIN_SQL) - which also tells whose failure it was (record_sources).
BREAKER_OF = {READINGS_SQL[0]: "jps_levels", READINGS_SQL[1]: "jps_levels",
              READINGS_SQL[2]: "open_meteo", READINGS_SQL[3]: "data_gov_my",
              WARNING_SQL: "data_gov_my", FLOOD_WARNING_SQL: "data_gov_my"}
BREAKER_OF_TABLE = {"open_meteo": "open_meteo", "mygov_forecast": "data_gov_my"}    # REFRESHABLE key -> breaker
OPTIONAL_SQL = {FLOOD_WARNING_SQL, WARNING_SQL, CLOCK_SQL, READINGS_SQL[2], READINGS_SQL[3], MIN_7D_SQL, OSM_SQL}
FLOOD_WARNING_TYPES = re.compile(r"RAIN|THUNDERSTORM", re.IGNORECASE)   # sea / wind / cyclone notices don't count
KELANTAN_AREA = re.compile(r"Kelantan\s*(\(([^)]*)\))?")


def freshness(source, age_minutes):
    """'fresh' | 'aging' | 'stale' | 'unknown' for an age in minutes, using the source's limits."""
    if age_minutes is None or source not in FRESHNESS:
        return "unknown"
    fresh, aging = FRESHNESS[source]
    return "fresh" if age_minutes <= fresh else "aging" if age_minutes <= aging else "stale"


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check(kind, row):
    """Schema + plausibility of one row -> {'ok', 'schema', 'plausible'} (freshness is judged per run)."""
    schema, plausible = [], []
    if kind == "jps_levels":
        if not _num(row.get("level_m")):
            schema.append(f"level_m is {row.get('level_m')!r}, not a number")
        for k in ("change_1h_m", "change_3h_m", "danger_m"):
            if row.get(k) is not None and not _num(row.get(k)):
                schema.append(f"{k} is not a number")
        if not schema:
            level = row["level_m"]
            if not LEVEL_RANGE_M[0] <= level <= LEVEL_RANGE_M[1]:
                plausible.append(f"level {level} m is outside {LEVEL_RANGE_M}")
            if _num(row.get("danger_m")) and level > row["danger_m"] + ABOVE_DANGER_MAX_M:
                plausible.append(f"level {level} m is more than {ABOVE_DANGER_MAX_M} m above danger")
            if _num(row.get("change_1h_m")) and abs(row["change_1h_m"]) > MAX_JUMP_1H_M:
                plausible.append(f"changed {row['change_1h_m']} m in 1 h")
    elif kind == "open_meteo":
        values = [row.get(k) for k in ("rain_past_24h_mm", "rain_next_24h_mm", "rain_next_72h_mm")]
        if all(v is None for v in values):
            schema.append("no rain values")
        elif any(v is not None and not _num(v) for v in values):
            schema.append("a rain value is not a number")
        elif any(v is not None and not 0 <= v <= MAX_RAIN_24H_MM * 3 for v in values) or \
                (row.get("rain_past_24h_mm") or 0) > MAX_RAIN_24H_MM:
            plausible.append("rain amount out of range")
    elif kind == "mygov_forecast":
        if not isinstance(row.get("forecast_today"), str) or not row["forecast_today"].strip():
            schema.append("no forecast text")
    return {"ok": not schema and not plausible, "schema": "; ".join(schema) or "ok",
            "plausible": "; ".join(plausible) or ("ok" if not schema else "not checked")}


def _utc(text):
    """Zetaris UTC text ('2026-10-22 08:45:00.123') -> aware datetime, or None."""
    try:
        return datetime.fromisoformat(str(text).split(".")[0].replace(" ", "T")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso(dt):
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def source_id(key):
    return external_id("source", "veda", key)


def _clock(result):
    """The time the data is 'as of': Zetaris's own clock (live = now; SAMPLE_MODE = when it was recorded)."""
    try:
        t = _utc(result.rows[0][0])
    except (AttributeError, IndexError):
        t = None
    return t or datetime.now(timezone.utc)


def _last_refresh(world, key):
    facts = world.facts_about(source_id(key), "refreshed_at")
    return datetime.fromisoformat(facts[-1]["value"].replace("Z", "+00:00")) if facts else None


def _refresh_if_old(world, key, clock, run_id):
    """UNCACHE + CACHE one forecast table when its last recorded refresh is old or unknown. Returns a note."""
    clock = clock or datetime.now(timezone.utc)
    last = _last_refresh(world, key)
    age = int((clock - last).total_seconds() // 60) if last else None
    if age is not None and age <= FRESHNESS[key][0]:
        return None
    table = REFRESHABLE[key]
    why = f"last refresh {age} min ago" if age is not None else "no refresh on record"
    if config.sample_mode():
        trace.step(AGENT, "data.refresh", input_summary=table, output_summary="skipped", status="fallback",
                   source="zetaris-replay", decision=f"{why}, but SAMPLE_MODE replays recorded data - no refresh")
        return f"{LABEL[key]}: recorded data, refresh time unknown."
    failed = world.facts_about(source_id(key), "refresh_failed_at")
    failed_at = datetime.fromisoformat(failed[-1]["value"].replace("Z", "+00:00")) if failed else None
    wall = datetime.now(timezone.utc)
    if failed_at and (not last or failed_at > last) and wall - failed_at < timedelta(minutes=REFRESH_RETRY_MIN):
        trace.step(AGENT, "data.refresh", input_summary=table, output_summary="skipped", status="fallback",
                   source="zetaris", decision=f"{why}; the last refresh failed at {_iso(failed_at)} -> no new try "
                                              f"for {REFRESH_RETRY_MIN} min")
        return f"{LABEL[key]}: refresh failed recently, its age is unknown."
    try:
        zetaris.run_ddl(f"UNCACHE TABLE {table}", agent=AGENT, purpose=f"refresh {table} ({why})",
                        budget_s=REFRESH_BUDGET_S)
        zetaris.run_ddl(f"CACHE TABLE {table}", agent=AGENT, purpose=f"re-cache {table}", budget_s=REFRESH_BUDGET_S)
    except zetaris.ZetarisError as e:
        at = _iso(datetime.now(timezone.utc))
        world.assert_fact(source_id(key), "refresh_failed_at", at, confidence=1.0, source={
            "kind": "agent_check", "at": at, "agent": AGENT, "run_id": run_id, "origin": f"refresh {table}"})
        trace.step(AGENT, "data.refresh", input_summary=table, output_summary=f"{e.kind}: {e}", status="fallback",
                   source="zetaris", decision=f"{why}; refresh failed -> using whatever Zetaris has, age unknown; "
                                              f"no new try for {REFRESH_RETRY_MIN} min")
        return f"{LABEL[key]}: refresh failed ({e.kind}), its age is unknown."
    at = _iso(datetime.now(timezone.utc))
    world.assert_fact(source_id(key), "refreshed_at", at, confidence=1.0, source={
        "kind": "zetaris", "at": at, "sql": f"UNCACHE TABLE {table}; CACHE TABLE {table}", "query_hash": None,
        "view": table, "agent": AGENT, "run_id": run_id, "origin": key})
    trace.step(AGENT, "data.refresh", input_summary=table, output_summary=f"refreshed at {at}",
               source="zetaris-live", decision=f"{why} -> fetched {key} again and recorded the time in the World Model")
    return None


def _age_since(clock, dt):
    return int((clock - dt).total_seconds() // 60) if dt else None


HEALTH_MEMO_MIN = 15      # Husaini 23 Oct: a source's status is remembered this long (data.gov.my rate limit)


def known_health(world, key, wall=None):
    """The source's last known status from the World Model -> {status, newest_reading, checked_at, age_min} or
    None. age_min = minutes since it was last read (None when the time is not recorded)."""
    attrs = (world.store.state["contexts"].get(source_id(key)) or {}).get("attrs", {})
    if attrs.get("status") not in ("stale", "ok"):
        return None
    checked = attrs.get("checked_at")
    wall = wall or datetime.now(timezone.utc)
    age = int((wall - datetime.fromisoformat(checked.replace("Z", "+00:00"))).total_seconds() // 60) if checked else None
    return {"status": attrs["status"], "newest_reading": attrs.get("newest_reading"), "checked_at": checked,
            "age_min": age}


def remembered(world, key, wall=None):
    """True when the source was read less than HEALTH_MEMO_MIN minutes ago (then it is not queried again)."""
    h = known_health(world, key, wall)
    return bool(h and h["age_min"] is not None and 0 <= h["age_min"] < HEALTH_MEMO_MIN)


def _from_memory(world, why):
    """/flood-warning not read in this run: a known stale status -> still excluded; anything else -> not checked
    (Husaini 23 Oct)."""
    h = known_health(world, "mygov_flood")
    if h and h["status"] == "stale":
        note = (f"data.gov.my /flood-warning not read now ({why}); known stale (newest reading "
                f"{h['newest_reading']}, checked {_myt_hhmm(h['checked_at']) if h['checked_at'] else 'earlier'}) "
                "- excluded; JPS is used instead.")
        trace.step(AGENT, "data.cross_check", input_summary="JPS vs data.gov.my /flood-warning",
                   output_summary="known stale (World Model)", status="fallback", source="world_model", decision=note)
        return {"status": "stale", "note": note, "newest": h["newest_reading"], "pairs": [], "from_memory": True}
    note = f"data.gov.my /flood-warning could not be read ({why}) and its status is unknown - not checked."
    trace.step(AGENT, "data.cross_check", input_summary="JPS vs data.gov.my /flood-warning",
               output_summary="not checked", status="fallback", source="zetaris", decision=note)
    return {"status": "not_checked", "note": note}


def _cross_check(ctx, clock, world, run_id, r=None, prefetched=False):
    """data.gov.my /flood-warning vs JPS for this place's gauges. Returns the result and writes source status.
    r = the already-fetched /flood-warning result (prefetch), else it is queried here. prefetched with r None =
    the prefetch did not read it (failed, circuit open, or read < 15 min ago) -> not asked again; the World Model's
    known status is used instead (audit + Husaini 23 Oct)."""
    if r is None and prefetched:
        return _from_memory(world, "failed, circuit open or read recently")
    if r is None:
        try:
            r = zetaris.run_sql(FLOOD_WARNING_SQL, agent=AGENT, purpose=PURPOSES[FLOOD_WARNING_SQL])
        except zetaris.ZetarisError as e:
            return _from_memory(world, e.kind)
    myt = [datetime.fromisoformat(str(x["water_level_update_datetime"])).replace(tzinfo=config.MYT)
           for x in r.records if x.get("water_level_update_datetime")]
    newest = max(myt) if myt else None
    age = _age_since(clock, newest)
    fresh = freshness("jps_levels", age)
    by_id = {str(x["station_id"]): x for x in r.records}
    pairs = []
    for g in ctx.get("gauges", []) + ctx.get("sentinels", []):
        other = by_id.get(g["station"].split(":", 2)[2])
        if other and g["level_m"] is not None:
            pairs.append({"gauge": g["name"], "jps_level_m": g["level_m"], "jps_at": g["observed_at"],
                          "mygov_level_m": other["water_level_current"],
                          "mygov_at": str(other["water_level_update_datetime"])})
    newest_text = newest.strftime("%Y-%m-%d %H:%M MYT") if newest else None
    excluded = fresh != "fresh"
    note = (f"data.gov.my /flood-warning is {fresh}: newest reading {newest_text} "
            f"({age // 1440 if age else '?'} days old) - excluded; JPS is used instead." if excluded
            else f"data.gov.my /flood-warning is current (newest {newest_text}).")
    world.upsert_context("source", external_key={"system": "veda", "id": "mygov_flood"},
                         attrs={"status": "stale" if excluded else "ok", "newest_reading": newest_text,
                                "excluded": excluded, "checked_at": _iso(datetime.now(timezone.utc))},
                         source={"kind": "zetaris", "at": _iso(clock), "sql": r.sql, "query_hash": r.query_hash,
                                 "view": "veda_wx.mygov_flood", "agent": AGENT, "run_id": run_id,
                                 "origin": "agreement check"})
    trace.step(AGENT, "data.cross_check", input_summary="JPS vs data.gov.my /flood-warning",
               output_summary=f"{len(pairs)} shared gauge(s); newest {newest_text}",
               status="fallback" if excluded else "success", source="zetaris", decision=note,
               details={"pairs": pairs[:5], "age_minutes": age})
    return {"status": "stale" if excluded else "ok", "note": note, "newest": newest_text, "pairs": pairs}


def reliability(world, key):
    """A source's reliability (0-1) from its World Model context; None if unknown."""
    ctx = world.store.state["contexts"].get(source_id(key)) if world else None
    return (ctx or {}).get("attrs", {}).get("reliability")


def _when(text, tz):
    """'2026-10-22T10:30:00Z' (UTC) or '2024-02-23 14:45:00' (local time in tz) -> aware datetime, or None."""
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=tz)


def reconcile(quantity, candidates, agree_within=AGREE_M):
    """One value for a quantity seen by several sources: higher reliability first, then the newer reading.
    candidates: [{'source', 'value', 'at' (aware datetime or None), 'reliability'}].
    Returns {quantity, candidates, chosen, rule, reason}; rule 'unresolved' (chosen None) when neither reliability
    nor time can decide - flag, don't guess."""
    shown = [{**c, "at": _iso(c["at"]) if c["at"] else None} for c in candidates]
    entry = {"quantity": quantity, "candidates": shown}
    candidates = [c for c in candidates if isinstance(c["value"], (int, float)) and not isinstance(c["value"], bool)]
    if len(candidates) < 2:                 # a source without a value cannot disagree
        only = candidates[0] if candidates else None
        return {**entry, "chosen": only and only["source"], "value": only and only["value"], "rule": "single",
                "reason": "only one source has a value"}
    values = [c["value"] for c in candidates]
    best_rel = max((c["reliability"] or 0) for c in candidates)
    top = [c for c in candidates if (c["reliability"] or 0) == best_rel]
    if max(values) - min(values) <= agree_within:
        chosen, rule, reason = top[0], "agree", f"sources agree within {agree_within}"
    elif len(top) == 1:
        chosen, rule, reason = top[0], "reliability", f"{top[0]['source']} is the more reliable source ({best_rel})"
    else:
        dated = sorted((c for c in top if c["at"]), key=lambda c: c["at"], reverse=True)
        if len(dated) == len(top) and dated[0]["at"] > dated[1]["at"]:
            chosen, rule = dated[0], "recency"
            reason = (f"equal reliability ({best_rel}); {dated[0]['source']} is newer "
                      f"({_iso(dated[0]['at'])} vs {_iso(dated[1]['at'])})")
        else:
            return {**entry, "chosen": None, "value": None, "rule": "unresolved",
                    "reason": f"equal reliability ({best_rel}) and no newer reading - flagged, not guessed"}
    return {**entry, "chosen": chosen["source"], "value": chosen["value"], "rule": rule, "reason": reason}


def _reconcile_levels(cross, world):
    """Gauge levels seen by both JPS and data.gov.my /flood-warning -> reconciliation entries."""
    out = []
    for pr in (cross or {}).get("pairs", []):
        out.append(reconcile(f"water level at {pr['gauge']}", [
            {"source": "jps_levels", "value": pr["jps_level_m"], "at": _when(pr["jps_at"], timezone.utc),
             "reliability": reliability(world, "jps_levels")},
            {"source": "mygov_flood", "value": pr["mygov_level_m"], "at": _when(pr["mygov_at"], config.MYT),
             "reliability": reliability(world, "mygov_flood")}]))
    return out


def _myt_time(text):
    """MetMalaysia times ('2026-10-22T10:30:00', local) -> aware datetime in MYT, or None."""
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00")) if text else None
    except ValueError:
        return None
    return t if t is None or t.tzinfo else t.replace(tzinfo=config.MYT)


def _covers(text, place):
    """Does a warning text name this place's area? 'Kelantan' alone = the whole state; 'Kelantan (Tumpat, ...)'
    = only those districts."""
    for m in KELANTAN_AREA.finditer(text or ""):
        districts = m.group(2)
        if districts is None:
            return True
        names = {place.get("district"), place.get("name")} - {None}
        if any(n.lower() in districts.lower() for n in names):
            return True
    return False


def met_warnings(result, place, clock, world=None, run_id=None):
    """MetMalaysia warnings for one place -> {status: ok | stale | failed, newest_issued, active: [...], note}.
    Only rain / thunderstorm warnings that name the place's area and are valid now count. If the feed's newest
    warning is older than the MET 'aging' limit (24 h) the feed is stale: reported, and it triggers nothing."""
    if result is None:
        return {"status": "failed", "active": [], "note": "MetMalaysia warnings could not be read"}
    rows = result.records
    issued = [t for t in (_myt_time(r.get("issued")) for r in rows) if t]
    newest = max(issued) if issued else None
    age = _age_since(clock, newest)
    fresh = freshness("mygov_warning", age)
    active = []
    for r in rows:
        if not FLOOD_WARNING_TYPES.search(r.get("heading_en") or ""):
            continue
        if not (_covers(r.get("text_en"), place) or _covers(r.get("text_bm"), place)):
            continue
        start, end, at = _myt_time(r.get("valid_from")), _myt_time(r.get("valid_to")), _myt_time(r.get("issued"))
        now_valid = (start is None or start <= clock) and (end >= clock if end else
                                                             at is not None and _age_since(clock, at) <= 1440)
        if now_valid:
            active.append({"heading": r.get("heading_en"), "valid_to": end.isoformat() if end else None})
    newest_text = newest.strftime("%Y-%m-%d %H:%M MYT") if newest else None
    if fresh in ("stale", "unknown"):
        status, note, active = "stale", (f"MetMalaysia warnings feed is stale (newest {newest_text}) - "
                                         "ignored, it triggers nothing"), []
    else:
        status = "ok"
        note = (f"{len(active)} active MetMalaysia warning(s) for this area: "
                + "; ".join(a["heading"] for a in active) if active
                else f"no active MetMalaysia rain/thunderstorm warning for this area (feed updated {newest_text})")
    if world is not None:
        world.upsert_context("source", external_key={"system": "veda", "id": "mygov_warning"},
                             attrs={"status": status, "newest_issued": newest_text},
                             source={"kind": "zetaris", "at": _iso(clock), "sql": result.sql,
                                     "query_hash": result.query_hash, "view": "veda_wx.mygov_warning",
                                     "agent": AGENT, "run_id": run_id, "origin": "MetMalaysia warnings check"})
    trace.step(AGENT, "data.met_warnings", input_summary=place.get("name"), output_summary=note,
               status="success" if status == "ok" else "fallback", source="mygov_warning",
               details={"newest_issued": newest_text, "active": active, "rows": len(rows)})
    return {"status": status, "newest_issued": newest_text, "active": active, "note": note}


# -- Self-healing ladder (B-15) -------------------------------------------------------------------------------
def _fresh_ok(g):
    return (g is not None and g["level_m"] is not None and g.get("freshness") in ("fresh", "aging")
            and (g.get("health") or {"ok": True})["ok"])


def backups_for(world, station):
    """Gauges that can stand in for `station`: the mapping's backup_of pair, either way round (B-67)."""
    key = station.split(":", 2)[2]
    me = world.entity(station) or {"attrs": {}}
    out = [external_id("station", "jps", me["attrs"]["backup_of"])] if me["attrs"].get("backup_of") else []
    out += [e["id"] for e in world.store.state["entities"].values()
            if e["type"] == "station" and str(e["attrs"].get("backup_of") or "") == key and e["id"] not in out]
    return out


def heal(ctx, world, clock):
    """The ladder for every gauge the answer needs, in place on ctx. Steps: 1 fresh/aging reading -> use it;
    2 silent/stale -> a backup gauge with a fresh reading (mapping backup_of; for a place with a second controlling
    gauge, that one); 3 no fresh backup -> keep the last reading for context only (never for the verdict), so the
    controlling gauge gives INSUFFICIENT DATA. Returns the decisions; each is one data.heal trace line."""
    cb, decisions = ContextBuilder(world), []

    def backup_items(g, role):
        items = []
        for b in backups_for(world, g["station"]):
            item = cb.gauge(b, role, f"backup gauge for {g['name']}", clock)
            item["freshness"] = freshness("jps_levels", item["age_minutes"])
            items.append(item)
        return items

    def silent_since(g):
        return (f"silent since {_myt_hhmm(g['observed_at'])}" if g["observed_at"] else "no reading at all")

    def note(step, text, g, used=None):
        decisions.append({"step": step, "gauge": g["name"], "role": g["role"], "used": used, "note": text})
        trace.step(AGENT, "data.heal", input_summary=f"{g['name']} ({g['role']})", output_summary=text,
                   status="fallback", source="jps_levels", decision=f"self-healing step {step}")

    gauges = ctx.get("gauges", [])
    main = next((g for g in gauges if g["role"] == "controlling"), None)
    if main is not None and not _fresh_ok(main):
        candidates = backup_items(main, "controlling") + [g for g in gauges if g["role"] == "controlling_secondary"]
        good = next((c for c in candidates if _fresh_ok(c)), None)
        if good is not None:
            healed = {**good, "role": "controlling", "backup_for": main["name"],
                      "selection_reason": f"backup: {main['name']} {silent_since(main)}"}
            ctx["gauges"] = [healed] + [g for g in gauges if g is not main and g["station"] != good["station"]]
            ctx["silent"] = [main]
            note(2, f"{main['name']} {silent_since(main)} -> using {good['name']}", main, good["name"])
        else:
            ctx["last_reading"] = main if main["level_m"] is not None else None
            note(3, f"{main['name']} {silent_since(main)} and no fresh backup -> INSUFFICIENT DATA"
                    + (f"; last reading {main['level_m']} m shown for context only" if main["level_m"] is not None
                       else ""), main)
    for i, sentinel in enumerate(ctx.get("sentinels", [])):
        if _fresh_ok(sentinel):
            continue
        good = next((c for c in backup_items(sentinel, "sentinel") if _fresh_ok(c)), None)
        if good is not None:
            ctx["sentinels"][i] = {**good, "backup_for": sentinel["name"], "travel_time_h": None,
                                   "selection_reason": f"backup: {sentinel['name']} {silent_since(sentinel)}"}
            note(2, f"upstream {sentinel['name']} {silent_since(sentinel)} -> using {good['name']}", sentinel,
                 good["name"])
    return decisions


def _myt_hhmm(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(config.MYT).strftime("%d %b %H:%M")
    except ValueError:
        return str(iso)


def _forecast_age(world, key, clock):
    return _age_since(clock, _last_refresh(world, key))


# -- Circuit breaker (B-15) ----------------------------------------------------------------------------------
# 3 failures in a row -> the source's queries are skipped for 15 minutes (no 30 s timeouts on every question); then
# one trial (half-open): success closes it, failure opens it again. State lives on the source's World Model context
# (fail_count, open_until) - it survives across runs and its history is the evolution log.
BREAKER_FAILURES = 3
BREAKER_OPEN = timedelta(minutes=15)


def _breaker_state(world, key):
    attrs = (world.store.state["contexts"].get(source_id(key)) or {}).get("attrs", {})
    until = attrs.get("open_until")
    return attrs.get("fail_count") or 0, datetime.fromisoformat(until.replace("Z", "+00:00")) if until else None


def _is_open(world, key, wall):
    """The breaker's state without a trace line (circuit_open traces it)."""
    _, until = _breaker_state(world, key)
    return until is not None and wall < until


def circuit_open(world, key, wall):
    """True while the source's circuit is open (its queries are skipped). Traced either way when not closed."""
    fails, until = _breaker_state(world, key)
    if until is None:
        return False
    if wall < until:
        trace.step(AGENT, "data.circuit", input_summary=key, output_summary=f"open until {_myt_hhmm(_iso(until))} - skipped",
                   status="fallback", source=key, decision=f"{fails} failures in a row -> not called for 15 min")
        return True
    trace.step(AGENT, "data.circuit", input_summary=key, output_summary="half-open: one trial call", source=key,
               decision="15 minutes passed -> try once; success closes the circuit, failure opens it again")
    return False


def record_call(world, key, ok, wall, run_id, why=None):
    """Update the source's breaker after a call: success resets it; the 3rd failure in a row opens it."""
    fails, until = _breaker_state(world, key)
    if ok:
        if not fails and until is None:
            return
        fails, until, text = 0, None, "closed again after a successful call"
    else:
        fails += 1
        until = wall + BREAKER_OPEN if fails >= BREAKER_FAILURES else None
        text = (f"opened until {_myt_hhmm(_iso(until))} after {fails} failures in a row" if until
                else f"failure {fails} of {BREAKER_FAILURES}" + (f" ({why})" if why else ""))
    world.upsert_context("source", external_key={"system": "veda", "id": key},
                         attrs={"fail_count": fails, "open_until": _iso(until) if until else None},
                         source={"kind": "agent_check", "at": _iso(wall), "agent": AGENT, "run_id": run_id,
                                 "origin": "circuit breaker"})
    trace.step(AGENT, "data.circuit", input_summary=key, output_summary=text, source=key,
               status="success" if ok else "fallback", decision="circuit breaker (B-15)")


def record_sources(world, sqls, skipped, results, rain, wall, run_id):
    """One breaker update per SOURCE that was asked this run (Husaini 23 Oct). rain = how the place rain arrived
    (veda_ingest.ingest_readings): 'joined' | 'alone' | 'failed' | 'skipped'."""
    asked = [q for q in sqls if q in BREAKER_OF and q not in skipped]
    ok = {"jps_levels": None, "open_meteo": None, "data_gov_my": None}
    for q in asked:
        key = BREAKER_OF[q]
        if q == READINGS_SQL[3] and results.get(q) is None:
            if rain == "alone":                       # rain read on its own -> the data.gov.my part failed
                ok["data_gov_my"] = False
            continue                                  # rain unreadable too: not data.gov.my's failure to count
        ok[key] = (ok[key] is not False) and results.get(q) is not None
    if rain in ("joined", "alone", "failed") and READINGS_SQL[2] in asked:
        ok["open_meteo"] = ok["open_meteo"] is not False and rain != "failed"
    for key, good in ok.items():
        if good is not None:
            record_call(world, key, good, wall, run_id)


def prefetch(world, now=None, replay=None):
    """The part of gathering that needs no plan: refresh an old forecast table, then fetch the network, the
    readings, the data clock and /flood-warning AT THE SAME TIME and load them into the World Model. The loop runs
    this while the Coordinator is still planning (B-17). Returns {clock, notes, results, events_added} or
    {error, clock, notes}. Never raises for a data problem.
    replay = a scenario (B-70) with now = the replay time: the gauge rows and archive rain are cut at that time in
    the SQL, and no MetMalaysia data is used (data.gov.my keeps no 2024 archive - today's would be anachronistic)."""
    run = trace.current_run()
    run_id = run.run_id if run else None
    events_before = len(world.store.events)
    wall = datetime.now(timezone.utc)               # the breaker runs on real time, also in a replay's past clock
    # audit 23 Oct: the refresh sits behind the breaker - Zetaris down means no refresh tries at all; and a table
    # is not refreshed while its own source's circuit is open (Husaini 23 Oct: per source)
    refresh = not replay and not _is_open(world, "jps_levels", wall)
    notes = []
    for key in REFRESHABLE if refresh else ():
        if _is_open(world, BREAKER_OF_TABLE[key], wall):
            notes.append(f"{LABEL[key]}: not refreshed - {BREAKER_OF_TABLE[key]} circuit open.")
        else:
            notes += [n for n in (_refresh_if_old(world, key, now, run_id),) if n]
    if not replay and not refresh:
        notes.append("Forecast tables not refreshed: Zetaris failed repeatedly (circuit open).")
    rsql = replay_sqls(replay, now) if replay else None
    sqls = (NETWORK_SQL + [rsql["levels"], rsql["rain"], FLOOD_WARNING_SQL, OSM_SQL, DISCOVER_SQL] if replay else
            NETWORK_SQL + READINGS_SQL + [FLOOD_WARNING_SQL, WARNING_SQL, MIN_7D_SQL, OSM_SQL, DISCOVER_SQL]
            + ([] if now else [CLOCK_SQL]))
    skipped = set() if replay else {q for q in sqls if q in BREAKER_OF and circuit_open(world, BREAKER_OF[q], wall)}
    if not replay and FLOOD_WARNING_SQL in sqls and FLOOD_WARNING_SQL not in skipped and remembered(world, "mygov_flood",
                                                                                                    wall):
        skipped.add(FLOOD_WARNING_SQL)              # Husaini 23 Oct: read < 15 min ago -> its status is remembered
        trace.step(AGENT, "data.memo", input_summary="data.gov.my /flood-warning", output_summary="not queried",
                   source="world_model", decision=f"read less than {HEALTH_MEMO_MIN} min ago -> remembered status "
                                                  "used (data.gov.my rate limit)")
    if skipped & JPS_CORE:
        e = zetaris.ZetarisError("source_unavailable", "JPS river levels skipped: circuit open after repeated failures")
        trace.step(AGENT, "world.write", output_summary=str(e), status="failed", source="jps_levels",
                   decision="Circuit breaker open -> no gauge data this run; the answer must say so")
        return {"error": e, "clock": now or wall, "notes": notes}
    try:
        results = fetch_all([q for q in sqls if q not in skipped], AGENT, optional=OPTIONAL_SQL)
        results.update({q: None for q in skipped})
        clock = now or _clock(results[CLOCK_SQL])    # after any refresh, so a just-refreshed forecast is 0 min old
        net = build_network(world, AGENT, run_id, results=results)
        discover(world, results, run_id)              # B-71(c): unmapped JPS gauges -> discovered (never used yet)
        counts = (ingest_replay(world, AGENT, run_id, rsql, now, check=check, results=results) if replay else
                  ingest_readings(world, AGENT, run_id, check=check, results=results,
                                  rain_alone=not _is_open(world, "open_meteo", wall)))
        if not replay:
            record_sources(world, sqls, skipped, results, counts.get("rain"), wall, run_id)
    except zetaris.ZetarisError as e:
        if not replay:
            record_call(world, "jps_levels", False, wall, run_id, f"{e.kind}: {e}")
        trace.step(AGENT, "world.write", output_summary=f"{e.kind}: {e}", status="failed", source="zetaris",
                   decision="Could not load the world from Zetaris -> no evidence; the answer must say so")
        return {"error": e, "clock": now or datetime.now(timezone.utc), "notes": notes}
    added = len(world.store.events) - events_before
    trace.step(AGENT, "world.write", output_summary=f"{net['stations']} gauges, {counts['gauges']} readings, "
                                                    f"{counts['places']} places; {added} new event(s)",
               source="world_model", decision=(f"Wrote {added} new event(s) to the World Model" if added
                                               else "Nothing changed since the last run -> no new events"),
               details={"network": net, "unhealthy": counts["unhealthy"], "queries_in_parallel": len(sqls)})
    return {"clock": clock, "notes": notes, "results": results, "events_added": added,
            "replay": {"scenario": replay, "at": _iso(clock)} if replay else None}


def osm_features(result, place, world, clock):
    """B-73: OpenStreetMap features for one place - {'status', 'pps', 'bridges', 'loaded_at'}. Possible PPS are
    never official or open; a bridge is a fact (it crosses this river, this far away) plus the band of the nearest JPS
    gauge on that river, only when that gauge has a fresh or aging, healthy reading. No prediction (Husaini 23 Oct)."""
    if result is None:
        return {"status": "failed", "pps": [], "bridges": [], "loaded_at": None}
    # names are text even when Zetaris reads a road ref such as "223" as a number (found live 23 Oct)
    rows = [r for r in result.records if r["place_id"] == (place or {}).get("place_id")]
    out = {"status": "ok", "loaded_at": max((str(r["loaded_at"]) for r in rows), default=None),
           "pps": [{"name": str(r["name"]), "category": r["category"], "km": r["km"]}
                   for r in sorted(rows, key=lambda r: (PPS_RANK.get(r["category"], 1), r["km"]))
                   if r["kind"] == "pps_candidate"],
           "bridges": []}
    builder = ContextBuilder(world)
    for r in sorted((r for r in rows if r["kind"] == "bridge"), key=lambda r: r["km"]):
        band = gauge_name = None
        if r["station_key"]:
            g = builder.gauge(station_id(r["station_key"]), "bridge", "nearest JPS gauge on the bridge's river", clock)
            gauge_name = g["name"]
            if (g["level_m"] is not None and freshness("jps_levels", g["age_minutes"]) in ("fresh", "aging")
                    and (g["health"] or {"ok": True})["ok"]):
                band = g["band"]
        out["bridges"].append({"name": str(r["name"]), "river": str(r["river"]), "km": r["km"], "band": band,
                               "gauge": gauge_name, "gauge_km": r["gauge_km"], "has_gauge": bool(r["station_key"])})
    return out


# B-71(c): gauge discovery - JPS gauges the collector stores that VEDA has not mapped (no mapping_status).
DISCOVER_SQL = "SELECT station_key, name, river, district FROM veda_pg.stations WHERE mapping_status IS NULL"
PURPOSES[DISCOVER_SQL] = "discovery: JPS gauges VEDA has not mapped yet"
OPTIONAL_SQL.add(DISCOVER_SQL)
DISCOVERED = "discovered_gauge"          # World Model entity type; attrs.status: discovered | approved


def discover(world, results, run_id):
    """B-71(c): every unmapped JPS gauge becomes a `discovered_gauge` in the World Model with a proposed fit (its river
    and district from JPS, a covered place in the same district, mapped gauges on the same river). It is NEVER used
    until a person approves it (`python -m app.discover approve`), and then only as context - never in the verdict
    until Dr Ariff approves a role. A later scan updates the fit but never the status. -> [names] or None."""
    r = (results or {}).get(DISCOVER_SQL)
    if r is None:
        return None
    stations = (results.get(veda_ingest.STATIONS_SQL) or SimpleResult()).records
    places = (results.get(veda_ingest.PLACES_SQL) or SimpleResult()).records
    place_in = {}
    for p in places:
        place_in.setdefault((p.get("district") or "").lower(), {"place_id": p["place_id"], "name": p["name"]})
    on_river = {}
    for s in stations:
        on_river.setdefault(s.get("river"), []).append(s["name"])
    src = {"kind": "zetaris", "at": _iso(datetime.now(timezone.utc)), "sql": r.sql, "query_hash": r.query_hash,
           "view": "veda_pg.stations", "agent": AGENT, "run_id": run_id, "origin": "discovery"}
    names, new = [], []
    for row in r.records:
        fit = {"river": row.get("river"), "district": row.get("district"),
               "place": place_in.get((row.get("district") or "").lower()),
               "same_river_as": (on_river.get(row.get("river")) or [])[:3],
               "use": "context only, after a person approves; any role in the verdict needs Dr Ariff"}
        eid = external_id(DISCOVERED, "jps", row["station_key"])
        exists = world.entity(eid) is not None
        attrs = {"station_key": row["station_key"], "name": row.get("name"), "fit": fit}
        if not exists:
            attrs["status"] = "discovered"
            new.append(row.get("name"))
        world.upsert_entity(DISCOVERED, external_key={"system": "jps", "id": row["station_key"]}, attrs=attrs,
                            source=src)
        names.append(row.get("name"))
    trace.step(AGENT, "data.discover", input_summary="JPS gauges without a VEDA mapping",
               output_summary=f"{len(names)} unmapped JPS gauge(s) noticed ({len(new)} new) - discovered, not used "
                              "until a person approves", source="world_model",
               decision="written to the World Model with a proposed fit; list them: python -m app.discover list",
               details={"gauges": names[:40], "new": new[:40]})
    return names


class SimpleResult:
    records = []


# B-71(b): the Critic's missing-source request. Live: one query for every mapped gauge's latest reading.
LATEST_ALL_SQL = "SELECT station_key, level_m, observed_at_utc, age_minutes, band FROM veda.river_status_latest"
PURPOSES[LATEST_ALL_SQL] = "Critic's request: the latest reading of every mapped gauge"


def _gap_reason(g):
    if g["level_m"] is None:
        return "no reading"
    if not (g.get("health") or {"ok": True})["ok"]:
        return "failed the plausibility check"
    if g.get("freshness") in ("stale", "unknown"):
        return f"reading too old ({g['age_minutes']} min)" if g.get("age_minutes") is not None else "reading too old"
    return None


def find_gaps(evidence):
    """B-71(b), used by the Critic: the controlling gauge or an upstream gauge without a fresh, healthy reading."""
    ctx = (evidence or {}).get("context") or {}
    gaps = []
    for g in ctx.get("gauges", []) + ctx.get("sentinels", []):
        why = _gap_reason(g) if g["role"] in ("controlling", "sentinel") and not g.get("requested_for") else None
        if why:
            gaps.append({"kind": "controlling" if g["role"] == "controlling" else "upstream", "station": g["station"],
                         "gauge": g["name"], "why": why})
    return gaps


def _load_latest_all(world, run_id):
    """Live: read every mapped gauge's latest reading through Zetaris into the World Model (one query)."""
    r = zetaris.run_sql(LATEST_ALL_SQL, agent=AGENT, purpose=PURPOSES[LATEST_ALL_SQL])
    for row in r.records:
        if row.get("level_m") is None or not row.get("observed_at_utc"):
            continue
        at = _iso(_utc(str(row["observed_at_utc"])))
        health = check("jps_levels", row)
        src = {"kind": "zetaris", "at": at, "sql": r.sql, "query_hash": r.query_hash, "view": "veda.river_status_latest",
               "agent": AGENT, "run_id": run_id, "origin": "jps_levels", "health": health}
        sid = station_id(row["station_key"])
        world.assert_fact(sid, "water_level_m", row["level_m"], confidence=0.9 if health["ok"] else 0.2, source=src)
        world.assert_fact(sid, "band", row["band"], confidence=0.9 if health["ok"] else 0.2, source=src)


def answer_request(gaps, evidence, world):
    """B-71(b): the Data & Reconciler answers the Critic's request. A stale controlling gauge is only re-read (which
    gauge controls a town is flood logic - never swapped here); a silent upstream gauge may be replaced by the nearest
    fresh, healthy gauge further UP the same river chain that the place does not use yet. Changes evidence in place
    (the new gauge joins the upstream list, marked `requested_for`). -> {'found': [...], 'missing': [...]}."""
    run = trace.current_run()
    run_id = run.run_id if run else None
    ctx = evidence["context"]
    clock = datetime.fromisoformat(str(evidence["clock"]).replace("Z", "+00:00"))     # keeps the offset (replay MYT)
    note = None
    if not evidence.get("replay"):
        try:
            _load_latest_all(world, run_id)
        except zetaris.ZetarisError as e:
            note = f"latest readings could not be read ({e.kind})"
    builder = ContextBuilder(world)
    stations = {eid: e["attrs"] for eid, e in world.store.state["entities"].items() if e.get("type") == "station"}
    used = {g["station"] for g in ctx.get("gauges", []) + ctx.get("sentinels", [])}
    main = next((g for g in ctx.get("gauges", []) if g["role"] == "controlling"), None)
    main_attrs = stations.get(main["station"], {}) if main else {}
    found, missing = [], []

    def fresh(item):
        item["freshness"] = freshness("jps_levels", item["age_minutes"])
        return item if _gap_reason(item) is None else None

    for gap in gaps:
        if gap["kind"] == "controlling":
            item = fresh(builder.gauge(gap["station"], "controlling", "re-read on the Critic's request", clock))
            if item:
                ctx["gauges"] = [item if g["station"] == gap["station"] else g for g in ctx["gauges"]]
                found.append({"gauge": item["name"], "role": "controlling", "for": gap["gauge"],
                              "band": item["band"], "age_minutes": item["age_minutes"]})
            else:
                missing.append({"gauge": gap["gauge"], "role": "controlling", "why": gap["why"]})
            continue
        silent = stations.get(gap["station"], {})
        top = main_attrs.get("chain_order") if main_attrs.get("chain") == silent.get("chain") else None
        cands = sorted((sid for sid, a in stations.items() if sid not in used and a.get("chain")
                        and a.get("chain") == silent.get("chain") and a.get("chain_order") is not None
                        and (top is None or a["chain_order"] < top)),
                       key=lambda sid: abs(stations[sid]["chain_order"] - (silent.get("chain_order") or 0)))
        item = next((i for i in (fresh(builder.gauge(sid, "sentinel", f"upstream gauge found on the Critic's request "
                                                                       f"(instead of {gap['gauge']})", clock))
                                 for sid in cands) if i), None)
        if item:
            item.update(requested_for=gap["gauge"], travel_time_h=None)
            ctx["sentinels"].append(item)
            used.add(item["station"])
            found.append({"gauge": item["name"], "role": "upstream", "for": gap["gauge"], "band": item["band"],
                          "age_minutes": item["age_minutes"]})
        else:
            missing.append({"gauge": gap["gauge"], "role": "upstream", "why": gap["why"]})
    text = "; ".join([f"found {f['gauge']} ({f['role']}, {f['band']}, {f['age_minutes']} min old) for {f['for']}"
                      for f in found] + [f"nothing fresh for {m['gauge']} ({m['why']})" for m in missing])
    trace.step(AGENT, "data.request", input_summary="; ".join(f"{g['gauge']}: {g['why']}" for g in gaps),
               output_summary=text + (f" - {note}" if note else ""), target_agent="Critic", source="world_model",
               status="success" if found else "fallback",
               decision=("new evidence -> the verdict is recomputed" if found else
                         "no alternative source -> the answer says what is missing"),
               details={"found": found, "missing": missing, "note": note})
    return {"found": found, "missing": missing}


def sources_selected(plan, ctx, sources, cross, osm):
    """B-71(a): which sources the Data & Reconciler chose for this place, and which it skipped and why ->
    {'chosen': [...], 'skipped': [...]} (short phrases; the trace line and the live view show them)."""
    chosen, skipped = [], []
    for g in ctx.get("gauges", []) + ctx.get("sentinels", []):
        role = {"controlling": "controlling", "controlling_secondary": "second river", "sentinel": "upstream"}.get(
            g["role"], g["role"])
        if g["level_m"] is None:
            skipped.append(f"{g['name']} ({role}): no reading")
        elif not (g.get("health") or {"ok": True})["ok"]:
            skipped.append(f"{g['name']} ({role}): failed the plausibility check")
        elif g.get("freshness") in ("stale", "unknown"):
            skipped.append(f"{g['name']} ({role}): reading too old ({g['age_minutes']} min)")
        else:
            chosen.append(f"{g['name']} ({role}" + (f", backup for {g['backup_for']}" if g.get("backup_for") else "")
                          + ")")
    rain = ctx.get("rain")
    for key, label in (("open_meteo", "Open-Meteo rain" + (f" (point {rain.get('rain_point')})" if rain else "")),
                       ("mygov_forecast", "MetMalaysia forecast"), ("mygov_warning", "MetMalaysia warnings")):
        s = sources.get(key) or {}
        if s.get("status") in ("ok", "stale", "degraded"):
            chosen.append(label + (" (stale)" if s.get("status") == "stale" else ""))
        else:
            skipped.append(f"{label}: {s.get('note') or s.get('status') or 'not read'}")
    if cross:
        (skipped if cross.get("status") != "ok" else chosen).append(
            "data.gov.my flood-warning" + {"stale": ": stale - excluded", "not_checked": ": could not be read"}.get(
                cross.get("status"), ""))
    elif plan.get("effort") == "quick":
        skipped.append("data.gov.my flood-warning cross-check: quick path")
    if osm:
        (chosen if osm["status"] == "ok" else skipped).append(
            "OpenStreetMap " + ("possible PPS" if plan.get("intent") == "evacuation" else "bridges")
            + ("" if osm["status"] == "ok" else ": could not be read"))
    return {"chosen": chosen, "skipped": skipped}


def gather(plan, world, now=None, pre=None):
    """Evidence for plan['place'] from the sources the plan asks for. pre = prefetch() result (run during
    planning); without it the prefetch runs here. A quick plan skips the cross-check and reconciliation.
    Never raises for a data problem."""
    run = trace.current_run()
    run_id = run.run_id if run else None
    pre = pre or prefetch(world, now)
    quick = plan.get("effort") == "quick"
    wanted = [s for s in plan.get("sources", []) if s in SOURCES]
    events_before = len(world.store.events)
    sources = {s: {"status": "skipped", "note": "not in the plan"} for s in SOURCES if s not in wanted}
    notes, clock = list(pre["notes"]), pre["clock"]
    if pre.get("error"):
        e = pre["error"]
        return {"place": plan.get("place"), "clock": _iso(clock), "usable": False, "context": None,
                "sources": {s: {"status": "failed", "note": f"Zetaris {e.kind}"} for s in wanted} | sources,
                "notes": [f"Could not read data through Zetaris ({e.kind})."], "events_added": 0,
                "reconciliation": [], "conflicts_unresolved": []}

    ctx = ContextBuilder(world).build(plan.get("intent", "risk_check"), place_id(plan["place"]["place_id"]),
                                      now=clock)
    trace.step(AGENT, "world.read", input_summary=ctx["place"].get("name") if ctx["found"] else plan["place"],
               output_summary=f"{ctx['items']} item(s); missing: {', '.join(ctx['trace'].get('missing', [])) or '-'}",
               source="world_model", decision=ctx["trace"]["strategy"])

    for key, field in (("open_meteo", "rain"), ("mygov_forecast", "met_forecast")):
        if key not in wanted and ctx.get(field) is not None:
            ctx[field] = None           # evidence holds only what the plan asked for
    for g in ctx.get("gauges", []) + ctx.get("sentinels", []):
        g["freshness"] = freshness("jps_levels", g["age_minutes"])
    healing = heal(ctx, world, clock) if ctx.get("found") else []
    gauges = ctx.get("gauges", []) + ctx.get("sentinels", [])
    if "jps_levels" in wanted:
        bad = [g["name"] for g in gauges if g["health"] and not g["health"]["ok"]]
        stale = [g["name"] for g in gauges if g["freshness"] in ("stale", "unknown")]
        status = "failed" if not gauges else "degraded" if bad or stale else "ok"
        sources["jps_levels"] = {"status": status, "note": (
            f"{len(gauges)} gauge(s); " + (f"stale or missing: {', '.join(stale)}; " if stale else "")
            + (f"failed checks: {', '.join(bad)}" if bad else "all readings passed the checks"))}
    replay = pre.get("replay")
    for key, item in (("open_meteo", ctx.get("rain")), ("mygov_forecast", ctx.get("met_forecast"))):
        if key not in wanted:
            continue
        if replay and key == "open_meteo" and item is not None:
            item["age_minutes"], item["freshness"] = None, "archive"
            sources[key] = {"status": "ok", "note": "Open-Meteo archive: real hourly rain up to the replay time"}
            continue
        if replay:
            sources[key] = {"status": "skipped", "note": NOT_IN_REPLAY}
            continue
        if item is None:
            unread = key == "mygov_forecast" and pre.get("results", {}).get(READINGS_SQL[3], True) is None
            sources[key] = ({"status": "not_checked", "note": NOT_READ} if unread else
                            {"status": "failed", "note": "no data for this place"})
            continue
        age = _forecast_age(world, key, clock)
        item["age_minutes"], item["freshness"] = age, freshness(key, age)
        health = (item.get("provenance") or {}).get("health") or {"ok": True}
        status = "degraded" if not health["ok"] else "stale" if item["freshness"] == "stale" else \
            "degraded" if item["freshness"] in ("aging", "unknown") else "ok"
        sources[key] = {"status": status, "note": f"refreshed {age} min ago ({item['freshness']})"
                        if age is not None else "refresh time unknown"}
    warnings = None
    if "mygov_warning" in wanted and replay:
        sources["mygov_warning"] = {"status": "skipped", "note": NOT_IN_REPLAY}
    elif "mygov_warning" in wanted:
        warnings = met_warnings(pre.get("results", {}).get(WARNING_SQL), plan["place"], clock, world, run_id)
        sources["mygov_warning"] = {"status": {"ok": "ok", "stale": "stale"}.get(warnings["status"], "not_checked"),
                                    "note": warnings["note"] if warnings["status"] in ("ok", "stale") else NOT_READ}

    cross = None
    if quick:
        trace.step(AGENT, "data.quick", output_summary="cross-check and reconciliation skipped", source="plan",
                   decision="Quick plan: current readings only (the full path cross-checks data.gov.my)")
    elif "jps_levels" in wanted and ctx["found"]:
        cross = _cross_check(ctx, clock, world, run_id, pre.get("results", {}).get(FLOOD_WARNING_SQL),
                             prefetched=FLOOD_WARNING_SQL in pre.get("results", {}))
    if cross:
        notes.insert(0, cross["note"])         # the excluded source matters more than refresh details
    reconciliation = _reconcile_levels(cross, world)
    unresolved = [r for r in reconciliation if r["rule"] == "unresolved"]
    if reconciliation:
        trace.step(AGENT, "data.reconcile", input_summary=f"{len(reconciliation)} quantity(ies) seen by 2 sources",
                   output_summary=f"{len(unresolved)} unresolved", source="world_model",
                   status="fallback" if unresolved else "success",
                   decision="; ".join(f"{r['quantity']}: {r['rule']} - {r['reason']}" for r in reconciliation[:3]),
                   details={"reconciliation": reconciliation})

    osm = None
    if plan.get("intent") in OSM_INTENTS and ctx["found"]:
        osm = osm_features(pre.get("results", {}).get(OSM_SQL), plan["place"], world, clock)
        trace.step(AGENT, "data.osm", input_summary=f"{plan['intent']}: {ctx['place'].get('name')}",
                   output_summary=(f"{len(osm['pps'])} possible PPS, {len(osm['bridges'])} bridge(s)"
                                   if osm["status"] == "ok" else "OpenStreetMap table could not be read"),
                   source="openstreetmap", status="success" if osm["status"] == "ok" else "fallback",
                   decision="Possible PPS are not an official list; bridges are facts only, no prediction")

    controlling = next((g for g in ctx.get("gauges", []) if g["role"] == "controlling"), None)
    usable = bool(controlling and controlling["level_m"] is not None and controlling["freshness"] in ("fresh", "aging")
                  and (controlling["health"] or {"ok": True})["ok"])
    if not usable:
        notes.append("The controlling gauge has no fresh, healthy reading - current status cannot be confirmed.")
    for key, s in sources.items():
        if s["status"] != "skipped":
            world.assert_fact(source_id(key), "health", s, confidence=1.0, source={
                "kind": "agent_check", "at": _iso(clock), "agent": AGENT, "run_id": run_id, "origin": "Data & Reconciler agent"})
        trace.step(AGENT, "data.health", input_summary=key, output_summary=f"{s['status']}: {s['note']}",
                   status="success" if s["status"] in ("ok", "skipped") else "fallback", source=key)
    selected = sources_selected(plan, ctx, sources, cross, osm) if ctx.get("found") else None
    if selected:                                   # B-71(a): what was chosen for this place, what was skipped and why
        trace.step(AGENT, "data.sources", input_summary=(ctx.get("place") or {}).get("name"),
                   output_summary=f"chosen: {'; '.join(selected['chosen']) or '-'} | skipped: "
                                  f"{'; '.join(selected['skipped']) or '-'}",
                   target_agent="Forecast", source="world_model",
                   decision=f"{len(selected['chosen'])} source(s) used, {len(selected['skipped'])} skipped",
                   details=selected)
    return {"place": ctx.get("place"), "clock": _iso(clock), "usable": usable, "context": ctx, "sources": sources,
            "selected": selected,
            "cross_check": cross, "reconciliation": reconciliation, "conflicts_unresolved": unresolved,
            "met_warnings": warnings, "replay": replay, "healing": healing, "osm": osm,
            "notes": notes, "events_added": pre["events_added"] + len(world.store.events) - events_before}
