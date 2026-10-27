"""Seed historic flood peaks (B-55) from data/historic_peaks.csv into veda-pg. Idempotent: safe to re-run.

    python scripts/seed_peaks.py              # validate, seed, print the "bigger than 2014?" lines via Zetaris
    python scripts/seed_peaks.py --check-only # validate only

Every row cites its own source URL. Official JPS figures (source_type=official) and news-reported figures
(source_type=news) are kept apart; news values for the same event may disagree - that is shown, not hidden.
"""
import argparse
import csv
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app import config, trace  # noqa: E402
from app.adapters import pg, zetaris  # noqa: E402

PEAKS = ROOT / "data" / "historic_peaks.csv"
AGENT = "Setup"
SOURCE_TYPES = {"official", "news"}
NUMBER_COLS = ("peak_m", "normal_m", "alert_m", "warning_m", "danger_m")


def load_rows(path=PEAKS):
    with Path(path).open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def _num(value):
    return float(value) if value != "" else None


def validate_peaks(rows, known_keys):
    """Problems with the peaks file (empty list = OK)."""
    problems, seen = [], set()
    for i, r in enumerate(rows, 2):
        where = f"line {i} ({r.get('station_key', '?')}, {r.get('event', '?')})"
        if r.get("station_key") not in known_keys:
            problems.append(f"{where}: station_key not in the stations table")
        if not r.get("event"):
            problems.append(f"{where}: event is empty")
        if (r.get("station_key"), r.get("event")) in seen:
            problems.append(f"{where}: duplicate station_key + event")
        seen.add((r.get("station_key"), r.get("event")))
        if r.get("source_type") not in SOURCE_TYPES:
            problems.append(f"{where}: source_type must be official or news")
        u = urlparse(r.get("source_url", ""))
        if u.scheme != "https" or not u.netloc:
            problems.append(f"{where}: source_url must be a full https URL")
        if not r.get("source_name"):
            problems.append(f"{where}: source_name is empty")
        for col in NUMBER_COLS:
            try:
                v = _num(r.get(col, ""))
            except ValueError:
                problems.append(f"{where}: {col} is not a number")
                continue
            if col == "peak_m" and v is None:
                problems.append(f"{where}: peak_m is required")
            elif v is not None and not -50 <= v <= 1000:
                problems.append(f"{where}: {col} {v} is outside -50..1000 m")
    return problems


def known_station_keys():
    with pg.transaction() as conn:
        return {r[0] for r in conn.execute("SELECT station_key FROM stations")}


def seed(rows):
    """Replace all peaks with the CSV in one transaction. Returns the row count."""
    with pg.transaction() as conn:
        conn.execute("DELETE FROM historic_peaks")
        for r in rows:
            conn.execute(
                """INSERT INTO historic_peaks (station_key, event, peak_m, source_url, reconstructed, observed_when,
                       source_type, source_name, normal_m, alert_m, warning_m, danger_m, notes)
                   VALUES (%s, %s, %s, %s, false, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (r["station_key"], r["event"], _num(r["peak_m"]), r["source_url"], r["observed_when"] or None,
                 r["source_type"], r["source_name"], _num(r["normal_m"]), _num(r["alert_m"]), _num(r["warning_m"]),
                 _num(r["danger_m"]), r["notes"] or None))
    return len(rows)


# "Bigger than 2014?" for the core stations: latest level vs the official Dec 2014 peak, through Zetaris.
COMPARE_SQL = """
SELECT s.brief_name, l.level_m, l.observed_at, p.peak_m, p.observed_when, p.source_name
FROM veda_pg.stations s
JOIN veda_pg.historic_peaks p ON p.station_key = s.station_key AND p.event = 'Dec 2014' AND p.source_type = 'official'
LEFT JOIN (SELECT station_key, level_m, observed_at,
                  ROW_NUMBER() OVER (PARTITION BY station_key ORDER BY observed_at DESC) AS rn
           FROM veda_pg.river_levels) l ON l.station_key = s.station_key AND l.rn = 1
WHERE s.is_core = true
ORDER BY s.chain, s.chain_order
"""


def _myt(utc_text):
    """Zetaris returns timestamps as UTC text without a zone ('2026-10-22 08:45:00.0') -> '22 Oct 16:45 MYT'."""
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(str(utc_text).split(".")[0]).replace(tzinfo=timezone.utc)
    except ValueError:
        return f"{utc_text} UTC"
    return dt.astimezone(config.MYT).strftime("%d %b %H:%M MYT")


def compare_lines():
    """One plain sentence per core station, e.g. 'Sg Golok @ Rantau Panjang: [JPS reading] m (reading [date, time] MYT) -
    [distance] m below ...'. The reading time is always shown: a gauge can stop reporting, and "now" would then be a lie.
    (Whether a reading is too old to use is the Critic's call - freshness limits are still KIV.)"""
    rows = zetaris.run_sql(COMPARE_SQL, agent=AGENT, purpose="bigger than 2014? (core stations)").rows
    lines = []
    for name, level, observed_at, peak, when, source in rows:
        if level is None:
            lines.append(f"{name}: no current reading - Dec 2014 peak was {peak:.2f} m ({when}; {source})")
            continue
        diff = level - peak
        relation = (f"{abs(diff):.2f} m below" if diff < 0 else f"{diff:.2f} m ABOVE")
        lines.append(f"{name}: {level:.2f} m (reading {_myt(observed_at)}) - {relation} the Dec 2014 peak of "
                     f"{peak:.2f} m ({when}; {source})")
    return lines


def main(argv=None):
    """Validate, seed, then print the comparison lines; every step traced."""
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Seed data/historic_peaks.csv into veda-pg")
    ap.add_argument("--check-only", action="store_true", help="validate only, write nothing")
    args = ap.parse_args(argv)
    if config.sample_mode():
        print("SAMPLE_MODE is on - seeding is for live mode only.")
        return 1
    trace.start_run("seed historic peaks (B-55)")
    try:
        rows = load_rows()
        problems = validate_peaks(rows, known_station_keys())
        trace.step(AGENT, "peaks.validate", output_summary=f"{len(rows)} rows; {len(problems)} problem(s)",
                   status="failed" if problems else "success", details={"problems": problems[:20]})
        if problems:
            trace.end_run("failed", f"{len(problems)} problem(s) in {PEAKS.name}")
            print("\n".join(problems))
            return 1
        if args.check_only:
            trace.end_run("success", "CSV valid (check only, nothing written)")
            return 0
        n = seed(rows)
        trace.step(AGENT, "pg.seed", output_summary=f"{n} historic peaks written", source="veda-pg")
        lines = compare_lines()
        trace.step(AGENT, "compare_2014", output_summary=f"{len(lines)} core stations compared",
                   decision="'Bigger than 2014?' works through Zetaris", details={"lines": lines})
        print("\n".join(lines))
    except (pg.PgError, zetaris.ZetarisError, OSError, KeyError, ValueError) as e:
        trace.end_run("failed", f"{type(e).__name__}: {e}")
        print(f"SEED FAILED: {type(e).__name__}: {trace.redact(str(e))}")
        return 1
    trace.end_run("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
