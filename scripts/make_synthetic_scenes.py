"""B-75: every SYNTHETIC value VEDA ships, made from cited facts only - never from real JPS readings or their patterns.

    python scripts/make_synthetic_scenes.py            # rewrite all four outputs (same seed -> same values)
    python scripts/make_synthetic_scenes.py --check    # fail if a committed output differs from what the method makes

Inputs (cited facts): each gauge's official JPS thresholds Normal / Waspada (Alert) / Amaran (Warning) / Bahaya
(Danger) and its place in the river chain (data/stations_mapping.csv), the Dec 2014 peaks (data/historic_peaks.csv),
and the cited travel times between gauges (link rows in data/stations_mapping.csv).

Method (seeded, SEED below):
- calm: every gauge below Waspada - Normal + u * (Waspada - Normal), u in [-0.15, 0.25], then small noise (+-0.03 m)
  between readings 3 hours apart; tide-influenced gauges swing +-0.1 m.
- rising: every gauge climbs 0.1-0.3 m/h (tidal 0.05-0.1 m/h). Upstream gauges are further into the rise than
  downstream ones: progress p falls down each chain (0.85 at the top, 0.25 at the bottom) and, where a cited travel
  time from Kuala Krai exists, by lag/30 below Kuala Krai's. Level at the scene time = Waspada + p * (Bahaya -
  Waspada), kept below the Dec 2014 peak (minus 0.3 m) where one is cited.
- reading times: the scene's own times, or (live-path test fixtures) the fixture clock minus 10-40 seeded minutes.

Outputs (all labelled SYNTHETIC):
1. data/replay/synthetic_anchors.csv            - the SYNTHETIC calm / rising / silent-upstream scenes (seed into veda_pg with
                                                   scripts/build_replay.py --anchors ..., then record fixtures)
2. data/fixtures/zetaris/<jps-table queries>.json - the offline live-path test fixtures (flag "synthetic": true)
3. data/fixtures/zetaris/<flood-warning>.json   - data.gov.my /flood-warning rows for the mapped gauges; the feed's
                                                   documented frozen date (23 Feb 2024) is kept, the levels are made up
   data/fixtures/zetaris/<MET warnings / forecast> - MetMalaysia warnings and today's forecast text, made up (live mode
                                                   still reads the real MetMalaysia data at runtime)
4. tests/fixtures/jps_synthetic_page.html        - a page in the JPS Infobanjir table structure for the parser tests
"""
import argparse
import csv
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 7524
FIXTURES = ROOT / "data" / "fixtures" / "zetaris"
ANCHORS = ROOT / "data" / "replay" / "synthetic_anchors.csv"
PAGE = ROOT / "tests" / "fixtures" / "jps_synthetic_page.html"
SCENES = {"synthetic_calm": ("2024-06-15", ("04:00", "07:00", "10:00"), "calm"),
          "synthetic_rising": ("2024-11-25", ("12:00", "15:00", "18:00"), "rising")}
FROZEN_FEED = "2024-02-23 14:45:00"     # data.gov.my /flood-warning stopped updating then (documented, README)
NOTE = ("SYNTHETIC values (B-75): made by scripts/make_synthetic_scenes.py from cited thresholds, 2014 peaks and "
        "travel times - not JPS readings.")
MYT = timezone(timedelta(hours=8))


def load_gauges():
    rows = list(csv.DictReader((ROOT / "data" / "stations_mapping.csv").open(encoding="utf-8")))
    num = lambda v: float(v) if v not in (None, "") else None                         # noqa: E731
    gauges = {r["station_key"]: {"key": r["station_key"], "name": r["jps_name"], "chain": r["chain"],
                                 "order": int(r["chain_order"]), "tidal": "tide" in r["role"],
                                 "n": num(r["jps_normal_m"]), "a": num(r["jps_alert_m"]),
                                 "w": num(r["jps_warning_m"]), "d": num(r["jps_danger_m"])}
              for r in rows if r["record_type"] == "gauge"}
    for r in rows:                                                    # cited travel times from Kuala Krai
        if r["record_type"] == "link" and r["link_type"] == "travel_time" and r["lag_min_h"]:
            gauges[r["to_key"]]["lag_from_krai"] = (r["from_key"], float(r["lag_min_h"]))
    peaks = {r["station_key"]: float(r["peak_m"])
             for r in csv.DictReader((ROOT / "data" / "historic_peaks.csv").open(encoding="utf-8"))
             if r["event"] == "Dec 2014"}
    for k, g in gauges.items():
        g["peak2014"] = peaks.get(k)
    return gauges


