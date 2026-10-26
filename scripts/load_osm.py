"""Load OpenStreetMap features near VEDA's places (B-73) into veda-pg. One-off at setup; idempotent (safe to re-run).

    python scripts/load_osm.py                # fetch from Overpass (or reuse data/cache/osm/), compute, write veda-pg
    python scripts/load_osm.py --from-cache   # no network: use the cached Overpass answers only

For each place in data/places.csv, inside Kelantan and within RADIUS_KM:
  - possible PPS (relief centres): NAMED schools, masjid / surau (place_of_worship + religion=muslim) and community
    halls (amenity=community_centre, or a name with "dewan orang ramai" / "balai raya" / "dewan serbaguna") - Husaini
    23 Oct. Always shown as "possible PPS - not an official list"; OSM says nothing about which one is open.
  - bridges: road bridges (highway + bridge=yes) whose line crosses (or ends within 60 m of) a named river, each with the nearest JPS gauge
    on the same river within GAUGE_KM. Facts only: no prediction of a road being cut off (Husaini 23 Oct).
Data (c) OpenStreetMap contributors, ODbL. Agents never fetch: they read veda_pg.osm_place_features through Zetaris.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app import config, trace  # noqa: E402
from app.adapters import pg  # noqa: E402

AGENT = "Setup"
PLACES = ROOT / "data" / "places.csv"
CACHE = ROOT / "data" / "cache" / "osm"          # gitignored; one Overpass answer per place
ENDPOINTS = ("https://overpass-api.de/api/interpreter",) * 2       # main server, a second try after a pause
USER_AGENT = "VEDA-hackathon/0.1 (+https://github.com/vedacool/veda-flood-kelantan; one-off setup load)"
RADIUS_KM = 10            # design choice (B-73 plan): features within 10 km of the place
GAUGE_KM = 10             # a bridge is linked to a JPS gauge on the same river only within 10 km
BRIDGE_RIVER_KM = 0.06    # a bridge line ending within 60 m of a river's centre line spans it
TOP_PPS, TOP_BRIDGES = 5, 5
HALL_WORDS = ("dewan orang ramai", "balai raya", "dewan serbaguna")
PAUSE_S = 30              # between Overpass calls and before a second try (fair use; it answers 502 when busy)


def overpass_query(lat, lon, radius_km=RADIUS_KM):
    """One query per place: bridges + rivers (with geometry), then possible PPS (centres), Kelantan only."""
    r = int(radius_km * 1000)
    around = f"(around:{r},{lat},{lon})"
    halls = "|".join(HALL_WORDS)
    return f"""[out:json][timeout:170];
area["ISO3166-2"="MY-03"]->.k;
(
  way["highway"]["bridge"="yes"]{around}(area.k);
  way["waterway"="river"]{around};
);
out tags geom;
(
  nwr["amenity"="school"]["name"]{around}(area.k);
  nwr["amenity"="place_of_worship"]["religion"="muslim"]["name"]{around}(area.k);
  nwr["amenity"="community_centre"]["name"]{around}(area.k);
  nwr["name"~"{halls}",i]{around}(area.k);
);
out tags center;
"""


def fetch(place, from_cache=False):
    """The Overpass answer for one place: {'fetched_at', 'elements'} - from the cache when present."""
    path = CACHE / f"{place['place_id']}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if from_cache:
        raise OSError(f"no cached Overpass answer for {place['place_id']} ({path.name})")
    q = overpass_query(float(place["lat"]), float(place["lon"]))
    last = None
    for url in ENDPOINTS:
        t0 = time.monotonic()
        try:
            r = requests.post(url, data={"data": q}, timeout=180, headers={"User-Agent": USER_AGENT})
            ok = r.status_code == 200
            trace.step(AGENT, "osm.fetch", input_summary=f"{place['name']} ({url.split('/')[2]})",
                       output_summary=f"HTTP {r.status_code}, {len(r.content)} bytes", source="overpass",
                       status="success" if ok else "failed", duration_ms=int((time.monotonic() - t0) * 1000))
            if ok:
                doc = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "elements": r.json()["elements"]}
                CACHE.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(doc), encoding="utf-8")
                return doc
            last = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            last = f"{type(e).__name__}"
        time.sleep(PAUSE_S)
    raise OSError(f"Overpass failed for {place['place_id']}: {last}")


def km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def centre(el):
    """(lat, lon) of a node, a way with geometry, or an element with an Overpass 'center'."""
    if "lat" in el:
        return el["lat"], el["lon"]
    if "center" in el:
        return el["center"]["lat"], el["center"]["lon"]
    pts = el.get("geometry") or []
    return (sum(p["lat"] for p in pts) / len(pts), sum(p["lon"] for p in pts) / len(pts)) if pts else (None, None)


def _cross(a, b, c, d):
    """True when segment a-b crosses segment c-d (points as (x, y); touching counts)."""
    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(v) < 1e-15 else (1 if v > 0 else -1)

    def on(p, q, r):
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if o1 != o2 and o3 != o4:
        return True
    return (o1 == 0 and on(a, c, b)) or (o2 == 0 and on(a, d, b)) or (o3 == 0 and on(c, a, d)) or \
        (o4 == 0 and on(c, b, d))


def _segments(el):
    pts = [(p["lon"], p["lat"]) for p in el.get("geometry") or [] if p]
    return list(zip(pts, pts[1:]))


def crosses(way_a, way_b):
    """True when two ways' lines cross anywhere (plain lat/lon geometry - fine at bridge scale)."""
    segs_b = _segments(way_b)
    return any(_cross(a, b, c, d) for a, b in _segments(way_a) for c, d in segs_b)


