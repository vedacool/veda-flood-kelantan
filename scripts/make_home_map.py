"""The Home page's "Where these towns are" sketch map (Cowork / Husaini 24 Oct): a static inline SVG, no tiles, no
network at run time, no map library.

    python scripts/make_home_map.py --fetch   # once: OSM rivers + coastline from Overpass -> data/map/home_map_lines.json
    python scripts/make_home_map.py           # build the SVG into app/web/index.html (between the MAP markers)
    python scripts/make_home_map.py --check   # exit 1 if index.html is not what the script makes

The lines (Sg. Kelantan from Kuala Krai, Sg. Golok, the coastline) come from OpenStreetMap (© OpenStreetMap
contributors, ODbL), simplified to about 300 m and stored in data/map/home_map_lines.json, so building the SVG needs no
network and gives the same file every time. Towns from data/places.csv; the two upstream gauges (Kuala Krai, Kg. Jenob)
from data/stations_mapping.csv. The Thai border is drawn along Sg. Golok (it is the border from Kg. Jenob to the sea);
the Thai side is shaded west of the river.
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINES = ROOT / "data" / "map" / "home_map_lines.json"
PAGE = ROOT / "app" / "web" / "index.html"
START, END = "<!-- MAP START (scripts/make_home_map.py) -->", "<!-- MAP END -->"
USER_AGENT = "VEDA-hackathon/0.1 (+https://github.com/vedacool/veda; one-off map sketch)"
BBOX = (5.47, 101.80, 6.30, 102.40)           # south, west, north, east
W = 340                                         # viewBox width; the height follows the map's shape
PAD = 6
SIMPLIFY_KM = 0.3
UPSTREAM = ("5521044_DKKI0014", "_DTMH0008")    # Sg. Kelantan di Kuala Krai, Sg. Golok di Kg. Jenob
# Label side per town, chosen so the four tap targets never overlap (Tumpat / Kota Bharu / Pasir Mas are close)
# (side, how far the label's centre / start moves right of the dot). Measured at 375 px: no two targets overlap.
SIDE = {"Rantau Panjang": ("below", -15), "Pasir Mas": ("below-start", 0), "Kota Bharu": ("right2", 0),
        "Tumpat": ("left", 0)}


# -- fetch (once, network) ---------------------------------------------------------------------------------------
def fetch():
    import requests
    s, w, n, e = BBOX
    q = f"""[out:json][timeout:120];
