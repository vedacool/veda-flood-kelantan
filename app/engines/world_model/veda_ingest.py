"""Load VEDA's world from Zetaris into the World Model (the Data & Reconciler agent calls these).

    build_network(world, agent, run_id)   gauges, rivers, districts, places, sources, historic peaks + relations
    ingest_readings(world, agent, run_id) the current facts for covered places: river levels, rain, forecast

Everything is read through run_sql (so it replays offline in SAMPLE_MODE). Every write carries provenance:
{kind: 'zetaris', at: <time the DATA refers to>, sql, query_hash, view, agent, run_id} (+ health on readings). Using the data's own time
(gauge reading time, forecast window) keeps ingest idempotent: the same readings twice change nothing.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from app import config, trace
from app.adapters import zetaris
from app.engines.world_model.stable_ids import external_id

MAPPING_VERSION_AT = "2026-10-22T00:00:00Z"   # curated mapping v1 (B-67/B-09); bump when Dr Ariff's review is seeded

STATIONS_SQL = ("SELECT station_key, name, river, district, is_core, chain, chain_order, role, controls_town, lat, lon, "
                "normal_m, alert_m, warning_m, danger_m, mapping_status, backup_of FROM veda_pg.stations "
                "WHERE mapping_status IS NOT NULL")
LINKS_SQL = ("SELECT from_key, to_key, link_type, lag_min_h, lag_max_h, lag_source, status FROM veda_pg.station_links")
PLACES_SQL = ("SELECT p.place_id, p.name, p.kind, p.district, p.lat, p.lon, p.rain_location_id, p.forecast_location_id, "
              "p.mapping_status, g.station_key, g.role, g.sort_order FROM veda_pg.places p "
              "JOIN veda_pg.place_gauges g ON g.place_id = p.place_id")
PEAKS_SQL = ("SELECT station_key, event, peak_m, observed_when, source_type, source_name, source_url, reconstructed "
             "FROM veda_pg.historic_peaks")
GAUGE_STATUS_SQL = ("SELECT place_id, role, station_key, level_m, age_minutes, band, change_1h_m, change_3h_m "
                    "FROM veda.place_gauge_status")
READING_TIMES_SQL = ("SELECT station_key, observed_at_utc FROM veda.river_status_latest")
PLACE_INPUTS_SQL = ("SELECT place_id, rain_point, rain_past_24h_mm, rain_past_7d_mm, rain_next_24h_mm, rain_next_72h_mm, "
                    "max_prob_next_24h_pct, forecast_today, forecast_today_when FROM veda.place_risk_inputs")
RAIN_WINDOW_SQL = "SELECT point_key, forecast_until_myt FROM veda.rain_24h_by_point"
# The rain part of PLACE_INPUTS_SQL alone (no MetMalaysia join) - read only when that query fails (Husaini 23 Oct)
PLACE_RAIN_SQL = ("SELECT p.place_id, rp.point_key AS rain_point, rp.rain_past_24h_mm, rp.rain_past_7d_mm, "
                  "rp.rain_next_24h_mm, rp.rain_next_72h_mm, rp.max_prob_next_24h_pct FROM veda_pg.places p "
                  "JOIN veda.rain_24h_by_point rp ON rp.location_id = p.rain_location_id")
# Husaini 23 Oct: a projected range never goes below the gauge's lowest level in the past 7 days
MIN_7D_SQL = ("SELECT station_key, MIN(level_m) AS min_7d_m FROM veda_pg.river_levels "
              "WHERE observed_at > current_timestamp() - INTERVAL 7 DAYS GROUP BY station_key")

# Contexts: where VEDA's facts come from. `reliability` (0-1, TENTATIVE - Dr Ariff) decides conflicts first,
# recency second: official gauge data 0.9, official forecasts/warnings 0.8-0.9, a global weather model 0.6.
SOURCES = {
    "jps_levels": {"name": "JPS Public Infobanjir river levels (scraped -> veda-pg)", "kind": "scrape",
                   "reliability": 0.9},
    "open_meteo": {"name": "Open-Meteo forecast (Zetaris REST table om_rain)", "kind": "rest_table",
                   "reliability": 0.6},
    "mygov_forecast": {"name": "data.gov.my MetMalaysia forecast (Zetaris REST table)", "kind": "rest_table",
                       "reliability": 0.8},
    "mygov_warning": {"name": "data.gov.my MetMalaysia warnings (Zetaris REST table)", "kind": "rest_table",
                      "reliability": 0.9},
    "mygov_flood": {"name": "data.gov.my /flood-warning (FROZEN since Feb 2024)", "kind": "rest_table",
                    "reliability": 0.9},
}


_SQL_BY_HASH = {}


def _sql(sql, agent, purpose, results=None):
    """Records + query hash for one query - from `results` (already fetched by fetch_all) when there."""
    r = results[sql] if results and sql in results else zetaris.run_sql(sql, agent=agent, purpose=purpose)
    _SQL_BY_HASH[r.query_hash] = r.sql
    return r.records, r.query_hash


PURPOSES = {}          # sql -> trace purpose, filled below


FETCH_BUDGET_S = 40      # one parallel query, all tries included (audit 23 Oct: was up to 3 x 30 s + waits each)


LIMITS = {}             # sql -> row limit when a query returns more than run_sql's default 1000 rows


def fetch_all(sqls, agent, workers=10, optional=(), budget_s=FETCH_BUDGET_S):
    """Run independent read-only queries at the same time (B-17: ~28 s one by one -> ~6 s together).
    Returns {sql: SqlResult}. A failed query in `optional` maps to None (its run_sql trace line says why);
    any other failure raises its ZetarisError. budget_s caps each query's total time (all tries)."""
    def run_one(q):
        try:
            return zetaris.run_sql(q, agent=agent, purpose=PURPOSES.get(q, "world: parallel fetch"), budget_s=budget_s,
                                   limit=LIMITS.get(q, 1000))
        except zetaris.ZetarisError as e:
            if q in optional:
                return None
            return e
    with ThreadPoolExecutor(max_workers=min(workers, len(sqls)) or 1) as ex:
        results = dict(zip(sqls, ex.map(trace.bind(run_one), sqls)))
    failed = next((r for r in results.values() if isinstance(r, zetaris.ZetarisError)), None)
    if failed:
        raise failed
    return results


