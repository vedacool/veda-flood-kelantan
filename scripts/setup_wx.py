"""Set up VEDA's live weather/warning sources as Zetaris REST tables (B-07). Idempotent: safe to re-run.

    python scripts/setup_wx.py              # create database + tables, cache them, smoke-check rows
    python scripts/setup_wx.py --refresh    # re-fetch every table now (uncache + cache)
    python scripts/setup_wx.py --recreate   # drop + recreate the tables (after editing data/rain_points.csv)

Tables in Lightning database VEDA_WX:
    om_rain         Open-Meteo rain, ONE table for all points in data/rain_points.csv (one row per point,
                    location_id = row order in the CSV; Open-Meteo leaves location_id EMPTY for the first point,
                    so always read COALESCE(location_id, 0)): hourly precipitation + probability, daily totals,
                    past 7 + next 7 days, Malaysia time
    mygov_forecast  data.gov.my district forecast (all Malaysia; views pick Kelantan)
    mygov_warning   data.gov.my / MetMalaysia weather warnings
    mygov_flood     data.gov.my /flood-warning for Kelantan - FROZEN since Feb 2024, kept on purpose so the
                    Critic can catch a stale source
Tables are cached right after creation: data.gov.my allows only a few requests per minute.
"""
import argparse
import csv
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app import config, trace  # noqa: E402
from app.adapters import pg, zetaris  # noqa: E402

DB = "VEDA_WX"
POINTS = ROOT / "data" / "rain_points.csv"
AGENT = "Setup"
MYGOV = "https://api.data.gov.my"
TABLES = {  # name -> URL (trailing slash + meta=true for data.gov.my: B-64 spike 2)
    "mygov_forecast": f"{MYGOV}/weather/forecast/?meta=true&limit=5000",
    "mygov_warning": f"{MYGOV}/weather/warning/?meta=true&limit=200",
    "mygov_flood": f"{MYGOV}/flood-warning/?meta=true&ifilter=kelantan@state&limit=500",
}
NEAR_KELANTAN = (4.5, 6.6, 101.2, 102.8)   # lat min, lat max, lon min, lon max (incl. the Thai border strip)
KELANTAN_FORECAST_PLACES = ("Kota Bharu", "Pasir Mas", "Tumpat", "Kuala Krai", "Tanah Merah")


def load_points(path=POINTS):
    """Rain points in location_id order."""
    with Path(path).open(encoding="utf-8", newline="") as f:
        rows = [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]
    return sorted(rows, key=lambda r: int(r["location_id"]) if r.get("location_id", "").isdigit() else 10**6)


def validate_points(points):
    """Problems with the points file (empty list = OK)."""
    problems = []
    ids = [p.get("location_id", "") for p in points]
    if ids != [str(i) for i in range(len(points))]:
        problems.append("location_id must be 0, 1, 2, ... in order (Open-Meteo returns points in request order)")
    keys = [p.get("point_key", "") for p in points]
    if len(set(keys)) != len(keys) or "" in keys:
        problems.append("point_key must be unique and non-empty")
    for p in points:
        try:
            lat, lon = float(p["lat"]), float(p["lon"])
            if not (NEAR_KELANTAN[0] <= lat <= NEAR_KELANTAN[1] and NEAR_KELANTAN[2] <= lon <= NEAR_KELANTAN[3]):
                problems.append(f"{p['point_key']}: {lat},{lon} is not in or next to Kelantan")
        except (KeyError, ValueError):
            problems.append(f"{p.get('point_key', '?')}: lat/lon missing or not numbers")
        for col in ("coords_source", "status"):
            if not p.get(col):
                problems.append(f"{p.get('point_key', '?')}: {col} is empty")
    if not points:
        problems.append("no rain points")
    return problems


def open_meteo_url(points):
    """One Open-Meteo request for all points (Zetaris turns the returned list into one row per point)."""
    query = {
        "latitude": ",".join(p["lat"] for p in points),
        "longitude": ",".join(p["lon"] for p in points),
        "hourly": "precipitation,precipitation_probability",
        "daily": "precipitation_sum",
        "past_days": 7,
        "forecast_days": 7,
        "timezone": "Asia/Kuala_Lumpur",
    }
    return "https://api.open-meteo.com/v1/forecast?" + urlencode(query, safe=",")


# B-70 flood replays: the REAL hourly rain at the same points from the Open-Meteo archive (ERA5). The replay cuts it
# at the replay time, so no rain that fell later is ever used (Husaini 22 Oct night: hourly, not daily totals).
REPLAYS = {"om_rain_nov2024": ("2024-11-15", "2024-12-02")}


def archive_url(points, start, end):
    """One Open-Meteo archive request for all points, hourly rain in Malaysia time."""
    query = {
        "latitude": ",".join(p["lat"] for p in points),
        "longitude": ",".join(p["lon"] for p in points),
        "hourly": "precipitation",
        "start_date": start,
        "end_date": end,
        "timezone": "Asia/Kuala_Lumpur",
    }
    return "https://archive-api.open-meteo.com/v1/archive?" + urlencode(query, safe=",")


def all_tables(points):
    return {"om_rain": open_meteo_url(points), **TABLES,
            **{name: archive_url(points, start, end) for name, (start, end) in REPLAYS.items()}}


def create_sql(name, url):
    return (f'CREATE LIGHTNING REST TABLE {name} FROM {DB} REQUEST(endpoint "{url}", method "get", '
            f'response_type "json", http_encoding "URLENCODED") HEADER () BODY ()')


