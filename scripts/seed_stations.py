"""Seed the curated station mapping (B-67) from data/stations_mapping.csv into veda-pg. Idempotent: safe to re-run.

    python scripts/seed_stations.py              # validate, seed, check through Zetaris
    python scripts/seed_stations.py --check-only # validate the CSV against the stations table, write nothing

The CSV is the single source of truth: Dr Ariff reviews/corrects it, then this script re-seeds. Each run first clears
every curated column and all station_links, then writes the CSV - so a row removed from the CSV disappears from the DB.
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app import config, trace  # noqa: E402
from app.adapters import pg, zetaris  # noqa: E402

MAPPING = ROOT / "data" / "stations_mapping.csv"
AGENT = "Setup"
LINK_TYPES = {"upstream_of", "backup_for", "travel_time"}
KELANTAN_BOX = (4.5, 6.4, 101.3, 102.8)      # lat min, lat max, lon min, lon max (generous)
CURATED = ["brief_name", "chain", "chain_order", "role", "controls_town", "backup_of", "mapping_status",
           "mapping_note", "coords_source"]


def load_rows(path=MAPPING):
    """CSV rows as dicts (all values stripped strings)."""
    with Path(path).open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def _num(value):
    return float(value) if value != "" else None


def validate_mapping(rows, known_keys):
    """Return a list of problems (empty = OK). known_keys: station_keys present in the stations table."""
    problems = []
    gauges = [r for r in rows if r.get("record_type") == "gauge"]
    links = [r for r in rows if r.get("record_type") == "link"]
    for i, r in enumerate(rows, 2):           # line 1 is the header
        if r.get("record_type") not in ("gauge", "link"):
            problems.append(f"line {i}: record_type must be gauge or link")
    keys = [g["station_key"] for g in gauges]
    gauge_keys = set(keys)
    if len(keys) != len(gauge_keys):
        problems.append("duplicate gauge station_key")
    for g in gauges:
        k = g["station_key"]
        if k not in known_keys:
            problems.append(f"gauge {k}: not in the stations table (run the JPS collector first?)")
        if not g.get("status"):
            problems.append(f"gauge {k}: status is empty")
        if g.get("is_core") not in ("yes", "no"):
            problems.append(f"gauge {k}: is_core must be yes or no")
        if g.get("chain_order") and not g["chain_order"].isdigit():
            problems.append(f"gauge {k}: chain_order must be a whole number")
        if bool(g.get("lat")) != bool(g.get("lon")):
            problems.append(f"gauge {k}: lat and lon must both be set or both empty")
        elif g.get("lat"):
            try:
                lat, lon = float(g["lat"]), float(g["lon"])
                if not (KELANTAN_BOX[0] <= lat <= KELANTAN_BOX[1] and KELANTAN_BOX[2] <= lon <= KELANTAN_BOX[3]):
                    problems.append(f"gauge {k}: coordinates {lat},{lon} are outside Kelantan")
            except ValueError:
                problems.append(f"gauge {k}: lat/lon are not numbers")
        if g.get("backup_of") and g["backup_of"] not in gauge_keys:
            problems.append(f"gauge {k}: backup_of {g['backup_of']} is not a gauge in this file")
    seen = set()
    for link in links:
        a, b, kind = link.get("from_key"), link.get("to_key"), link.get("link_type")
        name = f"link {a} -> {b} ({kind})"
        if a not in gauge_keys or b not in gauge_keys:
            problems.append(f"{name}: both ends must be gauges in this file")
        if a == b:
            problems.append(f"{name}: a gauge cannot link to itself")
        if kind not in LINK_TYPES:
            problems.append(f"{name}: link_type must be one of {sorted(LINK_TYPES)}")
        if (a, b, kind) in seen:
            problems.append(f"{name}: duplicate link")
        seen.add((a, b, kind))
        if not link.get("status"):
            problems.append(f"{name}: status is empty")
        try:
            lo, hi = _num(link.get("lag_min_h", "")), _num(link.get("lag_max_h", ""))
            if lo is not None and hi is not None and lo > hi:
                problems.append(f"{name}: lag_min_h > lag_max_h")
            if (lo is not None and lo < 0) or (hi is not None and hi < 0):
                problems.append(f"{name}: lags cannot be negative")
        except ValueError:
            problems.append(f"{name}: lags are not numbers")
    # upstream_of must not loop
    down = {}
    for link in links:
        if link.get("link_type") == "upstream_of":
            down.setdefault(link["from_key"], []).append(link["to_key"])

    def loops_from(node, path):
        for nxt in down.get(node, []):
            if nxt in path or loops_from(nxt, path | {nxt}):
                return True
        return False

    if any(loops_from(k, {k}) for k in down):
        problems.append("upstream_of links form a loop")
    return problems


def known_station_keys():
    with pg.transaction() as conn:
        return {r[0] for r in conn.execute("SELECT station_key FROM stations")}


def seed(rows):
    """Clear curated data, write the CSV. One transaction. Returns (gauges, links)."""
    gauges = [r for r in rows if r["record_type"] == "gauge"]
    links = [r for r in rows if r["record_type"] == "link"]
    with pg.transaction() as conn:
        conn.execute("DELETE FROM station_links")
        conn.execute("UPDATE stations SET is_core = false, " + ", ".join(f"{c} = NULL" for c in CURATED))
        for g in gauges:
            conn.execute(
                """UPDATE stations SET brief_name = %s, is_core = %s, chain = %s, chain_order = %s, role = %s,
                     controls_town = %s, backup_of = %s, mapping_status = %s, mapping_note = %s,
                     lat = COALESCE(%s, lat), lon = COALESCE(%s, lon), coords_source = %s
                   WHERE station_key = %s""",
                (g["brief_name"] or None, g["is_core"] == "yes", g["chain"] or None,
                 int(g["chain_order"]) if g["chain_order"] else None, g["role"] or None, g["controls_town"] or None,
                 g["backup_of"] or None, g["status"], g["notes"] or None, _num(g["lat"]), _num(g["lon"]),
                 g["coords_source"] or None, g["station_key"]))
        for link in links:
            conn.execute(
                """INSERT INTO station_links (from_key, to_key, link_type, lag_min_h, lag_max_h, lag_source, status, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (link["from_key"], link["to_key"], link["link_type"], _num(link["lag_min_h"]), _num(link["lag_max_h"]),
                 link["lag_source"] or None, link["status"], link["notes"] or None))
    return len(gauges), len(links)


