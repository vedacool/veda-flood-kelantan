"""Build a flood replay (B-70) from verified readings into veda-pg. Idempotent: safe to re-run.

    python scripts/build_replay.py              # validate the anchors, rebuild the scenario, check it via Zetaris
    python scripts/build_replay.py --check-only # validate only

Anchors (data/replay/<scenario>_anchors.csv) are real JPS readings quoted by a cited news report - each with its
source URL, the quoted sentence and whether its time is exact or approximate. Method (approved 22 Oct night):
    reported       every anchor, as written
    reconstructed  every whole hour strictly BETWEEN two consecutive anchors of the same gauge, on a straight line
                   - never before the first anchor, never after the last, never for a gauge with one anchor
Every row carries its label, e.g. "reconstructed between the verified JPS readings 8.41 m (26 Nov ~18:00) and
10.94 m (27 Nov 2024 19:30)", shown verbatim in the trace and the answer card. Zetaris reads the table.
"""
import argparse
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app import config, trace  # noqa: E402
from app.adapters import pg, zetaris  # noqa: E402

ANCHORS = ROOT / "data" / "replay" / "nov2024_anchors.csv"
SYNTHETIC_LABEL = "SYNTHETIC reading - made up for the offline demo, not a real JPS reading"
AGENT = "Setup"
TIME_FORMAT = "%Y-%m-%d %H:%M"


def load_rows(path=ANCHORS):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def _time(text):
    return datetime.strptime(text, TIME_FORMAT).replace(tzinfo=config.MYT)


def validate(rows, known_keys):
    """Problems with the anchors file (empty list = OK)."""
    problems, last = [], {}
    for i, r in enumerate(rows, start=2):
        where = f"line {i} ({r.get('station_key')})"
        if not r.get("scenario"):
            problems.append(f"{where}: no scenario")
        if r.get("station_key") not in known_keys:
            problems.append(f"{where}: unknown station_key")
        try:
            t = _time(r.get("observed_at_myt", ""))
        except ValueError:
            problems.append(f"{where}: observed_at_myt must be '{TIME_FORMAT}' (MYT)")
            t = None
        if r.get("time_exact") not in ("true", "false"):
            problems.append(f"{where}: time_exact must be true or false")
        try:
            float(r.get("level_m", ""))
        except ValueError:
            problems.append(f"{where}: level_m is not a number")
        if r.get("scenario", "").startswith("synthetic_"):        # B-75: made-up readings, labelled SYNTHETIC
            if r.get("source_name") != "SYNTHETIC":
                problems.append(f"{where}: a synthetic scenario's rows must say source_name SYNTHETIC")
        else:
            if urlparse(r.get("source_url", "")).scheme != "https":
                problems.append(f"{where}: source_url must be https")
            if not r.get("quote") or not r.get("source_name"):
                problems.append(f"{where}: every anchor needs its source_name and the quoted sentence")
        key = (r.get("scenario"), r.get("station_key"))
        if t is not None and key in last and t <= last[key]:
            problems.append(f"{where}: readings of one gauge must be in time order")
        if t is not None:
            last[key] = t
    return problems


def _when(t, exact):
    """'27 Nov 2024 19:30' (exact) or '26 Nov ~18:00' (approximate) - the wording approved 22 Oct night."""
    return t.strftime("%d %b %Y %H:%M") if exact else t.strftime("%d %b ~%H:%M")