def _point_seg_km(p, a, b):
    """Distance in km from point p to segment a-b ((lon, lat) points, local flat projection)."""
    import math
    kx, ky = 111.32 * math.cos(math.radians(p[1])), 110.57
    px, py, ax, ay, bx, by = p[0] * kx, p[1] * ky, a[0] * kx, a[1] * ky, b[0] * kx, b[1] * ky
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def near_or_crosses(bridge, river, within_km=None):
    """A bridge spans a river when their lines cross, or come within BRIDGE_RIVER_KM (an OSM bridge way often stops
    short of the river's centre line, e.g. where it is split at the border)."""
    within_km = BRIDGE_RIVER_KM if within_km is None else within_km
    if crosses(bridge, river):
        return True
    sb, sr = _segments(bridge), _segments(river)
    return any(min(_point_seg_km(a, c, d), _point_seg_km(b, c, d), _point_seg_km(c, a, b), _point_seg_km(d, a, b))
               <= within_km for a, b in sb for c, d in sr)


def river_name(tags):
    """The river's Malay name as JPS writes it: 'แม่น้ำโกลก / Sungai Golok' -> 'Sg. Golok'; None if unnamed."""
    name = tags.get("name:ms") or tags.get("name") or ""
    parts = [p.strip() for p in name.split("/")]
    latin = [p for p in parts if p and all(ord(ch) < 0x250 for ch in p)]
    if not latin:
        return None
    n = latin[0]
    for long in ("Sungai ", "Sg. ", "Sg "):
        if n.startswith(long):
            return "Sg. " + n[len(long):].strip()
    return n


NOT_PPS_WORDS = ("musalla", "musolla", "mushola", "prayer room")      # Husaini 23 Oct: prayer rooms are not PPS
PPS_RANK = {"school": 0, "community_hall": 0, "masjid": 1, "surau": 1}  # schools / halls before masjid / surau


def pps_category(tags):
    """school | masjid | surau | community_hall, or None when the element is not a possible PPS."""
    name = (tags.get("name") or "").lower()
    if any(w in name for w in NOT_PPS_WORDS):
        return None
    if tags.get("amenity") == "school":
        return "school"
    if tags.get("amenity") == "place_of_worship" and tags.get("religion") == "muslim":
        return "surau" if "surau" in name else "masjid"
    if tags.get("amenity") == "community_centre" or any(w in name for w in HALL_WORDS):
        return "community_hall"
    return None


