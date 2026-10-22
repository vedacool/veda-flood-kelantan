"""Load VEDA's world from Zetaris into the World Model (the Data agent calls these).

    build_network(world, agent, run_id)   gauges, rivers, districts, places, sources and how they relate
    ingest_readings(world, agent, run_id) the current facts for covered places: river levels, rain, forecast

Everything is read through run_sql (so it replays offline in SAMPLE_MODE). Every write carries provenance:
{kind: 'zetaris', at: <time the DATA refers to>, query_hash, view, agent, run_id}. Using the data's own time
(gauge reading time, forecast window) keeps ingest idempotent: the same readings twice change nothing.
"""
from datetime import datetime

from app import config
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
GAUGE_STATUS_SQL = ("SELECT place_id, role, station_key, level_m, age_minutes, band, change_1h_m, change_3h_m "
                    "FROM veda.place_gauge_status")
READING_TIMES_SQL = ("SELECT station_key, observed_at_utc FROM veda.river_status_latest")
PLACE_INPUTS_SQL = ("SELECT place_id, rain_point, rain_past_24h_mm, rain_past_7d_mm, rain_next_24h_mm, rain_next_72h_mm, "
                    "max_prob_next_24h_pct, forecast_today, forecast_today_when FROM veda.place_risk_inputs")
RAIN_WINDOW_SQL = "SELECT point_key, forecast_until_myt FROM veda.rain_24h_by_point"

SOURCES = {  # contexts: where VEDA's facts come from
    "jps_levels": {"name": "JPS Public Infobanjir river levels (scraped -> veda-pg)", "kind": "scrape"},
    "open_meteo": {"name": "Open-Meteo forecast (Zetaris REST table om_rain)", "kind": "rest_table"},
    "mygov_forecast": {"name": "data.gov.my MetMalaysia forecast (Zetaris REST table)", "kind": "rest_table"},
    "mygov_warning": {"name": "data.gov.my MetMalaysia warnings (Zetaris REST table)", "kind": "rest_table"},
    "mygov_flood": {"name": "data.gov.my /flood-warning (FROZEN since Feb 2024)", "kind": "rest_table"},
}


def _sql(sql, agent, purpose):
    r = zetaris.run_sql(sql, agent=agent, purpose=purpose)
    return r.records, r.query_hash


def _src(at, query_hash, view, agent, run_id, origin):
    return {"kind": "zetaris", "at": at, "query_hash": query_hash, "view": view, "agent": agent, "run_id": run_id,
            "origin": origin}


def _utc_iso(text):
    """Zetaris UTC text '2026-10-22 08:45:00.0' -> '2026-10-22T08:45:00Z'."""
    return str(text).split(".")[0].replace(" ", "T") + "Z" if text else None


def station_id(key):
    return external_id("station", "jps", key)


def place_id(pid):
    return external_id("place", "veda", pid)