def reconstruct(rows):
    """Anchors -> replay rows (reported + reconstructed), sorted by gauge and time."""
    by_gauge = {}
    for r in rows:
        by_gauge.setdefault((r["scenario"], r["station_key"]), []).append(
            {**r, "t": _time(r["observed_at_myt"]), "level": float(r["level_m"]), "exact": r["time_exact"] == "true"})
    out = []
    for (scenario, key), anchors in by_gauge.items():
        anchors.sort(key=lambda a: a["t"])
        for a in anchors:
            out.append({"scenario": scenario, "station_key": key, "observed_at": a["t"], "level_m": a["level"],
                        "kind": "reported", "time_exact": a["exact"], "source_url": a["source_url"],
                        "label": SYNTHETIC_LABEL if a["source_name"] == "SYNTHETIC" else
                                 f"reported JPS reading ({a['source_name']})"
                                 + ("" if a["exact"] else "; time approximate")})
        for a, b in zip(anchors, anchors[1:]):
            label = (SYNTHETIC_LABEL if a["source_name"] == "SYNTHETIC" else
                     f"reconstructed between the verified JPS readings {a['level']:g} m ({_when(a['t'], a['exact'])})"
                     f" and {b['level']:g} m ({_when(b['t'], b['exact'])})")
            span = (b["t"] - a["t"]).total_seconds()
            t = a["t"].replace(minute=0) + timedelta(hours=1)
            while t < b["t"]:
                frac = (t - a["t"]).total_seconds() / span
                out.append({"scenario": scenario, "station_key": key, "observed_at": t,
                            "level_m": round(a["level"] + (b["level"] - a["level"]) * frac, 2),
                            "kind": "reconstructed", "time_exact": a["exact"] and b["exact"], "label": label,
                            "source_url": " ; ".join(dict.fromkeys([a["source_url"], b["source_url"]]))})
                t += timedelta(hours=1)
    return sorted(out, key=lambda r: (r["scenario"], r["station_key"], r["observed_at"]))


def known_station_keys():
    with pg.transaction() as conn:
        return {r[0] for r in conn.execute("SELECT station_key FROM stations")}


def seed(rows):
    """Replace each scenario's rows in one transaction. Returns the row count."""
    with pg.transaction() as conn:
        for scenario in {r["scenario"] for r in rows}:
            conn.execute("DELETE FROM replay_levels WHERE scenario = %s", (scenario,))
        for r in rows:
            conn.execute("""INSERT INTO replay_levels (scenario, station_key, observed_at, level_m, kind, time_exact,
                                                       label, source_url)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                         (r["scenario"], r["station_key"], r["observed_at"], r["level_m"], r["kind"], r["time_exact"],
                          r["label"], r["source_url"]))
    return len(rows)


CHECK_SQL = ("SELECT scenario, station_key, kind, COUNT(*) AS n, MIN(level_m) AS lo, MAX(level_m) AS hi "
             "FROM veda_pg.replay_levels GROUP BY scenario, station_key, kind ORDER BY scenario, station_key, kind")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--anchors", default=str(ANCHORS))
    args = ap.parse_args(argv)
    load_dotenv(ROOT / ".env")
    trace.start_run(f"build replay from {Path(args.anchors).name}")
    try:
        anchors = load_rows(args.anchors)
        problems = validate(anchors, known_station_keys())
        if problems:
            trace.step(AGENT, "replay.validate", output_summary=f"{len(problems)} problem(s)", status="failed",
                       decision="; ".join(problems[:5]))
            print("\n".join(problems))
            trace.end_run("failed")
            return 1
        rows = reconstruct(anchors)
        trace.step(AGENT, "replay.validate", output_summary=f"{len(anchors)} anchors -> {len(rows)} rows "
                   f"({sum(r['kind'] == 'reconstructed' for r in rows)} reconstructed)",
                   decision="straight line between consecutive verified readings only")
        if args.check_only:
            trace.end_run()
            return 0
        n = seed(rows)
        trace.step(AGENT, "replay.seed", output_summary=f"{n} rows written to replay_levels")
        for row in zetaris.run_sql(CHECK_SQL, agent=AGENT, purpose="replay check through Zetaris").rows:
            print(row)
        trace.end_run()
        return 0
    except (pg.PgError, zetaris.ZetarisError) as e:
        trace.end_run("failed", str(e))
        print(f"FAILED: {trace.redact(str(e))}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