def _src(at, query_hash, view, agent, run_id, origin, health=None):
    src = {"kind": "zetaris", "at": at, "sql": _SQL_BY_HASH.get(query_hash), "query_hash": query_hash, "view": view,
           "agent": agent, "run_id": run_id, "origin": origin}
    if health is not None:
        src["health"] = health
    return src


def _utc_iso(text):
    """Zetaris UTC text '2026-10-22 08:45:00.0' -> '2026-10-22T08:45:00Z'."""
    return str(text).split(".")[0].replace(" ", "T") + "Z" if text else None


def station_id(key):
    return external_id("station", "jps", key)


def place_id(pid):
    return external_id("place", "veda", pid)


def build_network(world, agent, run_id, results=None):
    """Gauges, rivers, districts, places and sources + relations. Returns counts."""
    stations, qh = _sql(STATIONS_SQL, agent, "world: curated gauges", results)
    src = _src(MAPPING_VERSION_AT, qh, "veda_pg.stations", agent, run_id, "curated mapping v1")
    for s in stations:
        sid = station_id(s["station_key"])
        world.upsert_entity("station", external_key={"system": "jps", "id": s["station_key"]}, source=src, attrs={
            "name": s["name"], "is_core": s["is_core"], "chain": s["chain"], "chain_order": s["chain_order"],
            "role": s["role"], "controls_town": s["controls_town"], "lat": s["lat"], "lon": s["lon"],
            "normal_m": s["normal_m"], "alert_m": s["alert_m"], "warning_m": s["warning_m"], "danger_m": s["danger_m"],
            "mapping_status": s["mapping_status"], "backup_of": s["backup_of"]})
        if s["river"]:
            river = world.upsert_entity("river", name=s["river"], source=src)
            world.relate(sid, "on_river", river["id"], valid_from=MAPPING_VERSION_AT, source=src)
        if s["district"]:
            district = world.upsert_entity("district", name=s["district"], source=src)
            world.relate(sid, "in_district", district["id"], valid_from=MAPPING_VERSION_AT, source=src)
    links, qh = _sql(LINKS_SQL, agent, "world: gauge links", results)
    lsrc = _src(MAPPING_VERSION_AT, qh, "veda_pg.station_links", agent, run_id, "curated mapping v1")
    for link in links:
        attrs = {"lag_min_h": link["lag_min_h"], "lag_max_h": link["lag_max_h"], "lag_source": link["lag_source"],
                 "status": link["status"]}
        # travel times may exist between many pairs from one gauge -> scope by target (context) so none closes another
        world.relate(station_id(link["from_key"]), link["link_type"], station_id(link["to_key"]),
                     valid_from=MAPPING_VERSION_AT, context=link["to_key"] if link["link_type"] == "travel_time" else None,
                     attrs=attrs, source=lsrc)
    rows, qh = _sql(PLACES_SQL, agent, "world: places and their gauges", results)
    psrc = _src(MAPPING_VERSION_AT, qh, "veda_pg.places", agent, run_id, "gazetteer v1")
    for r in rows:
        pid = place_id(r["place_id"])
        world.upsert_entity("place", external_key={"system": "veda", "id": r["place_id"]}, source=psrc, attrs={
            "name": r["name"], "kind": r["kind"], "district": r["district"], "lat": r["lat"], "lon": r["lon"],
            "rain_location_id": r["rain_location_id"], "forecast_location_id": r["forecast_location_id"],
            "mapping_status": r["mapping_status"]})
        gid = station_id(r["station_key"])
        if r["role"] == "controlling":
            world.relate(pid, "controlled_by", gid, valid_from=MAPPING_VERSION_AT, source=psrc)
        elif r["role"] == "controlling_secondary":
            world.relate(pid, "also_controlled_by", gid, valid_from=MAPPING_VERSION_AT, context=r["station_key"],
                         source=psrc)
        else:
            world.relate(gid, "sentinel_for", pid, valid_from=MAPPING_VERSION_AT, context=r["place_id"],
                         attrs={"sort_order": r["sort_order"]}, source=psrc)
    peaks, qh = _sql(PEAKS_SQL, agent, "world: historic peaks", results)
    ksrc = _src(MAPPING_VERSION_AT, qh, "veda_pg.historic_peaks", agent, run_id, "historic peaks (B-55)")
    by_station = {}
    for pk in peaks:
        by_station.setdefault(pk["station_key"], []).append(
            {k: pk[k] for k in ("event", "peak_m", "observed_when", "source_type", "source_name", "source_url",
                                "reconstructed")})
    for key, rows in by_station.items():   # one fact per gauge: all its peaks, highest first
        world.assert_fact(station_id(key), "historic_peaks", sorted(rows, key=lambda r: -r["peak_m"]),
                          confidence=0.9, source=ksrc)
    for key, attrs in SOURCES.items():
        world.upsert_context("source", external_key={"system": "veda", "id": key}, attrs=attrs,
                             source=_src(MAPPING_VERSION_AT, None, "registry", agent, run_id, "VEDA source list"))
    return {"stations": len(stations), "links": len(links), "place_gauges": len(rows), "peaks": len(peaks),
            "sources": len(SOURCES)}


