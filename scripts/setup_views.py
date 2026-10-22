"""Create VEDA's Zetaris views (B-08) from db/views/*.sql. Idempotent: safe to re-run (CREATE OR REPLACE).

    python scripts/setup_views.py

Views live in SchemaStore container `veda` and are read as veda.<view>:
    river_status_latest   one row per JPS gauge: latest level, reading time + age, band vs thresholds, change 1 h / 3 h
    rain_24h_by_point     one row per rain point: rain past 24 h / 7 d, next 24 h / 72 h, max probability next 24 h
    forecast_kelantan     one row per Kelantan place (state / district / town) per day: MetMalaysia forecast
    station_risk_inputs   one row per core station: the three above fused
    place_risk_inputs     one row per covered place (B-09): controlling gauge + nearest rain + town forecast
    place_gauge_status    one row per place x gauge (controlling, secondary, sentinels) + travel time if known
Each view file holds one read-only SELECT; it is checked with the same rule as run_sql before it is created.
Needs: scripts/setup_pg.py, seed_stations.py and setup_wx.py run first.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from app import config, trace  # noqa: E402
from app.adapters import zetaris  # noqa: E402

CONTAINER = "veda"
VIEWS_DIR = ROOT / "db" / "views"
ORDER = ["river_status_latest", "rain_24h_by_point", "forecast_kelantan", "station_risk_inputs",
         "place_risk_inputs", "place_gauge_status"]  # dependencies last
AGENT = "Setup"


def view_body(name):
    """The SELECT of one view file, normalised (comments removed). Raises ZetarisError if it is not read-only."""
    body = zetaris.normalize_sql((VIEWS_DIR / f"{name}.sql").read_text(encoding="utf-8"))
    problem = zetaris.read_only_problem(body)
    if problem:
        raise zetaris.ZetarisError("not_allowed", f"view {name} is not a pure read query ({problem})")
    return body


def view_sql(name):
    return f"CREATE OR REPLACE SCHEMASTORE VIEW {name} WITH CONTAINER {CONTAINER} AS {view_body(name)}"


def create_views():
    zetaris.run_ddl(f"CREATE SCHEMASTORE CONTAINER {CONTAINER}", agent=AGENT, purpose=f"container {CONTAINER}",
                    setup=True)
    for name in ORDER:
        zetaris.run_ddl(view_sql(name), agent=AGENT, purpose=f"view {CONTAINER}.{name}", setup=True)
    return ORDER


def smoke_check():
    """Row count per view through run_sql. Returns {view: rows}."""
    return {name: zetaris.run_sql(f"SELECT COUNT(*) FROM {CONTAINER}.{name}", agent=AGENT,
                                  purpose=f"smoke check {name}").rows[0][0] for name in ORDER}


def main():
    """Create every view, then count rows; every step traced."""
    load_dotenv(ROOT / ".env")
    if config.sample_mode():
        print("SAMPLE_MODE is on - views are created in live mode only.")
        return 1
    trace.start_run("setup Zetaris views (B-08)")
    try:
        create_views()
        counts = smoke_check()
        trace.step(AGENT, "smoke_check", output_summary=", ".join(f"{k}={v}" for k, v in counts.items()),
                   decision="Every view answers through Zetaris")
        print(counts)
    except (zetaris.ZetarisError, OSError) as e:
        trace.end_run("failed", f"{type(e).__name__}: {e}")
        print(f"SETUP FAILED: {type(e).__name__}: {trace.redact(str(e))}")
        return 1
    trace.end_run("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