def progress(gauges):
    """Rising-scene progress per gauge: 0.85 at the top of each chain, 0.25 at the bottom, cited lags on top."""
    chains = {}
    for g in gauges.values():
        chains.setdefault(g["chain"], []).append(g)
    p = {}
    for members in chains.values():
        top, bottom = min(m["order"] for m in members), max(m["order"] for m in members)
        for m in members:
            p[m["key"]] = 0.85 - 0.6 * ((m["order"] - top) / (bottom - top) if bottom > top else 0)
    for g in gauges.values():
        if g.get("lag_from_krai"):
            src, lag = g["lag_from_krai"]
            p[g["key"]] = min(p[g["key"]], p[src] - lag / 30)
    return {k: max(0.15, v) for k, v in p.items()}


def calm_level(g, rnd):
    span = g["a"] - g["n"]
    return round(min(g["n"] + rnd.uniform(-0.15, 0.25) * span, g["a"] - 0.1 * span), 2)


def rising_level(g, p, rnd):
    level = g["a"] + p * (g["d"] - g["a"])
    if g["peak2014"] is not None:
        level = min(level, g["peak2014"] - 0.3)
    rate = rnd.uniform(0.05, 0.1) if g["tidal"] else rnd.uniform(0.1, 0.3)
    return round(level, 2), round(rate, 3)


def scene_rows(gauges, rnd):
    p = progress(gauges)
    out = []
    for name, (day, times, kind) in SCENES.items():
        for g in gauges.values():
            if kind == "calm":
                base = calm_level(g, rnd)
                swing = 0.1 if g["tidal"] else 0.03
                levels = [round(base + rnd.uniform(-swing, swing), 2) for _ in times[:-1]] + [base]
            else:
                end, rate = rising_level(g, p[g["key"]], rnd)
                levels = [round(end - rate * h, 2) for h in (6, 3, 0)]
            for t, lv in zip(times, levels):
                out.append([name, g["key"], f"{day} {t}", "true", lv, "SYNTHETIC", "", "",
                            "made up for the offline demo - not a real JPS reading"])
    return out


# B-71(b): a made-up "silent upstream gauge" scene for the Critic -> Data request. Own seed, so adding it changes no
# other SYNTHETIC value. Calm day everywhere, except: three upstream gauges go silent after 04:00 (their 04:00
# reading is the last one) and Temangan - further up the Kelantan than Pasir Mas's own upstream gauges - is at Amaran
# (Warning) and rising. Rantau Panjang's only upstream gauge (Jenob) is silent too, with nothing further up.
SILENT_SCENE = ("synthetic_silent_upstream", "2024-06-15", ("04:00", "07:00", "10:00"))
SILENT_GAUGES = {"6021065_DPMS0001", "5521044_DKKI0014", "_DTMH0008"}      # Air Mulih, Tangga Krai, Jenob
RISING_GAUGE = "_DMCG0001"                                                 # Temangan


def silent_scene_rows(gauges):
    rnd = random.Random(SEED + 71)
    name, day, times = SILENT_SCENE
    out = []
    for g in gauges.values():
        if g["key"] == RISING_GAUGE:
            end = round(g["w"] + 0.3 * (g["d"] - g["w"]), 2)
            rate = round(rnd.uniform(0.1, 0.2), 3)
            levels = [round(end - rate * h, 2) for h in (6, 3, 0)]
        else:
            base = calm_level(g, rnd)
            swing = 0.1 if g["tidal"] else 0.03
            levels = [round(base + rnd.uniform(-swing, swing), 2) for _ in times[:-1]] + [base]
        for t, lv in list(zip(times, levels))[:1 if g["key"] in SILENT_GAUGES else 3]:
            out.append([name, g["key"], f"{day} {t}", "true", lv, "SYNTHETIC", "", "",
                        "made up for the offline demo - not a real JPS reading"])
    return out


# B-88: "upstream rain arriving during local rain" - every gauge calm (the river alone says Normal); the rain is the
# REAL Open-Meteo archive of 27 Nov 2024 (heavy rain at Kuala Krai, 9-17 h from Kota Bharu, while it rains heavily in
# Kota Bharu), so only the rain rule can raise the verdict. Own seed: no other SYNTHETIC value changes.
RAIN_SCENE = ("synthetic_upstream_rain", "2024-11-27", ("06:00", "09:00", "12:00"))


def rain_scene_rows(gauges):
    rnd = random.Random(SEED + 88)
    name, day, times = RAIN_SCENE
    out = []
    for g in gauges.values():
        base = calm_level(g, rnd)
        swing = 0.1 if g["tidal"] else 0.03
        levels = [round(base + rnd.uniform(-swing, swing), 2) for _ in times[:-1]] + [base]
        for t, lv in zip(times, levels):
            out.append([name, g["key"], f"{day} {t}", "true", lv, "SYNTHETIC", "", "",
                        "made up for the offline demo - not a real JPS reading"])
    return out