def ingest_readings(world, agent, run_id, check=None, results=None, rain_alone=True):
    """Current facts for covered places. River facts carry the gauge's reading time; rain the forecast window end;
    the forecast its date. check(kind, row) -> health dict (the Data & Reconciler agent's checks) is stored with each fact;
    a reading that fails a check is still written, with low confidence, so the gap stays visible.
    Returns counts + the gauges whose health was not ok."""
    times, qh_t = _sql(READING_TIMES_SQL, agent, "world: gauge reading times", results)
    observed = {t["station_key"]: _utc_iso(t["observed_at_utc"]) for t in times}
    gauges, qh = _sql(GAUGE_STATUS_SQL, agent, "world: gauge status for covered places", results)
    n, unhealthy = 0, {}
    for g in {r["station_key"]: r for r in gauges}.values():
        at = observed.get(g["station_key"])
        if not at:
            continue                    # no reading at all: nothing to assert (the Critic sees the gap)
        health = check("jps_levels", g) if check else None
        ok = not health or health.get("ok", True)
        if not ok:
            unhealthy[g["station_key"]] = health
        src = _src(at, qh, "veda.place_gauge_status", agent, run_id, "jps_levels", health)
        sid = station_id(g["station_key"])
        world.assert_fact(sid, "water_level_m", g["level_m"], confidence=0.9 if ok else 0.2, source=src)
        world.assert_fact(sid, "band", g["band"], confidence=0.9 if ok else 0.2, source=src)
        for pred in ("change_1h_m", "change_3h_m"):
            if g[pred] is not None:
                world.assert_fact(sid, pred, g[pred], confidence=0.8 if ok else 0.2, source=src)
        n += 1
    def optional(sql, purpose):          # a failed / skipped (circuit open) rain query -> no rain facts, not no answer
        if results is not None and sql in results and results[sql] is None:
            return [], None
        return _sql(sql, agent, purpose, results)

    if results is not None and MIN_7D_SQL in results:
        lows, qh_m = optional(MIN_7D_SQL, "world: lowest level per gauge, past 7 days")
        for row in lows:
            at = observed.get(row["station_key"])
            if at and row["min_7d_m"] is not None:
                world.assert_fact(station_id(row["station_key"]), "min_7d_m", row["min_7d_m"], confidence=0.9,
                                  source=_src(at, qh_m, "veda_pg.river_levels", agent, run_id, "jps_levels"))
    windows, _ = optional(RAIN_WINDOW_SQL, "world: rain forecast windows")
    window = {w["point_key"]: str(w["forecast_until_myt"]) for w in windows}
    inputs, qh = optional(PLACE_INPUTS_SQL, "world: place risk inputs")
    view, rain = "veda.place_risk_inputs", "joined"
    if results is not None and results.get(PLACE_INPUTS_SQL, True) is None and not rain_alone:
        inputs, rain = [], "skipped"                  # Open-Meteo circuit open: not called for 15 min
    elif results is not None and results.get(PLACE_INPUTS_SQL, True) is None:
        # Husaini 23 Oct: one source failing never takes another down. place_risk_inputs also joins the MetMalaysia
        # forecast (data.gov.my, may answer HTTP 429) - read the Open-Meteo rain on its own instead.
        try:
            inputs, qh = _sql(PLACE_RAIN_SQL, agent, PURPOSES[PLACE_RAIN_SQL])
            view, rain = "veda.rain_24h_by_point", "alone"
        except zetaris.ZetarisError:
            inputs, rain = [], "failed"
    today_myt = datetime.now(config.MYT).date().isoformat()   # the forecast row is "today" in Malaysia time
    for p in inputs:
        pid = place_id(p["place_id"])
        rsrc = _src(window.get(p["rain_point"], "unknown"), qh, view, agent, run_id, "open_meteo",
                    check("open_meteo", p) if check else None)
        world.assert_fact(pid, "rain_mm", {k: p[k] for k in ("rain_past_24h_mm", "rain_past_7d_mm", "rain_next_24h_mm",
                                                          "rain_next_72h_mm", "max_prob_next_24h_pct")} | {
            "rain_point": p["rain_point"]}, confidence=0.7, source=rsrc)
        if p.get("forecast_today"):
            fsrc = _src(today_myt + "T00:00:00+08:00", qh, "veda.place_risk_inputs", agent, run_id, "mygov_forecast",
                        check("mygov_forecast", p) if check else None)
            world.assert_fact(pid, "met_forecast_today", {"summary": p["forecast_today"],
                                                          "when": p["forecast_today_when"]}, confidence=0.7, source=fsrc)
    return {"gauges": n, "places": len(inputs), "unhealthy": unhealthy, "rain": rain}