(
  way["waterway"="river"]["name"~"Sungai Kelantan|Golok|Kolok|โก-ลก",i]({s - 0.1},{w - 0.1},{n + 0.1},{e + 0.1});
  way["natural"="coastline"]({n - 0.25},{w - 0.1},{n + 0.1},{e + 0.1});
);
out tags geom;"""
    r = requests.post("https://overpass-api.de/api/interpreter", data={"data": q}, timeout=180,
                      headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    ways = r.json()["elements"]
    groups = {"kelantan": [], "golok": [], "coast": []}
    for wy in ways:
        tags, pts = wy.get("tags", {}), [(round(g["lat"], 5), round(g["lon"], 5)) for g in wy.get("geometry", [])]
        name = (tags.get("name", "") + " " + tags.get("name:en", "") + " " + tags.get("name:ms", "")).lower()
        key = ("coast" if tags.get("natural") == "coastline" else "golok" if ("golok" in name or "kolok" in name
                                                                               or "โก-ลก" in name) else "kelantan")
        groups[key].append(pts)
    out = {"source": "© OpenStreetMap contributors, ODbL - Overpass API, fetched once by scripts/make_home_map.py",
           "simplified_km": SIMPLIFY_KM}
    for key, parts in groups.items():
        chains = chain(parts)
        if key == "coast":
            out[key] = [simplify(c, SIMPLIFY_KM) for c in chains if len(c) > 3]
        else:
            line = max(chains, key=len)
            if line[0][0] > line[-1][0]:          # rivers here flow north: source (south) first
                line = line[::-1]
            out[key] = simplify(line, SIMPLIFY_KM)
    LINES.parent.mkdir(parents=True, exist_ok=True)
    LINES.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {LINES.relative_to(ROOT)}: kelantan {len(out['kelantan'])} pts, golok {len(out['golok'])} pts, "
          f"coast {sum(len(c) for c in out['coast'])} pts")


def chain(parts):
    """Join ways that share end points into longer lines."""
    parts = [list(p) for p in parts if len(p) > 1]
    out = []
    while parts:
        line = parts.pop(0)
        grown = True
        while grown:
            grown = False
            for i, p in enumerate(parts):
                if p[0] == line[-1]:
                    line += p[1:]
                elif p[-1] == line[-1]:
                    line += p[::-1][1:]
                elif p[-1] == line[0]:
                    line = p[:-1] + line
                elif p[0] == line[0]:
                    line = p[::-1][:-1] + line
                else:
                    continue
                parts.pop(i)
                grown = True
                break
        out.append(line)
    return out


def km_xy(lat, lon):
    return lon * 111.32 * math.cos(math.radians(5.9)), lat * 110.57


def simplify(pts, tol_km):
    """Douglas-Peucker in km."""
    if len(pts) < 3:
        return pts
    xy = [km_xy(*p) for p in pts]
    (x1, y1), (x2, y2) = xy[0], xy[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-9
    dist = [abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm for x, y in xy]
    i = max(range(1, len(pts) - 1), key=lambda k: dist[k])
    if dist[i] <= tol_km:
        return [pts[0], pts[-1]]
    return simplify(pts[:i + 1], tol_km)[:-1] + simplify(pts[i:], tol_km)


# -- build (offline, deterministic) ------------------------------------------------------------------------------
def project():
    s, w, n, e = BBOX
    x0, y1 = km_xy(n, w)
    x1, _ = km_xy(n, e)
    _, y0 = km_xy(s, w)
    k = (W - 2 * PAD) / (x1 - x0)                 # viewBox units per km
    height = round((y1 - y0) * k + 2 * PAD)

    def xy(lat, lon):
        x, y = km_xy(lat, lon)
        return round(PAD + (x - x0) * k, 1), round(PAD + (y1 - y) * k, 1)
    return xy, k, height


def path(pts, xy):
    return "M" + " L".join(f"{x} {y}" for x, y in (xy(*p) for p in pts))


def arrows(pts, xy, every=4):
    """Small arrowheads along a river, pointing downstream (the list runs source -> mouth)."""
    out = []
    for i in range(every, len(pts) - 1, every):
        (ax, ay), (bx, by) = xy(*pts[i]), xy(*pts[i + 1])
        ang = math.degrees(math.atan2(by - ay, bx - ax))
        mx, my = round((ax + bx) / 2, 1), round((ay + by) / 2, 1)
        out.append(f'<path d="M-5 -4 L3 0 L-5 4" transform="translate({mx} {my}) rotate({round(ang)})" '
                   f'class="m-arrow"/>')
    return "".join(out)


def rows(path_, key=None):
    with path_.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if key is None or r.get("record_type") == key]


def build():
    data = json.loads(LINES.read_text(encoding="utf-8"))
    xy, k, height = project()
    s, w, n, e = BBOX
    towns = [(r["name"], float(r["lat"]), float(r["lon"])) for r in rows(ROOT / "data" / "places.csv")]
    gauges = {r["station_key"]: r for r in rows(ROOT / "data" / "stations_mapping.csv", "gauge")}
    golok, kel = data["golok"], data["kelantan"]
    # Thailand: west of the Golok, from its southern end to the sea (a simplification: south of the river's source
    # the real border runs over land; the sketch stops the shading there)
    g_south, g_mouth = golok[0], golok[-1]
    mx = xy(*g_mouth)[0]              # up from the mouth, across the top, down the west edge; the sea is drawn over it
    thai = path(golok, xy) + f" L{mx} -10 L-10 -10 L-10 {xy(g_south[0], w)[1]} Z"
    # the sea: north / east of the coastline, closed along the map's top and right edges
    coast = max(data["coast"], key=len)
    coast = sorted(coast, key=lambda p: p[1])
    sea = path(coast, xy) + f" L{W} {xy(coast[-1][0], e)[1]} L{W} 0 L0 0 L0 {xy(coast[0][0], w)[1]} Z"
    sea_lbl = xy(n - 0.02, e - 0.12)
    parts = [f'<svg viewBox="0 0 {W} {height}" class="home-map" role="group" aria-labelledby="map-title map-alt">',
             '<title id="map-title" data-t="map_title"></title><desc id="map-alt" data-t="map_alt"></desc>',
             f'<rect width="{W}" height="{height}" class="m-land"/>',
             f'<path d="{thai}" class="m-thai"/>',
             f'<path d="{sea}" class="m-sea"/>',
             f'<path d="{path(golok, xy)}" class="m-border"/>']
    for line in data["coast"]:
        parts.append(f'<path d="{path(line, xy)}" class="m-coast"/>')
    for line in (kel, golok):
        parts.append(f'<path d="{path(line, xy)}" class="m-river"/>' + arrows(line, xy))
    tx, ty = xy(6.27, 101.815)
    parts.append(f'<text x="{tx}" y="{ty}" class="m-label m-thai-label" data-t="map_thailand"></text>')
    cx, cy = xy(5.93, 101.845)                   # rain cloud over the Thai side of the upper Golok
    parts.append(f'<g transform="translate({cx} {cy})" class="m-cloud"><path d="M-14 6 a8 8 0 0 1 2 -15 a11 11 0 0 1 '
                 f'21 -2 a8 8 0 0 1 7 17 Z"/><path d="M-8 10 l-3 7 M0 10 l-3 7 M8 10 l-3 7" class="m-rain"/>'
                 f'<text x="-18" y="34" class="m-label m-small" data-t="map_rain"></text></g>')
    parts.append(f'<text x="{W - 8}" y="{sea_lbl[1] + 14}" class="m-label m-sea-label" text-anchor="end" '
                 f'data-t="map_sea"></text>')
    for key in UPSTREAM:
        g = gauges[key]
        gx, gy = xy(float(g["lat"]), float(g["lon"]))
        place = g["jps_name"].split(" di ")[-1].replace(" (F1)", "")
        lx, anchor = (gx - 10, "end") if key == UPSTREAM[0] else (gx + 10, "start")   # Kuala Krai: label left
        parts.append(f'<circle cx="{gx}" cy="{gy}" r="6" class="m-gauge"/>'
                     f'<text x="{lx}" y="{gy - 2}" text-anchor="{anchor}" class="m-label">{place}</text>'
                     f'<text x="{lx}" y="{gy + 16}" text-anchor="{anchor}" class="m-label m-small" '
                     f'data-t="map_gauge"></text>')
    for name, lat, lon in towns:
        x, y = xy(lat, lon)
        (side, dx), wl = SIDE[name], len(name) * 11.6     # label width at 20 units, bold
        if side == "right2":                        # two lines (Kota / Bharu): fits inside the map's east edge
            first, second = name.split(" ", 1)
            wl = max(len(first), len(second)) * 11.6
            label = (f'<text x="{x + 12}" y="{y - 3}" class="m-label m-town-label">{first}'
                     f'<tspan x="{x + 12}" dy="21">{second}</tspan></text>')
            box = (x - 16, y - 28, wl + 32, 56)
        elif side == "left":
            lx, ly, anchor, box = x - 12, y + 7, "end", (x - 16 - wl, y - 28, wl + 32, 56)
        elif side == "right":
            lx, ly, anchor, box = x + 12, y + 7, "start", (x - 16, y - 28, wl + 32, 56)
        elif side == "below-start":
            lx, ly, anchor, box = x - 8 + dx, y + 30, "start", (x - 16 + dx, y - 12, wl + 24, 56)
        else:
            lx, ly, anchor, box = x + dx, y + 30, "middle", (x + dx - wl / 2 - 6, y - 16, wl + 12, 56)
        if side != "right2":
            label = f'<text x="{lx}" y="{ly}" text-anchor="{anchor}" class="m-label m-town-label">{name}</text>'
        bx, by, bw, bh = (round(v, 1) for v in box)
        parts.append(f'<g class="m-town" role="button" tabindex="0" data-town="{name}">'
                     f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="10" class="m-hit"/>'
                     f'<circle cx="{x}" cy="{y}" r="8" class="m-dot"/>{label}</g>')
    # north arrow + 20 km scale (bottom left, an empty corner)
    ax, ay = 26, height - 74
    parts.append(f'<g transform="translate({ax} {ay})" class="m-north"><path d="M0 -16 L7 6 L0 1 L-7 6 Z"/>'
                 f'<text x="0" y="24" text-anchor="middle" class="m-label m-small">N</text></g>')
    sx, sy, sl = 14, height - 18, 20 * k
    parts.append(f'<g class="m-scale"><path d="M{round(sx, 1)} {sy} h{round(sl, 1)} M{round(sx, 1)} {sy - 5} v10 '
                 f'M{round(sx + sl, 1)} {sy - 5} v10"/><text x="{round(sx + sl / 2, 1)}" y="{sy - 9}" '
                 f'text-anchor="middle" class="m-label m-small">20 km</text></g>')
    parts.append("</svg>")
    return "\n".join(parts)


def page_with(svg):
    page = PAGE.read_text(encoding="utf-8")
    a, b = page.index(START) + len(START), page.index(END)
    return page[:a] + "\n" + svg + "\n" + page[b:]


def main(argv=None):
    ap = argparse.ArgumentParser(description="VEDA Home sketch map")
    ap.add_argument("--fetch", action="store_true", help="fetch the OSM lines once (network)")
    ap.add_argument("--check", action="store_true", help="exit 1 if index.html differs from a fresh build")
    args = ap.parse_args(argv)
    if args.fetch:
        fetch()
    new = page_with(build())
    if args.check:
        same = new == PAGE.read_text(encoding="utf-8")
        print("map up to date" if same else "map differs - run python scripts/make_home_map.py")
        return 0 if same else 1
    PAGE.write_text(new, encoding="utf-8", newline="\n")
    print("map written into app/web/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
