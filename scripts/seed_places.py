"""Seed the place gazetteer (B-09) from data/places.csv into veda-pg. Idempotent: safe to re-run.

    python scripts/seed_places.py              # validate, seed, resolve test names through Zetaris
    python scripts/seed_places.py --check-only # validate only

Each place gets: aliases (normalised with app.gazetteer.normalize), its gauges (controlling / secondary /
sentinels, from the review pack C6 - tentative), its town forecast id, and its nearest rain point
(computed here from rain_points by straight-line distance). One transaction replaces the whole gazetteer.
"""
import argparse
import csv
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app import config, gazetteer, trace  # noqa: E402
from app.adapters import pg, zetaris  # noqa: E402

PLACES = ROOT / "data" / "places.csv"
AGENT = "Setup"
KINDS = {"kampung", "town", "district", "school"}
KELANTAN_BOX = (4.5, 6.4, 101.3, 102.8)
TRY_NAMES = ["Kota Baru", "psr mas", "Rantau Panjng", "Bandar Tumpat", "Gua Musang", "Kuala Lumpur"]


def load_rows(path=PLACES):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def split(cell):
    return [x.strip() for x in cell.split("|") if x.strip()] if cell else []


def gauges_of(row):
    """[(station_key, role, sort_order)] for one place."""
    out = [(row["controlling"], "controlling", 1)] if row["controlling"] else []
    out += [(k, "controlling_secondary", 2) for k in split(row["controlling_secondary"])]
    out += [(k, "sentinel", 10 + i) for i, k in enumerate(split(row["sentinels"]))]
    return out


def validate_places(rows, known_stations):
    """Problems with the places file (empty list = OK)."""
    problems, ids, alias_owner = [], set(), {}
    for r in rows:
        pid = r.get("place_id", "")
        if not pid or pid in ids:
            problems.append(f"place_id '{pid}' is empty or duplicated")
        ids.add(pid)
        if r.get("kind") not in KINDS:
            problems.append(f"{pid}: kind must be one of {sorted(KINDS)}")
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
            if not (KELANTAN_BOX[0] <= lat <= KELANTAN_BOX[1] and KELANTAN_BOX[2] <= lon <= KELANTAN_BOX[3]):
                problems.append(f"{pid}: {lat},{lon} is outside Kelantan")
        except (KeyError, ValueError):
            problems.append(f"{pid}: lat/lon missing or not numbers")
        for col in ("name", "coords_source", "status", "forecast_location_id"):
            if not r.get(col):
                problems.append(f"{pid}: {col} is empty")
        if not r.get("controlling"):
            problems.append(f"{pid}: a controlling gauge is required")
        keys = [k for k, _, _ in gauges_of(r)]
        for k in keys:
            if k not in known_stations:
                problems.append(f"{pid}: gauge {k} is not in the stations table")
        if len(set(keys)) != len(keys):
            problems.append(f"{pid}: the same gauge is listed twice")
        names = split(r.get("aliases", "")) + [r.get("name", "")]
        for alias in names:
            norm = gazetteer.normalize(alias)
            if not norm:
                problems.append(f"{pid}: alias '{alias}' is empty after normalising")
            elif alias_owner.get(norm, pid) != pid:
                problems.append(f"alias '{alias}' belongs to both {alias_owner[norm]} and {pid}")
            else:
                alias_owner[norm] = pid
    return problems


def km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def nearest_rain_point(lat, lon, points):
    """(location_id, distance_km) of the closest rain point."""
    return min(((pid, km(lat, lon, plat, plon)) for pid, plat, plon in points), key=lambda x: x[1])


def seed(rows):
    """Replace the gazetteer in one transaction. Returns {place_id: (rain_location_id, km)}."""
    with pg.transaction() as conn:
        points = conn.execute("SELECT location_id, lat, lon FROM rain_points").fetchall()
        if not points:
            raise pg.PgError("rain_points is empty - run scripts/setup_wx.py first")
        conn.execute("DELETE FROM place_gauges")
        conn.execute("DELETE FROM place_aliases")
        conn.execute("DELETE FROM places")
        chosen = {}
        for r in rows:
            lat, lon = float(r["lat"]), float(r["lon"])
            rain_id, dist = nearest_rain_point(lat, lon, points)
            chosen[r["place_id"]] = (rain_id, round(dist, 1))
            conn.execute(
                """INSERT INTO places (place_id, name, name_norm, kind, district, lat, lon, nearest_station_key,
                       coords_source, rain_location_id, forecast_location_id, mapping_status, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (r["place_id"], r["name"], gazetteer.normalize(r["name"]), r["kind"], r["district"] or None, lat, lon,
                 r["controlling"], r["coords_source"], rain_id, r["forecast_location_id"], r["status"],
                 r["notes"] or None))
            for alias in dict.fromkeys(split(r["aliases"]) + [r["name"]]):
                conn.execute("INSERT INTO place_aliases (alias_norm, place_id, alias) VALUES (%s, %s, %s) "
                             "ON CONFLICT (alias_norm) DO NOTHING", (gazetteer.normalize(alias), r["place_id"], alias))
            for key, role, order in gauges_of(r):
                conn.execute("INSERT INTO place_gauges (place_id, station_key, role, sort_order) VALUES (%s, %s, %s, %s)",
                             (r["place_id"], key, role, order))
    return chosen


def known_station_keys():
    with pg.transaction() as conn:
        return {r[0] for r in conn.execute("SELECT station_key FROM stations")}


def main(argv=None):
    """Validate, seed, then resolve a few test names through Zetaris; every step traced."""
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Seed data/places.csv into veda-pg")
    ap.add_argument("--check-only", action="store_true", help="validate only, write nothing")
    args = ap.parse_args(argv)
    if config.sample_mode():
        print("SAMPLE_MODE is on - seeding is for live mode only.")
        return 1
    trace.start_run("seed place gazetteer (B-09)")
    try:
        rows = load_rows()
        problems = validate_places(rows, known_station_keys())
        trace.step(AGENT, "places.validate", output_summary=f"{len(rows)} places; {len(problems)} problem(s)",
                   status="failed" if problems else "success", details={"problems": problems[:20]})
        if problems:
            trace.end_run("failed", f"{len(problems)} problem(s) in {PLACES.name}")
            print("\n".join(problems))
            return 1
        if args.check_only:
            trace.end_run("success", "CSV valid (check only, nothing written)")
            return 0
        chosen = seed(rows)
        trace.step(AGENT, "pg.seed", output_summary=f"{len(chosen)} places; nearest rain point: "
                   + ", ".join(f"{p}->{lid} ({d} km)" for p, (lid, d) in chosen.items()), source="veda-pg")
        gazetteer.clear_cache()
        for name in TRY_NAMES:
            print(f"{name!r:18} -> {gazetteer.resolve(name, agent=AGENT).message}")
    except (pg.PgError, zetaris.ZetarisError, OSError, KeyError, ValueError) as e:
        trace.end_run("failed", f"{type(e).__name__}: {e}")
        print(f"SEED FAILED: {type(e).__name__}: {trace.redact(str(e))}")
        return 1
    trace.end_run("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