# -- Flood replay (B-70) ---------------------------------------------------------------------------------------
SCENARIO = re.compile(r"^[a-z0-9_]+$")


def rain_table(scenario):
    """The scene's Open-Meteo archive rain table (B-75: synthetic scenes use the real archive of a real date)."""
    return config.REPLAYS[scenario]["rain_table"]


def replay_sqls(scenario, at):
    """The replay's two queries, CUT AT THE REPLAY TIME in SQL - nothing later ever enters VEDA (no hindsight).
    at = aware datetime. Gauge rows: veda_pg.replay_levels (UTC); rain: the archive REST table, hours in MYT."""
    if not SCENARIO.match(scenario or ""):
        raise ValueError(f"bad replay scenario name {scenario!r}")
    utc = at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    myt = at.astimezone(config.MYT)
    hour = lambda d: d.strftime("%Y-%m-%dT%H:%M")        # noqa: E731 - Open-Meteo hour labels, MYT
    levels = ("SELECT station_key, observed_at, level_m, kind, time_exact, label FROM veda_pg.replay_levels "
              f"WHERE scenario = '{scenario}' AND observed_at <= TIMESTAMP '{utc}' ORDER BY station_key, observed_at")
    rain = ("SELECT COALESCE(r.location_id, 0) AS location_id, "
            f"ROUND(SUM(CASE WHEN t > '{hour(myt - timedelta(hours=24))}' THEN CAST(r.hourly.precipitation[i] AS DOUBLE) "
            "END), 1) AS rain_past_24h_mm, ROUND(SUM(CAST(r.hourly.precipitation[i] AS DOUBLE)), 1) AS rain_past_7d_mm, "
            f"MAX(t) AS last_hour FROM veda_wx.{rain_table(scenario)} r LATERAL VIEW posexplode(r.hourly.time) h AS i, t "
            f"WHERE t > '{hour(myt - timedelta(days=7))}' AND t <= '{hour(myt)}' GROUP BY COALESCE(r.location_id, 0)")
    PURPOSES[levels] = f"replay {scenario}: gauge levels up to the replay time"
    PURPOSES[rain] = f"replay {scenario}: archive rain up to the replay time"
    return {"scenario": scenario, "levels": levels, "rain": rain}