def ensure_tables(points, recreate=False):
    """Database + every REST table (dropped first with --recreate). Returns {table: 'created'|'exists'}."""
    zetaris.run_ddl(f'CREATE LIGHTNING DATABASE {DB} DESCRIBE BY "VEDA_weather_and_warnings"', agent=AGENT,
                    purpose=f"Lightning database {DB}", setup=True)
    done = {}
    for name, url in all_tables(points).items():
        if recreate:
            try:
                zetaris.run_ddl(f"DROP LIGHTNING DATABASE TABLE {DB}.{name}", agent=AGENT,
                                purpose=f"drop {name} (recreate)", setup=True)
            except zetaris.ZetarisError as e:
                if "doesn't exist" not in str(e):
                    raise
        created = zetaris.run_ddl(create_sql(name, url), agent=AGENT, purpose=f"REST table {name}")
        done[name] = "created" if created else "exists"
    return done


def cache_tables(points, refresh=False):
    """CACHE every table (UNCACHE first with --refresh, so the source is fetched again now)."""
    for name in all_tables(points):
        if refresh:
            zetaris.run_ddl(f"UNCACHE TABLE {DB}.{name}", agent=AGENT, purpose=f"uncache {name}", setup=True)
        zetaris.run_ddl(f"CACHE TABLE {DB}.{name}", agent=AGENT, purpose=f"cache {name}")


SMOKE = {
    "om_rain": ("SELECT COALESCE(location_id, 0) AS location_id, latitude, longitude, size(hourly.time) AS hours, "
                "size(daily.time) AS days "
                "FROM veda_wx.om_rain ORDER BY 1"),
    "mygov_forecast": ("SELECT f.location.location_name AS place, COUNT(*) AS days FROM veda_wx.mygov_forecast "
                       "LATERAL VIEW explode(data) AS f WHERE f.location.location_name IN ("
                       + ", ".join(f"'{p}'" for p in KELANTAN_FORECAST_PLACES) + ") GROUP BY f.location.location_name "
                       "ORDER BY place"),
    "mygov_warning": ("SELECT w.warning_issue.issued AS issued, w.warning_issue.title_en AS title "
                      "FROM veda_wx.mygov_warning LATERAL VIEW explode(data) AS w"),
    "mygov_flood": ("SELECT COUNT(*) AS stations, MAX(s.water_level_update_datetime) AS newest "
                    "FROM veda_wx.mygov_flood LATERAL VIEW explode(data) AS s"),
    "om_rain_nov2024": ("SELECT COALESCE(location_id, 0) AS location_id, size(hourly.time) AS hours, "
                        "hourly.time[0] AS first_hour FROM veda_wx.om_rain_nov2024 ORDER BY 1"),
}


def seed_points_table(points):
    """Replace veda-pg rain_points with the CSV (one transaction) so Zetaris views can name each om_rain row."""
    with pg.transaction() as conn:
        conn.execute("DELETE FROM rain_points")
        for p in points:
            conn.execute(
                """INSERT INTO rain_points (location_id, point_key, station_key, name, lat, lon, role, coords_source, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (int(p["location_id"]), p["point_key"], p.get("station_key") or None, p.get("name") or None,
                 float(p["lat"]), float(p["lon"]), p.get("role") or None, p["coords_source"], p["status"]))
    return len(points)


def smoke_check():
    """Rows from every table through run_sql. Returns {table: rows}."""
    return {name: zetaris.run_sql(sql, agent=AGENT, purpose=f"smoke check {name}").rows for name, sql in SMOKE.items()}


def main(argv=None):
    """Validate points, create/cache tables, smoke-check; every step traced."""
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Create VEDA's Zetaris REST tables (rain, forecast, warnings)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch every table now (uncache + cache)")
    ap.add_argument("--recreate", action="store_true", help="drop and recreate the tables (after editing the CSV)")
    args = ap.parse_args(argv)
    if config.sample_mode():
        print("SAMPLE_MODE is on - REST tables are for live mode only.")
        return 1
    trace.start_run("setup Zetaris REST tables (B-07)")
    try:
        points = load_points()
        problems = validate_points(points)
        trace.step(AGENT, "rain_points.validate", output_summary=f"{len(points)} points; {len(problems)} problem(s)",
                   status="failed" if problems else "success", details={"problems": problems})
        if problems:
            trace.end_run("failed", "; ".join(problems))
            print("\n".join(problems))
            return 1
        n_points = seed_points_table(points)
        trace.step(AGENT, "pg.rain_points", output_summary=f"{n_points} rain points written to veda-pg", source="veda-pg")
        done = ensure_tables(points, recreate=args.recreate)
        trace.step(AGENT, "zetaris.tables", output_summary=", ".join(f"{k}: {v}" for k, v in done.items()))
        cache_tables(points, refresh=args.refresh)
        rows = smoke_check()
        newest_flood = rows["mygov_flood"][0][1] if rows["mygov_flood"] else None
        trace.step(AGENT, "smoke_check",
                   output_summary=f"om_rain {len(rows['om_rain'])} points; forecast {len(rows['mygov_forecast'])} places; "
                                  f"warnings {len(rows['mygov_warning'])}; flood-warning newest {newest_flood}",
                   decision="Every table answers through Zetaris")
    except (zetaris.ZetarisError, pg.PgError, OSError, KeyError, ValueError) as e:
        trace.end_run("failed", f"{type(e).__name__}: {e}")
        print(f"SETUP FAILED: {type(e).__name__}: {trace.redact(str(e))}")
        return 1
    trace.end_run("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
