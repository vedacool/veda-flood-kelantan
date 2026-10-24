"""The operator screens' data (Cowork weekend plan B8, 24 Oct) - served on /admin, this computer only.

    overview(world)            source health + circuit breakers, discovered gauges, recent answers
    run_detail(run_id)         one run from logs/: timeline, sources, Zetaris SQL, World Model reads/writes,
                               Nightshift calls and the exact prompts sent to the AI

Never the user's question: run_start's input, and every field holding it, is hidden (view.hide_question). Read-only,
except approve(), which goes through app.discover.approve (a named person, context only, never the verdict).
"""
import json
import re
from datetime import datetime, timezone

from app import config, trace, view
from app.agents import data_agent

LOGS = config.ROOT / "logs"
RUN_ID = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
HIDDEN = "(the question is not shown - privacy)"
BREAKERS = ("jps_levels", "open_meteo", "data_gov_my")
RECENT = 20


def _myt(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(config.MYT).strftime("%d %b %H:%M")
    except ValueError:
        return None


def _records(path):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            if "action" in rec:
                out.append(rec)
    return out


def _question(recs):
    return next((r.get("input_summary") for r in recs if r["action"] == "run_start"), None)


def _safe(value, question):
    return json.loads(trace.redact(json.dumps(view.hide_question(value, question, HIDDEN), ensure_ascii=False)))


def sources(world):
    """Each data source's state from the World Model (status, newest data, breaker) - live only; in SAMPLE_MODE the
    World Model lives in memory for one run, so there is nothing shared to show."""
    if world is None:
        return [], []
    now = datetime.now(timezone.utc)
    rows = []
    for cid, c in sorted(world.store.state["contexts"].items()):
        if c.get("type") != "source":
            continue
        a = c.get("attrs") or {}
        if "retired" in str(a.get("breaker") or "") and not a.get("name"):
            continue                                            # an old breaker record, kept as history only
        rows.append({"id": cid.split(":")[-1], "name": a.get("name"), "status": a.get("status") or "-",
                     "newest": a.get("newest_reading") or a.get("newest_issued"), "excluded": bool(a.get("excluded")),
                     "reliability": a.get("reliability"), "checked_at": _myt(a.get("checked_at"))})
    breakers = []
    for key in BREAKERS:
        fails, until = data_agent._breaker_state(world, key)
        is_open = until is not None and now < until
        breakers.append({"source": key, "state": "open" if is_open else "closed", "fail_count": fails,
                         "open_until": _myt(until.isoformat()) if is_open else None})
    return rows, breakers


def discovered(world):
    if world is None:
        return []
    from app import discover
    out = []
    for _, a in discover.discovered(world):
        fit = a.get("fit") or {}
        out.append({"station_key": a.get("station_key"), "name": a.get("name"), "status": a.get("status"),
                    "river": fit.get("river"), "district": fit.get("district"),
                    "near": (fit.get("place") or {}).get("name"), "place_id": (fit.get("place") or {}).get("place_id"),
                    "same_river_as": fit.get("same_river_as") or [], "approved_by": a.get("approved_by"),
                    "approved_place": a.get("approved_place"), "approved_at": _myt(a.get("approved_at"))})
    return out


def summary(path):
    """One recent run as a row - place, verdict, time, whether the AI steps were used. Never the question."""
    try:
        recs = _records(path)
    except (OSError, ValueError):
        return None
    if not recs or recs[0]["action"] != "run_start":
        return None
    by = {}
    for r in recs:
        by.setdefault(r["action"], r)
    end = next((r for r in reversed(recs) if r["action"] == "run_end"), {})
    # the FINAL verdict: run_end says it (from 25 Oct); older traces -> the LAST forecast.verdict line, never the first
    verdicts = [(r.get("output_summary") or "").split(" ")[0] for r in recs if r["action"] == "forecast.verdict"]
    final = (end.get("details") or {}).get("verdict") or (verdicts[-1] if verdicts else None)
    first = (end.get("details") or {}).get("first_verdict") or (verdicts[0] if verdicts else None)
    timing = ((by.get("timing") or {}).get("details") or {}).get("timing") or {}
    ai = [r for r in recs if r["action"] == "nightshift.chat" and r.get("status") == "success"]
    return {"run_id": recs[0]["run_id"], "started": _myt(recs[0]["timestamp"]), "mode": recs[0].get("mode"),
            "place": (by.get("forecast.verdict") or {}).get("input_summary"),
            "verdict": final, "recomputed_from": first if first and final and first != final else None,
            "seconds": timing.get("total"),
            "ai_calls": len(ai), "ai_fallbacks": (end.get("details") or {}).get("ai_fallbacks") or [],
            "status": end.get("status") or "unfinished",
            "replay": ((by.get("replay") or {}).get("output_summary"))}


def recent(limit=RECENT):
    rows = []
    for path in sorted(LOGS.glob("trace-*.jsonl"), reverse=True):
        row = summary(path)
        if row and row["place"]:                      # runs that reached a place (not tool runs like discover)
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows


NEXT_TO_GROW = [  # what VEDA cannot see yet (a note, not a count)
    "data.gov.my catalogue data sets not read yet (e.g. more MetMalaysia products)",
    "Sg. Golok upstream rain points in Thailand (Sukhirin, Waeng) - not checked yet",
]


def growth(world, found, srcs):
    """The 'network grows, with approval' strip - every count from the World Model (Cowork 24 Oct), never typed in."""
    if world is None:
        return None
    ents = world.store.state["entities"].values()
    return {"mapped": sum(1 for e in ents if e.get("type") == "station"),
            "found": len(found),
            "waiting_near_towns": sum(1 for g in found if g["status"] == "discovered" and g["place_id"]),
            "waiting": sum(1 for g in found if g["status"] == "discovered"),
            "approved": sum(1 for g in found if g["status"] == "approved"),
            "left_out": [s["name"] or s["id"] for s in srcs if s["excluded"] or s["status"] == "stale"],
            "next": NEXT_TO_GROW}


def overview(world):
    srcs, breakers = sources(world)
    found = discovered(world)
    return {"sample_mode": config.sample_mode(), "growth": growth(world, found, srcs), "sources": srcs,
            "breakers": breakers, "discovered": found, "recent": recent()}


def run_detail(run_id):
    """Everything about one run, from its trace; None when there is no such run."""
    if not RUN_ID.match(run_id or ""):
        return None
    path = LOGS / f"trace-{run_id}.jsonl"
    if not path.is_file():
        return None
    recs = _records(path)
    q = _question(recs)
    t0 = datetime.fromisoformat(recs[0]["timestamp"].replace("Z", "+00:00"))

    def at(r):
        try:
            return round((datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) - t0).total_seconds())
        except (KeyError, ValueError):
            return None
    timeline = [{"step": r.get("step"), "t": at(r), "agent": r.get("agent_name"), "action": r["action"],
                 "status": r.get("status"), "target": r.get("target_agent"), "output": r.get("output_summary"),
                 "decision": r.get("decision"), "ms": r.get("duration_ms")} for r in recs]
    sql = [{"step": r.get("step"), "agent": r.get("agent_name"), "sql": (r.get("details") or {}).get("sql"),
            "purpose": r.get("input_summary"), "rows": (r.get("details") or {}).get("rows"), "ms": r.get("duration_ms"),
            "status": r.get("status"), "query_hash": (r.get("details") or {}).get("query_hash")}
           for r in recs if r["action"] == "zetaris.run_sql"]
    world = [{"step": r.get("step"), "agent": r.get("agent_name"), "action": r["action"], "what": r.get("input_summary"),
              "result": r.get("output_summary"), "decision": r.get("decision")}
             for r in recs if r["action"].startswith("world.")]
    ai = []
    for r in recs:
        if r["action"] != "nightshift.chat":
            continue
        d = r.get("details") or {}
        ai.append({"step": r.get("step"), "agent": r.get("agent_name"), "status": r.get("status"),
                   "requested": d.get("requested_model"), "served": d.get("served_model"), "app": d.get("app"),
                   "receipt": d.get("receipt_id"), "seconds": round((r.get("duration_ms") or 0) / 1000, 1),
                   "decision": r.get("decision"), "answer": r.get("output_summary"),
                   "prompt": d.get("prompt"), "usage": d.get("usage")})
    events = sum(int(m.group(1)) for r in recs if r["action"] == "world.write"
                 for m in [re.search(r"(\d+) new event", r.get("output_summary") or "")] if m)
    disc = next(((r.get("details") or {}) for r in recs if r["action"] == "data.discover"), {})
    stale = [r.get("input_summary") for r in recs if r["action"] in ("data.health", "data.cross_check")
             and "stale" in f"{r.get('output_summary')} {r.get('decision')}".lower()]
    counts = {"events_written": events,                          # the ingest's new events (readings, facts, sources)
              "other_writes": sum(1 for r in recs if r["action"] == "world.write"
                                  and not re.search(r"\d+ new event", r.get("output_summary") or "")),
              "reads": sum(1 for r in recs if r["action"] == "world.read"),
              "sources_stale": stale,
              "discovered_seen": len(disc.get("gauges") or []), "discovered_new": len(disc.get("new") or [])}
    chosen = next(((r.get("details") or {}) for r in recs if r["action"] == "data.sources"), {})
    out = {"run": summary(path), "timeline": timeline, "sources": {"chosen": chosen.get("chosen") or [],
                                                                 "skipped": chosen.get("skipped") or []},
           "sql": sql, "world": world, "world_counts": counts, "ai": ai, "how": view.how_it_worked(path)}
    return _safe(out, q)


def approve(world, station_key, place_id, by):
    """'Approve as context' from /admin -> app.discover.approve (live only; the caller holds the run lock)."""
    from app import discover
    return discover.approve(world, station_key, place_id, by)