def _true(value):
    """A boolean that may arrive as text from Zetaris ('true' / 'false')."""
    return value is True or str(value).strip().lower() in ("true", "t", "1")


def _band(level, attrs):
    """The JPS band for a level, from the gauge's thresholds (same rule as the river_status_latest view)."""
    for key, band in (("danger_m", "danger"), ("warning_m", "warning"), ("alert_m", "alert"), ("normal_m", "normal")):
        if attrs.get(key) is not None and level >= attrs[key]:
            return band
    return "below_normal" if attrs.get("normal_m") is not None else "unknown"


def _change(rows, latest, hours):
    """Level change against the newest row at least `hours` older (within one more hour) - like the view."""
    t = latest["t"]
    earlier = [r for r in rows if t - timedelta(hours=hours + 1) < r["t"] <= t - timedelta(hours=hours)]
    return round(latest["level_m"] - earlier[-1]["level_m"], 2) if earlier else None


def known_by_then(readings):
    """Drop reconstructed rows that were drawn toward a reported reading AFTER the replay time (audit 23 Oct:
    their level, slope and label would reveal the future). A reconstructed row is kept only when a later reported
    reading is also in the rows (all already cut at the replay time), i.e. both of its anchors were known."""
    kept, last_reported = [], None
    for r in reversed(readings):                               # oldest-first input, walk newest-first
        if r["kind"] == "reported":
            last_reported = r
        if r["kind"] == "reported" or last_reported is not None:
            kept.append(r)
    return kept[::-1]