def band(g, level):
    for key, name in (("d", "danger"), ("w", "warning"), ("a", "alert"), ("n", "normal")):
        if g[key] is not None and level >= g[key]:
            return name
    return "below_normal"


def live_path_values(gauges, rnd):
    """The offline live-path test fixtures: the Golok chain rising, everything else calm (a designed mix)."""
    p = progress(gauges)
    vals = {}
    for g in gauges.values():
        if g["chain"] == "golok":
            level, rate = rising_level(g, p[g["key"]] - 0.45, rnd)
            vals[g["key"]] = (level, round(rate, 2), round(rate * 3, 2))
        else:
            level = calm_level(g, rnd)
            vals[g["key"]] = (level, round(rnd.uniform(-0.03, 0.03), 2), round(rnd.uniform(-0.06, 0.06), 2))
    return vals


def clock_fixture(folder=FIXTURES):
    """The recorded clock: the fixture whose SQL is exactly the clock query. Other fixtures also contain
    current_timestamp(), and glob order differs between file systems (audit 24 Oct, P1-4: a Linux clone failed)."""
    docs = (json.loads(f.read_text(encoding="utf-8")) for f in sorted(folder.glob("*.json")))
    return next(d for d in docs if " ".join(d.get("sql", "").split()) == "SELECT current_timestamp() AS now_utc")