def build_network(world, agent, run_id):
    """Gauges, rivers, districts, places and sources + relations. Returns counts."""
    stations, qh = _sql(STATIONS_SQL, agent, "world: curated gauges")
    src = _src(MAPPING_VERSION_AT, qh, "veda_pg.stations", agent, run_id, "curated mapping v1")
    for s in stations:
        sid = station_id(s["station_key"])
        world.upsert_entity("station", external_key={"system": "jps", "id": s["station_key"]}, source=src, attrs={
            "name": s["name"], "is_core": s["is_core"], "chain": s["chain"], "chain_order": s["chain_order"],
            "role": s["role"], "controls_town": s["controls_town"], "lat": s["lat"], "lon": s["lon"],
            "normal_m": s["normal_m"], "alert_m": s["alert_m"], "warning_m": s["warning_m"], "danger_m": s["danger_m"],
            "mapping_status": s["mapping_status"]})
        if s["river"]:
            river = world.upsert_entity("river", name=s["river"], source=src)
            world.relate(sid, "on_river", river["id"], valid_from=MAPPING_VERSION_AT, source=src)
        if s["district"]:
            district = world.upsert_entity("district", name=s["district"], source=src)
            world.relate(sid, "in_district", district["id"], valid_from=MAPPING_VERSION_AT, source=src)
    links, qh = _sql(LINKS_SQL, agent, "world: gauge links")
    lsrc = _src(MAPPING_VERSION_AT, qh, "veda_pg.station_links", agent, run_id, "curated mapping v1")
    for link in links:
        attrs = {"lag_min_h": link["lag_min_h"], "lag_max_h": link["lag_max_h"], "lag_source": link["lag_source"],
                 "status": link["status"]}
        # travel times may exist between many pairs from one gauge -> scope by target (context) so none closes another
        world.relate(station_id(link["from_key"]), link["link_type"], station_id(link["to_key"]),
                     valid_from=MAPPING_VERSION_AT, context=link["to_key"] if link["link_type"] == "travel_time" else None,
                     attrs=attrs, source=lsrc)
    rows, qh = _sql(PLACES_SQL, agent, "world: places and their gauges")
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
    for key, attrs in SOURCES.items():
        world.upsert_context("source", external_key={"system": "veda", "id": key}, attrs=attrs,
                             source=_src(MAPPING_VERSION_AT, None, "registry", agent, run_id, "VEDA source list"))
    return {"stations": len(stations), "links": len(links), "place_gauges": len(rows), "sources": len(SOURCES)}


def ingest_readings(world, agent, run_id):
    """Current facts for covered places. River facts carry the gauge's reading time; rain the forecast window end;
    the forecast its date. Returns counts."""
    times, qh_t = _sql(READING_TIMES_SQL, agent, "world: gauge reading times")
    observed = {t["station_key"]: _utc_iso(t["observed_at_utc"]) for t in times}
    gauges, qh = _sql(GAUGE_STATUS_SQL, agent, "world: gauge status for covered places")
    n = 0
    for g in {r["station_key"]: r for r in gauges}.values():
        at = observed.get(g["station_key"])
        if not at:
            continue                    # no reading at all: nothing to assert (the Critic sees the gap)
        src = _src(at, qh, "veda.place_gauge_status", agent, run_id, "jps_levels")
        sid = station_id(g["station_key"])
        world.assert_fact(sid, "water_level_m", g["level_m"], confidence=0.9, source=src)
        world.assert_fact(sid, "band", g["band"], confidence=0.9, source=src)
        for pred in ("change_1h_m", "change_3h_m"):
            if g[pred] is not None:
                world.assert_fact(sid, pred, g[pred], confidence=0.8, source=src)
        n += 1
    windows, _ = _sql(RAIN_WINDOW_SQL, agent, "world: rain forecast windows")
    window = {w["point_key"]: str(w["forecast_until_myt"]) for w in windows}
    inputs, qh = _sql(PLACE_INPUTS_SQL, agent, "world: place risk inputs")
    today_myt = datetime.now(config.MYT).date().isoformat()   # the forecast row is "today" in Malaysia time
    for p in inputs:
        pid = place_id(p["place_id"])
        rsrc = _src(window.get(p["rain_point"], "unknown"), qh, "veda.place_risk_inputs", agent, run_id, "open_meteo")
        world.assert_fact(pid, "rain_mm", {k: p[k] for k in ("rain_past_24h_mm", "rain_past_7d_mm", "rain_next_24h_mm",
                                                          "rain_next_72h_mm", "max_prob_next_24h_pct")} | {
            "rain_point": p["rain_point"]}, confidence=0.7, source=rsrc)
        if p["forecast_today"]:
            fsrc = _src(today_myt + "T00:00:00+08:00", qh, "veda.place_risk_inputs", agent, run_id, "mygov_forecast")
            world.assert_fact(pid, "met_forecast_today", {"summary": p["forecast_today"],
                                                          "when": p["forecast_today_when"]}, confidence=0.7, source=fsrc)
    return {"gauges": n, "places": len(inputs)}