def ingest_replay(world, agent, run_id, sqls, at, check=None, results=None):
    """The replay's facts: gauge levels (reported or reconstructed, each with its label) and past rain - all
    stamped and cut at the replay time. No MetMalaysia forecast or warnings: data.gov.my keeps no 2024 archive."""
    rows, qh = _sql(sqls["levels"], agent, PURPOSES[sqls["levels"]], results)
    by = {}
    for r in rows:
        by.setdefault(r["station_key"], []).append({**r, "t": datetime.fromisoformat(
            _utc_iso(r["observed_at"]).replace("Z", "+00:00"))})
    for key in list(by):
        kept = known_by_then(by[key])
        if len(kept) < len(by[key]):
            trace.step(agent, "replay.cut", input_summary=f"{key}: {len(by[key])} rows up to the replay time",
                       output_summary=f"kept {len(kept)}", source="code",
                       decision=f"dropped {len(by[key]) - len(kept)} reconstructed rows drawn toward a reading after "
                                f"the replay time - no hindsight")
        if kept:
            by[key] = kept
        else:
            del by[key]
    n, unhealthy = 0, {}
    for key, readings in by.items():
        latest = readings[-1]
        ent = world.entity(station_id(key)) or {"attrs": {}}
        g = {"level_m": latest["level_m"], "change_1h_m": _change(readings, latest, 1),
             "change_3h_m": _change(readings, latest, 3), "danger_m": ent["attrs"].get("danger_m")}
        health = check("jps_levels", g) if check else None
        ok = not health or health.get("ok", True)
        if not ok:
            unhealthy[key] = health
        src = _src(_utc_iso(latest["observed_at"]), qh, "veda_pg.replay_levels", agent, run_id, "replay", health)
        src["replay"] = {"kind": latest["kind"], "label": latest["label"],    # Zetaris returns booleans as text
                         "time_exact": all(_true(r["time_exact"]) for r in readings[-4:])}
        sid = station_id(key)
        world.assert_fact(sid, "water_level_m", latest["level_m"], confidence=0.7 if ok else 0.2, source=src)
        world.assert_fact(sid, "band", _band(latest["level_m"], ent["attrs"]), confidence=0.7, source=src)
        for pred in ("change_1h_m", "change_3h_m"):
            if g[pred] is not None:
                world.assert_fact(sid, pred, g[pred], confidence=0.6, source=src)
        week = [r["level_m"] for r in readings if r["t"] > latest["t"] - timedelta(days=7)]
        world.assert_fact(sid, "min_7d_m", min(week), confidence=0.6, source=src)   # replay rows up to the replay time
        n += 1
    rain, qh_r = _sql(sqls["rain"], agent, PURPOSES[sqls["rain"]], results)
    by_loc = {r["location_id"]: r for r in rain}
    places, _ = _sql(PLACES_SQL, agent, "world: places and their gauges", results)
    at_iso = at.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    for pl in {r["place_id"]: r for r in places}.values():
        r = by_loc.get(pl["rain_location_id"])
        if not r:
            continue
        value = {"rain_past_24h_mm": r["rain_past_24h_mm"], "rain_past_7d_mm": r["rain_past_7d_mm"],
                 "rain_next_24h_mm": None, "rain_next_72h_mm": None, "max_prob_next_24h_pct": None,
                 "rain_point": pl["rain_location_id"]}
        rsrc = _src(at_iso, qh_r, f"veda_wx.{rain_table(sqls['scenario'])}", agent, run_id,
                    "open_meteo_archive", check("open_meteo", value) if check else None)
        world.assert_fact(place_id(pl["place_id"]), "rain_mm", value, confidence=0.7, source=rsrc)
    return {"gauges": n, "places": len(by_loc), "unhealthy": unhealthy}

# -- B-88: hourly rain at every rain point -> the upstream + local rain picture per place (app/rain_rule.py) ---------
_HOURS = ("COALESCE(r.location_id, 0) AS location_id, t AS hour_myt, CAST(r.hourly.precipitation[i] AS DOUBLE) AS rain_mm")
RAIN_HOURS_SQL = (                                       # live: 72 h back + 72 h ahead (Open-Meteo hours are MYT)
    "WITH clock AS (SELECT from_utc_timestamp(current_timestamp(), 'Asia/Kuala_Lumpur') AS now_myt), "
    f"hours AS (SELECT {_HOURS}, to_timestamp(t, \"yyyy-MM-dd'T'HH:mm\") AS ts_myt FROM veda_wx.om_rain r "
    "LATERAL VIEW posexplode(r.hourly.time) h AS i, t) "
    "SELECT p.location_id, p.point_key, p.station_key, p.name, h.hour_myt, h.rain_mm FROM hours h CROSS JOIN clock c "
    "JOIN veda_pg.rain_points p ON p.location_id = h.location_id "
    "WHERE h.ts_myt > c.now_myt - INTERVAL 72 HOURS AND h.ts_myt <= c.now_myt + INTERVAL 72 HOURS")
LIMITS[RAIN_HOURS_SQL] = 2000


