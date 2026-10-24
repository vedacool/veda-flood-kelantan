"""B-88 validation (Cowork 24 Oct): run the upstream + local rain rule hour by hour on real Open-Meteo archive rain,
with no hindsight (at each hour only the rain up to that hour is used - an archive has no forecasts, so the forecast
parts of the rule cannot fire here), and report when it fires. Numbers are NOT tuned to the result.

    python scripts/validate_rain_rule.py            # live Zetaris; writes docs/validation/b88_rain_rule.md

Two periods: the Nov 2024 flood (22 Nov -> 2 Dec) and 14 ordinary days (1-14 Oct 2024).
"""
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

from app import config, rain_rule, trace  # noqa: E402
from app.adapters import zetaris  # noqa: E402
from app.engines.world_model import veda_ingest  # noqa: E402

OUT = ROOT / "docs" / "validation" / "b88_rain_rule.md"
PERIODS = {"nov2024": ("om_rain_nov2024", "2024-11-22 00:00", "2024-12-02 00:00"),
           "oct2024": ("om_rain_oct2024", "2024-10-01 00:00", "2024-10-15 00:00")}
POINTS_SQL = "SELECT location_id, point_key, station_key, name FROM veda_pg.rain_points"
# Reported river readings VEDA may use for Nov 2024 (news, cited - data/replay/nov2024_anchors.csv); for the Sg.
# Kelantan towns there are none, so the lead time before Alert / Danger cannot be measured from VEDA's own data.
CROSSINGS = {"rantau_panjang": "first report 26 Nov 08:00 already above Alert (8.27 m, Alert 7.0) and Warning (8.0); "
                               "above Danger (9.0) by 27 Nov 19:30 (10.94 m) - exact crossing times not reported"}


def hourly_sql(table):
    return (f"SELECT COALESCE(r.location_id, 0) AS location_id, t AS hour_myt, "
            f"CAST(r.hourly.precipitation[i] AS DOUBLE) AS rain_mm FROM veda_wx.{table} r "
            f"LATERAL VIEW posexplode(r.hourly.time) h AS i, t")


def load(table):
    q = lambda sql, what, limit=1000: zetaris.run_sql(sql, agent="Validation", purpose=what, limit=limit).records  # noqa
    rows = q(hourly_sql(table), f"{table}: hourly rain at every point", limit=20000)
    points = {int(p["location_id"]): p for p in q(POINTS_SQL, "rain points")}
    links = q(veda_ingest.LINKS_SQL, "station links")
    places = q(veda_ingest.PLACES_SQL, "places and their gauges")
    rivers = {str(s["station_key"]): s.get("river") or "" for s in q(veda_ingest.STATIONS_SQL, "gauges")}
    hours = defaultdict(list)
    for r in rows:
        t = datetime.strptime(r["hour_myt"], "%Y-%m-%dT%H:%M").replace(tzinfo=config.MYT)
        hours[points[int(r["location_id"])]["point_key"]].append((t, r["rain_mm"]))
    towns = {}
    for r in places:
        town = towns.setdefault(r["place_id"], {"name": r["name"], "controlling": [], "rain_point": None})
        town["rain_point"] = points[int(r["rain_location_id"])]["point_key"]
        if r["role"] in ("controlling", "controlling_secondary"):
            town["controlling"].append((r["role"] != "controlling", str(r["station_key"])))
    for t in towns.values():
        t["controlling"] = [k for _, k in sorted(t["controlling"])]
        t["golok"] = any("Golok" in rivers.get(k, "") for k in t["controlling"])
    meta = {p["point_key"]: {"name": p["name"], "station_key": p["station_key"]} for p in points.values()}
    return hours, meta, links, towns


def run(period):
    table, start, end = PERIODS[period]
    hours, meta, links, towns = load(table)
    t0 = datetime.strptime(start, "%Y-%m-%d %H:%M").replace(tzinfo=config.MYT)
    t1 = datetime.strptime(end, "%Y-%m-%d %H:%M").replace(tzinfo=config.MYT)
    out = {pid: {"name": t["name"], "upstream": [], "combined": [], "local": [], "golok": t["golok"],
                 "no_upstream": None} for pid, t in towns.items()}
    now = t0
    while now < t1:
        pts = {k: {**meta[k], "features": rain_rule.features([(t, mm) for t, mm in hs if t <= now], now)}
               for k, hs in hours.items()}                       # no hindsight: nothing after `now`
        for pid, t in towns.items():
            a = rain_rule.assess(t["controlling"], t["rain_point"], pts, links, golok=t["golok"])
            o = out[pid]
            o["no_upstream"] = a["no_upstream_points"]
            if a["heavy_upstream"]:
                o["upstream"].append((now, a["heavy_upstream"], a["window_known"]))
            if a["combined"]:
                o["combined"].append((now, a["arriving_24h"]))
            if a["local"] and a["local"]["heavy"]:
                o["local"].append(now)
        now += timedelta(hours=1)
    return out