def check_via_zetaris():
    """Read the core stations and their links back through Zetaris, as agents will."""
    core = zetaris.run_sql("SELECT station_key, brief_name, mapping_status FROM veda_pg.stations WHERE is_core = true "
                           "ORDER BY chain, chain_order", agent=AGENT, purpose="core stations via Zetaris")
    links = zetaris.run_sql("SELECT link_type, COUNT(*) AS n FROM veda_pg.station_links GROUP BY link_type ORDER BY 1",
                            agent=AGENT, purpose="station links via Zetaris")
    return core.rows, dict((r[0], r[1]) for r in links.rows)


def main(argv=None):
    """Validate, seed and check; every step traced."""
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Seed data/stations_mapping.csv into veda-pg")
    ap.add_argument("--check-only", action="store_true", help="validate only, write nothing")
    args = ap.parse_args(argv)
    if config.sample_mode():
        print("SAMPLE_MODE is on - seeding is for live mode only.")
        return 1
    trace.start_run("seed station mapping (B-67)")
    try:
        rows = load_rows()
        problems = validate_mapping(rows, known_station_keys())
        trace.step(AGENT, "mapping.validate", input_summary=MAPPING.name,
                   output_summary=f"{len(rows)} rows; {len(problems)} problem(s)",
                   status="failed" if problems else "success", details={"problems": problems[:20]})
        if problems:
            trace.end_run("failed", f"{len(problems)} problem(s) in {MAPPING.name}")
            print("\n".join(problems))
            return 1
        if args.check_only:
            trace.end_run("success", "CSV valid (check only, nothing written)")
            return 0
        n_gauges, n_links = seed(rows)
        trace.step(AGENT, "pg.seed", output_summary=f"{n_gauges} gauges curated, {n_links} links written",
                   source="veda-pg", decision="Curated columns and links replaced from the CSV in one transaction")
        core, link_counts = check_via_zetaris()
        trace.step(AGENT, "zetaris.check", output_summary=f"{len(core)} core stations; links {link_counts}",
                   decision="Mapping readable through Zetaris")
    except (pg.PgError, zetaris.ZetarisError, OSError, KeyError, ValueError) as e:
        trace.end_run("failed", f"{type(e).__name__}: {e}")
        print(f"SEED FAILED: {type(e).__name__}: {trace.redact(str(e))}")
        return 1
    trace.end_run("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