def write_fixtures(gauges, rnd, check):
    clock_doc = clock_fixture()
    clock =datetime.fromisoformat(str(clock_doc["rows"][0][0]).split(".")[0]).replace(tzinfo=timezone.utc)
    vals = live_path_values(gauges, rnd)
    changed = []
    for path in sorted(FIXTURES.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        sql, cols = " ".join(doc.get("sql", "").split()), doc.get("columns") or []
        new = None
        if "river_status_latest" in sql:
            keys = [r[cols.index("station_key")] for r in doc["rows"]]
            new = [[k, (clock - timedelta(minutes=rnd.randint(10, 40))).strftime("%Y-%m-%d %H:%M:00.0")]
                   for k in keys]
        elif "place_gauge_status" in sql:
            new = []
            for r in doc["rows"]:
                rec = dict(zip(cols, r))
                v = vals.get(rec["station_key"])
                if v is None:
                    new.append(r)
                    continue
                g = gauges[rec["station_key"]]
                rec.update(level_m=str(v[0]), age_minutes=str(rnd.randint(10, 40)), band=band(g, v[0]),
                           change_1h_m=str(v[1]), change_3h_m=str(v[2]))
                new.append([rec[c] for c in cols])
        elif "min_7d_m" in sql:
            new = [[r[0], str(round(vals[r[0]][0] - rnd.uniform(0.1, 0.5), 2)) if r[0] in vals else
                    str(round((gauges.get(r[0]) or {"n": 1.0})["n"] or 1.0, 2))] for r in doc["rows"]]
        elif "veda_pg.river_levels" in sql and "level_m" in cols:
            new = [[r[0], str(vals[r[0]][0]) if r[0] in vals else r[1],
                    (clock - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:00.0")] for r in doc["rows"]]
        elif "mygov_warning" in sql and "heading_en" in cols:
            myt = clock.astimezone(MYT)
            iso = lambda dt: dt.strftime("%Y-%m-%dT%H:00:00")                                # noqa: E731
            issued = iso(myt - timedelta(hours=rnd.randint(2, 6)))
            new = [["SYNTHETIC - SECOND CATEGORY WARNING ON STRONG WINDS AND ROUGH SEAS",
                    "SYNTHETIC warning for the offline tests (sea areas only) - not issued by MetMalaysia.",
                    "Amaran SYNTHETIC untuk ujian luar talian (kawasan laut sahaja) - bukan dikeluarkan oleh "
                    "MetMalaysia.", iso(myt - timedelta(hours=6)), iso(myt + timedelta(hours=48)), issued],
                   ["SYNTHETIC - THUNDERSTORMS WARNING",
                    "SYNTHETIC: thunderstorms and heavy rain over parts of Pahang - made up for the offline tests.",
                    "SYNTHETIC: ribut petir dan hujan lebat di beberapa kawasan di Pahang - direka untuk ujian luar "
                    "talian.", iso(myt - timedelta(hours=2)), iso(myt + timedelta(hours=2)), issued],
                   ["No Advisory", "SYNTHETIC: no tropical cyclone advisory.",
                    "SYNTHETIC: tiada nasihat siklon tropika.", None, None, issued]]
        elif "place_risk_inputs" in sql and "forecast_today" in cols:
            i_f, i_w = cols.index("forecast_today"), cols.index("forecast_today_when")
            phrases = ("Tiada hujan", "Hujan di beberapa tempat", "Ribut petir di beberapa tempat")
            times = ("Pagi", "Petang", "Petang dan Malam", "Malam")
            new = []
            for r in doc["rows"]:                     # Open-Meteo rain values (CC BY 4.0) stay as recorded
                r = list(r)
                if r[i_f] is not None:
                    r[i_f], r[i_w] = f"SYNTHETIC: {rnd.choice(phrases)}", rnd.choice(times)
                new.append(r)
        elif "mygov_flood" in sql and "water_level_current" in cols:
            new = [[g["key"].split("_", 1)[0] if g["key"][0].isdigit() else g["key"],
                    re.sub(r"\s*\(F\d\)$", "", g["name"]), str(calm_level(g, rnd)), FROZEN_FEED]
                   for g in gauges.values()]
        if new is None:
            continue
        doc.update(rows=new, synthetic=True, note=NOTE)
        text = json.dumps(doc, ensure_ascii=False, indent=1)
        if path.read_text(encoding="utf-8") != text:
            changed.append(path.name)
            if not check:
                path.write_text(text, encoding="utf-8")
    return changed


def write_page(rnd, check):
    """The parser-test page: JPS table structure; levels from each row's own thresholds (calm method), times seeded."""
    html = PAGE.read_text(encoding="utf-8")
    body = html.split("-->\n", 1)[1]
    row = re.compile(r"(data-th='Last Update'>)[^<]*(</td><td data-th='wl'>\s*<a [^>]*>\s*)([^<]*)(</a></td>"
                     r"<td data-th='Normal'>)([-\d.]*)(</td><td data-th='Alert'>)([-\d.]*)")

    def fix(m):
        n, a = m.group(5), m.group(7)
        level = m.group(3).strip()
        if n and a and level not in ("", "-", "N/A"):
            g = {"n": float(n), "a": float(a)}
            level = f"{calm_level(g, rnd):.2f}"
        t = f"01/01/2026 {rnd.randint(6, 11):02d}:{rnd.choice((0, 15, 30, 45)):02d}"
        return f"{m.group(1)}{t}{m.group(2)}{level}{m.group(4)}{n}{m.group(6)}{a}"
    banner = ("<!-- SYNTHETIC test page (B-75): JPS Infobanjir table structure with the cited thresholds; every water "
              "level and time is made up by scripts/make_synthetic_scenes.py (calm method, seeded). Not a JPS "
              "reading - JPS readings are never stored in this repo. -->\n")
    text = banner + row.sub(fix, body)
    if text != html and not check:
        PAGE.write_text(text, encoding="utf-8", newline="")
    return [PAGE.name] if text != html else []


def write_discover_fixture(check):
    """B-71(c): SAMPLE_MODE's discovery query finds ONE made-up unmapped gauge, labelled SYNTHETIC (live mode finds the
    real unmapped JPS gauges at runtime)."""
    sys.path.insert(0, str(ROOT))
    from app.adapters.zetaris import query_hash
    from app.agents.data_agent import DISCOVER_SQL
    doc = {"sql": DISCOVER_SQL, "query_hash": query_hash(DISCOVER_SQL), "recorded_at": "2026-10-24T00:00:00Z",
           "columns": ["station_key", "name", "river", "district"],
           "rows": [["_SYN0001", "Sg. Kelantan di Kg. Contoh (SYNTHETIC)", "Sg. Kelantan", "Pasir Mas"]],
           "synthetic": True, "note": NOTE + " One made-up unmapped gauge for the discovery step (B-71c)."}
    path = FIXTURES / f"{doc['query_hash']}.json"
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return []
    if not check:
        path.write_text(text, encoding="utf-8")
    return [path.name]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only report outputs that differ from the method")
    args = ap.parse_args(argv)
    gauges = load_gauges()
    rnd = random.Random(SEED)
    rows = scene_rows(gauges, rnd) + silent_scene_rows(gauges) + rain_scene_rows(gauges)   # own seeds
    lines = ["scenario,station_key,observed_at_myt,time_exact,level_m,source_name,source_url,quote,note"]
    lines += [",".join(str(x) for x in r) for r in rows]
    text = "\n".join(lines) + "\n"
    changed = [ANCHORS.name] if ANCHORS.read_text(encoding="utf-8") != text else []
    if changed and not args.check:
        ANCHORS.write_text(text, encoding="utf-8", newline="")
    changed += write_fixtures(gauges, rnd, args.check)
    # B-101: the parser-test page has its own seed (its old shared-seed draw happened to equal a private live reading);
    # no other output changes
    changed += write_page(random.Random(SEED + 106), args.check)
    changed += write_discover_fixture(args.check)
    print(("differs: " if args.check else "written: ") + (", ".join(changed) or "nothing"))
    return 1 if (args.check and changed) else 0


if __name__ == "__main__":
    sys.exit(main())