def episodes(times):
    """Contiguous runs of hourly fires -> [(first, last)]."""
    eps = []
    for t in times:
        if eps and t - eps[-1][1] == timedelta(hours=1):
            eps[-1][1] = t
        else:
            eps.append([t, t])
    return eps


def fmt(t):
    return t.strftime("%d %b %H:%M")


def report(results):
    lines = ["# B-88 rain rule - validation on real Open-Meteo archive rain", "",
             f"Generated by `scripts/validate_rain_rule.py` on {datetime.now(config.MYT):%d %b %Y %H:%M} MYT through "
             "Zetaris (`veda_wx.om_rain_nov2024`, `veda_wx.om_rain_oct2024`; Open-Meteo, CC BY 4.0). Hour by hour, "
             "**no hindsight**: at each hour only the rain up to that hour is used. An archive has no forecasts, so only "
             "rain that has fallen counts (live, forecast hours also count). Numbers as set by Cowork 24 Oct, "
             f"tentative, **not tuned to these results**: heavy upstream = 72 h >= {rain_rule.UPSTREAM_72H_MM:g} mm or "
             f"24 h >= {rain_rule.UPSTREAM_24H_MM:g} mm at an upstream rain point; heavy local = >= "
             f"{rain_rule.LOCAL_12H_MM:g} mm in 12 h at the town's rain point; combined = heavy upstream with a known "
             f"window starting within {rain_rule.ARRIVAL_WITHIN_H:g} h + heavy local.", ""]
    for period, title in (("nov2024", "Nov 2024 flood, 22 Nov 00:00 -> 2 Dec 00:00 MYT"),
                          ("oct2024", "Ordinary rain, 1 Oct 00:00 -> 15 Oct 00:00 MYT (14 days)")):
        lines += [f"## {title}", "", "| Town | Upstream rule (>= Keep watching): first fires | hours firing | "
                  "episodes | Combined (+1 level): first fires | hours | Heavy local rain: hours |",
                  "|---|---|---|---|---|---|---|"]
        for pid, o in sorted(results[period].items()):
            up, comb = [t for t, *_ in o["upstream"]], [t for t, _ in o["combined"]]
            first_up = (f"{fmt(up[0])} ({', '.join(o['upstream'][0][1])}; window "
                        f"{'known' if o['upstream'][0][2] else 'not known'})") if up else "never"
            first_c = f"{fmt(comb[0])} (via {', '.join(o['combined'][0][1])})" if comb else "never"
            note = " - no upstream rain point (Thailand not checked)" if o["no_upstream"] else ""
            lines.append(f"| {o['name']}{note} | {first_up} | {len(up)} | {len(episodes(up))} | {first_c} | {len(comb)} "
                         f"| {len(o['local'])} |")
        lines.append("")
        if period == "nov2024":
            lines += ["**Lead time before the river crossed Alert / Danger:** "
                      + "; ".join(f"{results['nov2024'][k]['name']}: {v}" for k, v in CROSSINGS.items())
                      + ". For Pasir Mas, Kota Bharu and Tumpat VEDA holds no Nov 2024 river readings (JPS archives are "
                        "not redistributed, B-75), so the lead time cannot be measured from VEDA's data - a cited "
                        "crossing time (JPS / news) is needed to complete this.", ""]
    return "\n".join(lines) + "\n"


def main():
    load_dotenv(ROOT / ".env")
    if config.sample_mode():
        print("Run live (SAMPLE_MODE=false): the validation reads the archive tables through Zetaris.")
        return 1
    trace.start_run("validate B-88 rain rule", quiet=True)
    try:
        results = {p: run(p) for p in PERIODS}
    finally:
        trace.end_run("success")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(report(results), encoding="utf-8", newline="\n")
    print(OUT.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