def features(place, doc, stations):
    """Rows for osm_place_features from one Overpass answer. stations = [{station_key, river, lat, lon}]."""
    plat, plon = float(place["lat"]), float(place["lon"])
    els = doc["elements"]
    rivers = [e for e in els if e.get("type") == "way" and (e.get("tags") or {}).get("waterway") == "river"
              and river_name(e["tags"])]
    rows, seen = [], set()
    for e in els:
        tags = e.get("tags") or {}
        cat = None if tags.get("bridge") == "yes" or tags.get("waterway") else pps_category(tags)
        name = (tags.get("name") or "").strip()
        lat, lon = centre(e)
        if cat and name and lat is not None:
            d = km(plat, plon, lat, lon)
            if d <= RADIUS_KM and name.lower() not in seen:
                seen.add(name.lower())
                rows.append({"kind": "pps_candidate", "osm_ref": f"{e['type']}/{e['id']}", "name": name,
                             "category": cat, "river": None, "km": round(d, 1), "station_key": None, "gauge_km": None})
    pps = sorted(rows, key=lambda r: (PPS_RANK[r["category"]], r["km"]))[:TOP_PPS]
    bridges, seen = [], set()
    for e in els:
        tags = e.get("tags") or {}
        if e.get("type") != "way" or tags.get("bridge") != "yes" or not tags.get("highway"):
            continue
        name = (tags.get("name") or tags.get("ref") or "").strip()
        river = (next((river_name(r["tags"]) for r in rivers if crosses(e, r)), None)        # a real crossing first
                 or next((river_name(r["tags"]) for r in rivers if near_or_crosses(e, r)), None))
        lat, lon = centre(e)
        if not name or not river or lat is None:
            continue
        d = km(plat, plon, lat, lon)
        if d > RADIUS_KM or (name.lower(), river) in seen:      # one row per bridge (dual carriageways = 2 ways)
            continue
        seen.add((name.lower(), river))
        near = sorted(((km(lat, lon, float(s["lat"]), float(s["lon"])), s["station_key"]) for s in stations
                       if s.get("river") == river and s.get("lat") is not None and s.get("lon") is not None))
        gauge = near[0] if near and near[0][0] <= GAUGE_KM else None
        bridges.append({"kind": "bridge", "osm_ref": f"way/{e['id']}", "name": name, "category": tags["highway"],
                        "river": river, "km": round(d, 1), "station_key": gauge[1] if gauge else None,
                        "gauge_km": round(gauge[0], 1) if gauge else None})
    return pps + sorted(bridges, key=lambda r: r["km"])[:TOP_BRIDGES]


def load_places(path=PLACES):
    import csv
    with Path(path).open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def write(rows_by_place, fetched_at):
    """Replace every OSM row in one transaction."""
    with pg.transaction() as conn:
        conn.execute("DELETE FROM osm_place_features")
        for pid, rows in rows_by_place.items():
            for r in rows:
                conn.execute(
                    """INSERT INTO osm_place_features (place_id, kind, osm_ref, name, category, river, km, station_key,
                           gauge_km, loaded_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (pid, r["kind"], r["osm_ref"], r["name"], r["category"], r["river"], r["km"], r["station_key"],
                     r["gauge_km"], fetched_at[pid]))


def main(argv=None):
    """Fetch (or reuse) one Overpass answer per place, compute the rows, write veda-pg; every step traced."""
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Load OpenStreetMap features near VEDA's places into veda-pg")
    ap.add_argument("--from-cache", action="store_true", help="no network: cached Overpass answers only")
    args = ap.parse_args(argv)
    if config.sample_mode():
        print("SAMPLE_MODE is on - the OSM load is for live mode only.")
        return 1
    trace.start_run("load OpenStreetMap features (B-73)")
    try:
        with pg.transaction() as conn:
            stations = [dict(zip(("station_key", "river", "lat", "lon"), r)) for r in
                        conn.execute("SELECT station_key, river, lat, lon FROM stations")]
        rows, fetched = {}, {}
        for i, place in enumerate(load_places()):
            if i and not (CACHE / f"{place['place_id']}.json").exists() and not args.from_cache:
                time.sleep(PAUSE_S)
            doc = fetch(place, args.from_cache)
            rows[place["place_id"]], fetched[place["place_id"]] = features(place, doc, stations), doc["fetched_at"]
            n = rows[place["place_id"]]
            trace.step(AGENT, "osm.features", input_summary=place["name"],
                       output_summary=f"{sum(r['kind'] == 'pps_candidate' for r in n)} possible PPS, "
                                      f"{sum(r['kind'] == 'bridge' for r in n)} bridge(s) over a named river",
                       source="openstreetmap", decision=f"within {RADIUS_KM} km, Kelantan only, named features only")
            print(f"{place['name']}: " + "; ".join(f"{r['kind']} {r['name']} ({r['km']} km"
                                                    + (f", {r['river']}" if r["river"] else "") + ")" for r in n))
        write(rows, fetched)
        trace.step(AGENT, "pg.seed", output_summary=f"{sum(len(v) for v in rows.values())} OSM row(s)",
                   source="veda-pg")
    except (pg.PgError, OSError, KeyError, ValueError) as e:
        trace.end_run("failed", f"{type(e).__name__}: {e}")
        print(f"OSM LOAD FAILED: {type(e).__name__}: {trace.redact(str(e))}")
        return 1
    trace.end_run("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
