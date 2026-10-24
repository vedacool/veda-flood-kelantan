"""Gauge discovery from the command line (B-71c): what the Data & Reconciler noticed, and a person's approval.

    python -m app.discover list                  # unmapped JPS gauges, their proposed fit and status
    python -m app.discover approve <station_key> --place <place_id> --by "<your name>"     # live mode only

Live mode reads the shared World Model on disk (data/world/world.sqlite) after a fresh scan through Zetaris; in
SAMPLE_MODE the scan finds one SYNTHETIC gauge (data/fixtures, made by scripts/make_synthetic_scenes.py).
A discovered gauge is never used until a person approves it, and then only as context on the card - never in the
verdict until Dr Ariff approves a role (flood logic).
"""
import argparse
import sys
from datetime import datetime, timezone

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


def approve(world, key, place_id, by):
    """A person approves one discovered gauge as CONTEXT for one covered place (audited World Model event).
    Refused: an unknown gauge, a place VEDA does not cover, no name. -> (ok, message)."""
    eid = data_agent.external_id(data_agent.DISCOVERED, "jps", key)
    ent = world.entity(eid)
    if ent is None:
        return False, f"{key} is not a discovered gauge - run: python -m app.discover list"
    if not (by or "").strip():
        return False, "say who approves: --by \"<your name>\""
    places = {r["place_id"] for r in zetaris.run_sql(veda_ingest.PLACES_SQL, agent=AGENT,
                                                    purpose="approve: covered places").records}
    if place_id not in places:
        return False, f"{place_id} is not a covered place ({', '.join(sorted(places))})"
    at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    world.upsert_entity(data_agent.DISCOVERED, external_key={"system": "jps", "id": key},
                        attrs={"status": "approved", "approved_by": by.strip(), "approved_place": place_id,
                               "approved_at": at},
                        source={"kind": "person", "at": at, "agent": by.strip(), "origin": "python -m app.discover approve"})
    trace.step(AGENT, "discover.approve", input_summary=f"{key} for {place_id}",
               output_summary=f"{ent['attrs'].get('name')} approved by {by.strip()} for {place_id}",
               decision="context on that place's card only - never in the verdict until Dr Ariff approves a role")
    return True, f"approved: {ent['attrs'].get('name')} for {place_id} (context only, not the verdict)"


def main(argv=None):
    if not config.demo_mode():                      # VEDA_DEMO=1: no .env is read
        load_dotenv(config.ROOT / ".env")
    ap = argparse.ArgumentParser(description="VEDA gauge discovery (B-71c)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="scan, then list discovered gauges with their proposed fit")
    ok = sub.add_parser("approve", help="a person approves one discovered gauge as context for one covered place")
    ok.add_argument("station_key")
    ok.add_argument("--place", required=True, help="covered place id, e.g. pasir_mas")
    ok.add_argument("--by", required=True, help="who approves (a person's name)")
    args = ap.parse_args(argv)
    if args.cmd == "approve" and config.sample_mode():
        print("SAMPLE_MODE: approval writes to the live World Model - run it in live mode.")
        return 1
    run = trace.start_run(f"discover {args.cmd}", quiet=True)
    world = loop.open_world(run.run_id)
    try:
        if args.cmd == "approve":
            try:
                done, message = approve(world, args.station_key, args.place, args.by)
            except zetaris.ZetarisError as e:
                done, message = False, f"cannot check the place: Zetaris {e.kind}"
            print(message)
            return 0 if done else 1
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
