"""Gauge discovery from the command line (B-71c): what the Data & Reconciler noticed, and a person's approval.

    python -m app.discover list                  # unmapped JPS gauges, their proposed fit and status

Live mode reads the shared World Model on disk (data/world/world.sqlite) after a fresh scan through Zetaris; in
SAMPLE_MODE the scan finds one SYNTHETIC gauge (data/fixtures, made by scripts/make_synthetic_scenes.py).
A discovered gauge is never used until a person approves it, and then only as context on the card - never in the
verdict until Dr Ariff approves a role (flood logic).
"""
import argparse
import sys

from dotenv import load_dotenv

from app import config, loop, trace
from app.adapters import zetaris
from app.agents import data_agent
from app.engines.world_model import veda_ingest

AGENT = "Setup"


def scan(world):
    """One discovery scan through Zetaris (the same queries the Data & Reconciler uses). -> names, or None."""
    results = {sql: zetaris.run_sql(sql, agent=data_agent.AGENT, purpose=data_agent.PURPOSES.get(sql, "discovery"))
               for sql in (veda_ingest.STATIONS_SQL, veda_ingest.PLACES_SQL, data_agent.DISCOVER_SQL)}
    run = trace.current_run()
    return data_agent.discover(world, results, run.run_id if run else None)


def discovered(world):
    """[(entity id, attrs)] of every discovered gauge, by name."""
    return sorted(((eid, e["attrs"]) for eid, e in world.store.state["entities"].items()
                   if e.get("type") == data_agent.DISCOVERED), key=lambda x: x[1].get("name") or "")


def describe(attrs):
    fit = attrs.get("fit") or {}
    place = (fit.get("place") or {}).get("name")
    return (f"{attrs.get('station_key')} | {attrs.get('name')} | {attrs.get('status')} | river {fit.get('river') or '?'}"
            f", district {fit.get('district') or '?'}" + (f", near {place}" if place else ", no covered place in district")
            + (f"; same river as {', '.join(fit['same_river_as'])}" if fit.get("same_river_as") else "")
            + (f" | approved by {attrs['approved_by']} for {attrs.get('approved_place')} at {attrs.get('approved_at')}"
               if attrs.get("status") == "approved" else ""))


def main(argv=None):
    load_dotenv(config.ROOT / ".env")
    ap = argparse.ArgumentParser(description="VEDA gauge discovery (B-71c)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="scan, then list discovered gauges with their proposed fit")
    args = ap.parse_args(argv)
    run = trace.start_run(f"discover {args.cmd}", quiet=True)
    world = loop.open_world(run.run_id)
    try:
        try:
            scan(world)
        except zetaris.ZetarisError as e:
            print(f"scan skipped: Zetaris {e.kind} - showing what the World Model already holds")
        rows = discovered(world)
        print(f"{len(rows)} discovered gauge(s) - not used until a person approves; context only, never the verdict")
        for _, attrs in rows:
            print("  " + describe(attrs))
    finally:
        trace.end_run("success")
        world.store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