def rain_hours_replay_sql(scenario, at):
    """A scene's archive hours at every rain point, the 72 h up to the replay time - nothing later (no hindsight)."""
    if not SCENARIO.match(scenario or ""):
        raise ValueError(f"bad replay scenario name {scenario!r}")
    myt = at.astimezone(config.MYT)
    hour = lambda d: d.strftime("%Y-%m-%dT%H:%M")        # noqa: E731
    sql = (f"WITH hours AS (SELECT {_HOURS} FROM veda_wx.{rain_table(scenario)} r "
           "LATERAL VIEW posexplode(r.hourly.time) h AS i, t) "
           "SELECT p.location_id, p.point_key, p.station_key, p.name, h.hour_myt, h.rain_mm FROM hours h "
           "JOIN veda_pg.rain_points p ON p.location_id = h.location_id "
           f"WHERE h.hour_myt > '{hour(myt - timedelta(hours=72))}' AND h.hour_myt <= '{hour(myt)}'")
    PURPOSES[sql] = f"replay {scenario}: archive rain per hour at every rain point, up to the replay time"
    return sql


def ingest_rain_hours(world, agent, run_id, sql, now, results=None, archive=False):
    """B-88: the upstream + local rain picture for every covered place -> fact 'rain_upstream' on the place (with
    the query's provenance). None when the hours could not be read (the rule then does not run; never raises)."""
    from app import rain_rule
    res = (results or {}).get(sql) if results is not None and sql in results else None
    if res is None:
        return None
    rows, qh = _sql(sql, agent, PURPOSES.get(sql), results)
    links, _ = _sql(LINKS_SQL, agent, "world: gauge links", results)
    places, _ = _sql(PLACES_SQL, agent, "world: places and their gauges", results)
    stations, _ = _sql(STATIONS_SQL, agent, "world: curated gauges", results)
    rivers = {str(s["station_key"]): str(s.get("river") or "") for s in stations}
    hours, meta, key_of = {}, {}, {}
    for r in rows:
        t = datetime.strptime(str(r["hour_myt"]), "%Y-%m-%dT%H:%M").replace(tzinfo=config.MYT)
        hours.setdefault(r["point_key"], []).append((t, r["rain_mm"]))
        meta[r["point_key"]] = {"name": r["name"], "station_key": r["station_key"],
                                "thai": "Thailand" in str(r["name"] or "")}           # Thai-side Golok rain points
        key_of[int(r["location_id"])] = r["point_key"]
    if archive:                                           # a scene: never an hour after the replay time
        hours = {k: [(t, mm) for t, mm in hs if t <= now] for k, hs in hours.items()}
    points = {k: {**meta[k], "features": rain_rule.features(hs, now)} for k, hs in hours.items()}
    towns = {}
    for r in places:
        town = towns.setdefault(r["place_id"], {"controlling": [], "rain_point": key_of.get(int(r["rain_location_id"]))})
        if r["role"] in ("controlling", "controlling_secondary"):
            town["controlling"].append((r["role"] != "controlling", str(r["station_key"])))
    at = now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    for pid, t in towns.items():
        controlling = [k for _, k in sorted(t["controlling"])]
        value = rain_rule.assess(controlling, t["rain_point"], points, links,
                                 golok=any("Golok" in rivers.get(k, "") for k in controlling))
        value["archive"] = archive
        world.assert_fact(place_id(pid), "rain_upstream", value, confidence=0.6,
                          source=_src(at, qh, "veda_wx.om_rain_*" if archive else "veda_wx.om_rain", agent, run_id,
                                      "open_meteo_archive" if archive else "open_meteo"))
    return {"points": len(points), "places": len(towns)}


PURPOSES[RAIN_HOURS_SQL] = "world: rain per hour at every rain point (72 h back, 72 h ahead)"
NETWORK_SQL = [STATIONS_SQL, LINKS_SQL, PLACES_SQL, PEAKS_SQL]
READINGS_SQL = [READING_TIMES_SQL, GAUGE_STATUS_SQL, RAIN_WINDOW_SQL, PLACE_INPUTS_SQL]
PURPOSES.update({
    MIN_7D_SQL: "world: lowest level per gauge, past 7 days",
    STATIONS_SQL: "world: curated gauges",
    LINKS_SQL: "world: gauge links",
    PLACES_SQL: "world: places and their gauges",
    PEAKS_SQL: "world: historic peaks",
    READING_TIMES_SQL: "world: gauge reading times",
    GAUGE_STATUS_SQL: "world: gauge status for covered places",
    RAIN_WINDOW_SQL: "world: rain forecast windows",
    PLACE_INPUTS_SQL: "world: place risk inputs",
    PLACE_RAIN_SQL: "world: place rain only (forecast table unreadable)",
})
