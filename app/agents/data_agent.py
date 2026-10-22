"""Data & Reconciler agent (B-13): gathers the evidence for one plan - only through Zetaris (run_sql) - checks its health and
writes it to the World Model. Plain code, no LLM.

    evidence = data_agent.gather(plan, world)

Health checks (limits are TENTATIVE, 22 Oct - Dr Ariff to review, see docs/review_pack_ariff.md):
    fresh      age of the data vs FRESHNESS: fresh / aging (lower confidence) / stale (never used as "now")
    schema     each row has the fields the agents use, with the right types
    plausible  level in a sane range for its gauge; no jump bigger than MAX_JUMP_1H_M in one hour
    agreement  data.gov.my /flood-warning vs JPS for the same gauges. That source is frozen since Feb 2024, so
               the agent flags it stale and excludes it - and the World Model records why.
Reconciliation: when two sources give the same quantity, the more reliable one wins (reliability is on each source's
World Model context, tentative); on a tie the newer reading wins; if neither decides, the quantity goes into
`conflicts_unresolved` - flagged, never guessed.
Before reading, it refreshes a cached forecast table (Open-Meteo, MetMalaysia) when the World Model says the last
refresh is older than the 'fresh' limit or unknown, and records when it refreshed - so forecast age is known.
Nothing here crashes the run: every source ends with a status (ok | degraded | stale | failed | skipped) and a
plain note, and `usable` says whether the controlling gauge can be trusted for "now".
"""
from datetime import datetime, timezone

from app import config, trace
from app.adapters import zetaris
from app.engines.world_model.context import ContextBuilder
from app.engines.world_model.stable_ids import external_id
from app.engines.world_model.veda_ingest import build_network, ingest_readings, place_id

AGENT = "Data & Reconciler"
SOURCES = ("jps_levels", "open_meteo", "mygov_forecast", "mygov_warning")   # what a plan may ask for
FRESHNESS = {  # minutes: (fresh up to, aging up to); older = stale. Tentative, Dr Ariff to review.
    "jps_levels": (60, 180),
    "open_meteo": (360, 720),
    "mygov_forecast": (720, 1440),
}
REFRESHABLE = {"open_meteo": "veda_wx.om_rain", "mygov_forecast": "veda_wx.mygov_forecast"}
LABEL = {"jps_levels": "JPS river levels", "open_meteo": "Open-Meteo rain forecast",
         "mygov_forecast": "MetMalaysia forecast", "mygov_warning": "MetMalaysia warnings"}
LEVEL_RANGE_M = (-5.0, 120.0)     # every Kelantan gauge datum fits (Gua Musang reads ~50 m); outside = broken
ABOVE_DANGER_MAX_M = 15.0         # Dec 2014: Kuala Krai peaked ~9 m above danger; 15 m above = not believable
MAX_JUMP_1H_M = 3.0               # tentative: a bigger rise or fall in one hour is treated as a bad reading
MAX_RAIN_24H_MM = 1000.0
AGREE_M = 0.05                    # two sources within 5 cm of each other agree

CLOCK_SQL = "SELECT current_timestamp() AS now_utc"
FLOOD_WARNING_SQL = ("SELECT s.station_id, s.station_name, s.water_level_current, s.water_level_update_datetime "
                     "FROM veda_wx.mygov_flood LATERAL VIEW explode(data) AS s")


def freshness(source, age_minutes):
    """'fresh' | 'aging' | 'stale' | 'unknown' for an age in minutes, using the source's limits."""
    if age_minutes is None or source not in FRESHNESS:
        return "unknown"
    fresh, aging = FRESHNESS[source]
    return "fresh" if age_minutes <= fresh else "aging" if age_minutes <= aging else "stale"


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check(kind, row):
    """Schema + plausibility of one row -> {'ok', 'schema', 'plausible'} (freshness is judged per run)."""
    schema, plausible = [], []
    if kind == "jps_levels":
        if not _num(row.get("level_m")):
            schema.append(f"level_m is {row.get('level_m')!r}, not a number")
        for k in ("change_1h_m", "change_3h_m", "danger_m"):
            if row.get(k) is not None and not _num(row.get(k)):
                schema.append(f"{k} is not a number")
        if not schema:
            level = row["level_m"]
            if not LEVEL_RANGE_M[0] <= level <= LEVEL_RANGE_M[1]:
                plausible.append(f"level {level} m is outside {LEVEL_RANGE_M}")
            if _num(row.get("danger_m")) and level > row["danger_m"] + ABOVE_DANGER_MAX_M:
                plausible.append(f"level {level} m is more than {ABOVE_DANGER_MAX_M} m above danger")
            if _num(row.get("change_1h_m")) and abs(row["change_1h_m"]) > MAX_JUMP_1H_M:
                plausible.append(f"changed {row['change_1h_m']} m in 1 h")
    elif kind == "open_meteo":
        values = [row.get(k) for k in ("rain_past_24h_mm", "rain_next_24h_mm", "rain_next_72h_mm")]
        if all(v is None for v in values):
            schema.append("no rain values")
        elif any(v is not None and not _num(v) for v in values):
            schema.append("a rain value is not a number")
        elif any(v is not None and not 0 <= v <= MAX_RAIN_24H_MM * 3 for v in values) or \
                (row.get("rain_past_24h_mm") or 0) > MAX_RAIN_24H_MM:
            plausible.append("rain amount out of range")
    elif kind == "mygov_forecast":
        if not isinstance(row.get("forecast_today"), str) or not row["forecast_today"].strip():
            schema.append("no forecast text")
    return {"ok": not schema and not plausible, "schema": "; ".join(schema) or "ok",
            "plausible": "; ".join(plausible) or ("ok" if not schema else "not checked")}


def _utc(text):
    """Zetaris UTC text ('2026-10-22 08:45:00.123') -> aware datetime, or None."""
    try:
        return datetime.fromisoformat(str(text).split(".")[0].replace(" ", "T")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _iso(dt):
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def source_id(key):
    return external_id("source", "veda", key)


def _clock(now):
    """The time the data is 'as of': Zetaris's own clock (live = now; SAMPLE_MODE = when it was recorded)."""
    if now:
        return now
    try:
        t = _utc(zetaris.run_sql(CLOCK_SQL, agent=AGENT, purpose="data clock").rows[0][0])
    except (zetaris.ZetarisError, IndexError):
        t = None
    return t or datetime.now(timezone.utc)


def _last_refresh(world, key):
    facts = world.facts_about(source_id(key), "refreshed_at")
    return datetime.fromisoformat(facts[-1]["value"].replace("Z", "+00:00")) if facts else None


def _refresh_if_old(world, key, clock, run_id):
    """UNCACHE + CACHE one forecast table when its last recorded refresh is old or unknown. Returns a note."""
    clock = clock or datetime.now(timezone.utc)
    last = _last_refresh(world, key)
    age = int((clock - last).total_seconds() // 60) if last else None
    if age is not None and age <= FRESHNESS[key][0]:
        return None
    table = REFRESHABLE[key]
    why = f"last refresh {age} min ago" if age is not None else "no refresh on record"
    if config.sample_mode():
        trace.step(AGENT, "data.refresh", input_summary=table, output_summary="skipped", status="fallback",
                   source="zetaris-replay", decision=f"{why}, but SAMPLE_MODE replays recorded data - no refresh")
        return f"{LABEL[key]}: recorded data, refresh time unknown."
    try:
        zetaris.run_ddl(f"UNCACHE TABLE {table}", agent=AGENT, purpose=f"refresh {table} ({why})")
        zetaris.run_ddl(f"CACHE TABLE {table}", agent=AGENT, purpose=f"re-cache {table}")
    except zetaris.ZetarisError as e:
        trace.step(AGENT, "data.refresh", input_summary=table, output_summary=f"{e.kind}: {e}", status="fallback",
                   source="zetaris", decision=f"{why}; refresh failed -> using whatever Zetaris has, age unknown")
        return f"{LABEL[key]}: refresh failed ({e.kind}), its age is unknown."
    at = _iso(datetime.now(timezone.utc))
    world.assert_fact(source_id(key), "refreshed_at", at, confidence=1.0, source={
        "kind": "zetaris", "at": at, "sql": f"UNCACHE TABLE {table}; CACHE TABLE {table}", "query_hash": None,
        "view": table, "agent": AGENT, "run_id": run_id, "origin": key})
    trace.step(AGENT, "data.refresh", input_summary=table, output_summary=f"refreshed at {at}",
               source="zetaris-live", decision=f"{why} -> fetched {key} again and recorded the time in the World Model")
    return None


def _age_since(clock, dt):
    return int((clock - dt).total_seconds() // 60) if dt else None


def _cross_check(ctx, clock, world, run_id):
    """data.gov.my /flood-warning vs JPS for this place's gauges. Returns the result and writes source status."""
    try:
        r = zetaris.run_sql(FLOOD_WARNING_SQL, agent=AGENT, purpose="cross-check: data.gov.my /flood-warning")
    except zetaris.ZetarisError as e:
        return {"status": "failed", "note": f"data.gov.my /flood-warning could not be read ({e.kind})"}
    myt = [datetime.fromisoformat(str(x["water_level_update_datetime"])).replace(tzinfo=config.MYT)
           for x in r.records if x.get("water_level_update_datetime")]
    newest = max(myt) if myt else None
    age = _age_since(clock, newest)
    fresh = freshness("jps_levels", age)
    by_id = {str(x["station_id"]): x for x in r.records}
    pairs = []
    for g in ctx.get("gauges", []) + ctx.get("sentinels", []):
        other = by_id.get(g["station"].split(":", 2)[2])
        if other and g["level_m"] is not None:
            pairs.append({"gauge": g["name"], "jps_level_m": g["level_m"], "jps_at": g["observed_at"],
                          "mygov_level_m": other["water_level_current"],
                          "mygov_at": str(other["water_level_update_datetime"])})
    newest_text = newest.strftime("%Y-%m-%d %H:%M MYT") if newest else None
    excluded = fresh != "fresh"
    note = (f"data.gov.my /flood-warning is {fresh}: newest reading {newest_text} "
            f"({age // 1440 if age else '?'} days old) - excluded; JPS is used instead." if excluded
            else f"data.gov.my /flood-warning is current (newest {newest_text}).")
    world.upsert_context("source", external_key={"system": "veda", "id": "mygov_flood"},
                         attrs={"status": "stale" if excluded else "ok", "newest_reading": newest_text,
                                "excluded": excluded},
                         source={"kind": "zetaris", "at": _iso(clock), "sql": r.sql, "query_hash": r.query_hash,
                                 "view": "veda_wx.mygov_flood", "agent": AGENT, "run_id": run_id,
                                 "origin": "agreement check"})
    trace.step(AGENT, "data.cross_check", input_summary="JPS vs data.gov.my /flood-warning",
               output_summary=f"{len(pairs)} shared gauge(s); newest {newest_text}",
               status="fallback" if excluded else "success", source="zetaris", decision=note,
               details={"pairs": pairs[:5], "age_minutes": age})
    return {"status": "stale" if excluded else "ok", "note": note, "newest": newest_text, "pairs": pairs}


def reliability(world, key):
    """A source's reliability (0-1) from its World Model context; None if unknown."""
    ctx = world.store.state["contexts"].get(source_id(key)) if world else None
    return (ctx or {}).get("attrs", {}).get("reliability")


def _when(text, tz):
    """'2026-10-22T10:30:00Z' (UTC) or '2024-02-23 14:45:00' (local time in tz) -> aware datetime, or None."""
    try:
        t = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=tz)


def reconcile(quantity, candidates, agree_within=AGREE_M):
    """One value for a quantity seen by several sources: higher reliability first, then the newer reading.
    candidates: [{'source', 'value', 'at' (aware datetime or None), 'reliability'}].
    Returns {quantity, candidates, chosen, rule, reason}; rule 'unresolved' (chosen None) when neither reliability
    nor time can decide - flag, don't guess."""
    shown = [{**c, "at": _iso(c["at"]) if c["at"] else None} for c in candidates]
    entry = {"quantity": quantity, "candidates": shown}
    candidates = [c for c in candidates if isinstance(c["value"], (int, float)) and not isinstance(c["value"], bool)]
    if len(candidates) < 2:                 # a source without a value cannot disagree
        only = candidates[0] if candidates else None
        return {**entry, "chosen": only and only["source"], "value": only and only["value"], "rule": "single",
                "reason": "only one source has a value"}
    values = [c["value"] for c in candidates]
    best_rel = max((c["reliability"] or 0) for c in candidates)
    top = [c for c in candidates if (c["reliability"] or 0) == best_rel]
    if max(values) - min(values) <= agree_within:
        chosen, rule, reason = top[0], "agree", f"sources agree within {agree_within}"
    elif len(top) == 1:
        chosen, rule, reason = top[0], "reliability", f"{top[0]['source']} is the more reliable source ({best_rel})"
    else:
        dated = sorted((c for c in top if c["at"]), key=lambda c: c["at"], reverse=True)
        if len(dated) == len(top) and dated[0]["at"] > dated[1]["at"]:
            chosen, rule = dated[0], "recency"
            reason = (f"equal reliability ({best_rel}); {dated[0]['source']} is newer "
                      f"({_iso(dated[0]['at'])} vs {_iso(dated[1]['at'])})")
        else:
            return {**entry, "chosen": None, "value": None, "rule": "unresolved",
                    "reason": f"equal reliability ({best_rel}) and no newer reading - flagged, not guessed"}
    return {**entry, "chosen": chosen["source"], "value": chosen["value"], "rule": rule, "reason": reason}


def _reconcile_levels(cross, world):
    """Gauge levels seen by both JPS and data.gov.my /flood-warning -> reconciliation entries."""
    out = []
    for pr in (cross or {}).get("pairs", []):
        out.append(reconcile(f"water level at {pr['gauge']}", [
            {"source": "jps_levels", "value": pr["jps_level_m"], "at": _when(pr["jps_at"], timezone.utc),
             "reliability": reliability(world, "jps_levels")},
            {"source": "mygov_flood", "value": pr["mygov_level_m"], "at": _when(pr["mygov_at"], config.MYT),
             "reliability": reliability(world, "mygov_flood")}]))
    return out


def _forecast_age(world, key, clock):
    return _age_since(clock, _last_refresh(world, key))


def gather(plan, world, now=None):
    """Evidence for plan['place'] from the sources the plan asks for. Never raises for a data problem."""
    run = trace.current_run()
    run_id = run.run_id if run else None
    wanted = [s for s in plan.get("sources", []) if s in SOURCES]
    events_before = len(world.store.events)
    sources = {s: {"status": "skipped", "note": "not in the plan"} for s in SOURCES if s not in wanted}
    notes = []
    for key in REFRESHABLE:
        if key in wanted:
            note = _refresh_if_old(world, key, now, run_id)
            if note:
                notes.append(note)
    clock = _clock(now)                 # after any refresh, so a just-refreshed forecast is 0 min old
    try:
        net = build_network(world, AGENT, run_id)
        counts = ingest_readings(world, AGENT, run_id, check=check)
    except zetaris.ZetarisError as e:
        trace.step(AGENT, "world.write", output_summary=f"{e.kind}: {e}", status="failed", source="zetaris",
                   decision="Could not load the world from Zetaris -> no evidence; the answer must say so")
        return {"place": plan.get("place"), "clock": _iso(clock), "usable": False, "context": None,
                "sources": {s: {"status": "failed", "note": f"Zetaris {e.kind}"} for s in wanted} | sources,
                "notes": [f"Could not read data through Zetaris ({e.kind})."], "events_added": 0}
    added = len(world.store.events) - events_before
    trace.step(AGENT, "world.write", output_summary=f"{net['stations']} gauges, {counts['gauges']} readings, "
                                                    f"{counts['places']} places; {added} new event(s)",
               source="world_model", decision=(f"Wrote {added} new event(s) to the World Model" if added
                                               else "Nothing changed since the last run -> no new events"),
               details={"network": net, "unhealthy": counts["unhealthy"]})

    ctx = ContextBuilder(world).build(plan.get("intent", "risk_check"), place_id(plan["place"]["place_id"]),
                                      now=clock)
    trace.step(AGENT, "world.read", input_summary=ctx["place"].get("name") if ctx["found"] else plan["place"],
               output_summary=f"{ctx['items']} item(s); missing: {', '.join(ctx['trace'].get('missing', [])) or '-'}",
               source="world_model", decision=ctx["trace"]["strategy"])

    for key, field in (("open_meteo", "rain"), ("mygov_forecast", "met_forecast")):
        if key not in wanted and ctx.get(field) is not None:
            ctx[field] = None           # evidence holds only what the plan asked for
    gauges = ctx.get("gauges", []) + ctx.get("sentinels", [])
    for g in gauges:
        g["freshness"] = freshness("jps_levels", g["age_minutes"])
    if "jps_levels" in wanted:
        bad = [g["name"] for g in gauges if g["health"] and not g["health"]["ok"]]
        stale = [g["name"] for g in gauges if g["freshness"] in ("stale", "unknown")]
        status = "failed" if not gauges else "degraded" if bad or stale else "ok"
        sources["jps_levels"] = {"status": status, "note": (
            f"{len(gauges)} gauge(s); " + (f"stale or missing: {', '.join(stale)}; " if stale else "")
            + (f"failed checks: {', '.join(bad)}" if bad else "all readings passed the checks"))}
    for key, item in (("open_meteo", ctx.get("rain")), ("mygov_forecast", ctx.get("met_forecast"))):
        if key not in wanted:
            continue
        if item is None:
            sources[key] = {"status": "failed", "note": "no data for this place"}
            continue
        age = _forecast_age(world, key, clock)
        item["age_minutes"], item["freshness"] = age, freshness(key, age)
        health = (item.get("provenance") or {}).get("health") or {"ok": True}
        status = "degraded" if not health["ok"] else "stale" if item["freshness"] == "stale" else \
            "degraded" if item["freshness"] in ("aging", "unknown") else "ok"
        sources[key] = {"status": status, "note": f"refreshed {age} min ago ({item['freshness']})"
                        if age is not None else "refresh time unknown"}
    if "mygov_warning" in wanted:
        sources["mygov_warning"] = {"status": "skipped", "note": "MetMalaysia warnings are not wired into the agents yet"}

    cross = _cross_check(ctx, clock, world, run_id) if "jps_levels" in wanted and ctx["found"] else None
    if cross:
        notes.insert(0, cross["note"])         # the excluded source matters more than refresh details
    reconciliation = _reconcile_levels(cross, world)
    unresolved = [r for r in reconciliation if r["rule"] == "unresolved"]
    if reconciliation:
        trace.step(AGENT, "data.reconcile", input_summary=f"{len(reconciliation)} quantity(ies) seen by 2 sources",
                   output_summary=f"{len(unresolved)} unresolved", source="world_model",
                   status="fallback" if unresolved else "success",
                   decision="; ".join(f"{r['quantity']}: {r['rule']} - {r['reason']}" for r in reconciliation[:3]),
                   details={"reconciliation": reconciliation})

    controlling = next((g for g in ctx.get("gauges", []) if g["role"] == "controlling"), None)
    usable = bool(controlling and controlling["level_m"] is not None and controlling["freshness"] in ("fresh", "aging")
                  and (controlling["health"] or {"ok": True})["ok"])
    if not usable:
        notes.append("The controlling gauge has no fresh, healthy reading - current status cannot be confirmed.")
    for key, s in sources.items():
        if s["status"] != "skipped":
            world.assert_fact(source_id(key), "health", s, confidence=1.0, source={
                "kind": "agent_check", "at": _iso(clock), "agent": AGENT, "run_id": run_id, "origin": "Data & Reconciler agent"})
        trace.step(AGENT, "data.health", input_summary=key, output_summary=f"{s['status']}: {s['note']}",
                   status="success" if s["status"] in ("ok", "skipped") else "fallback", source=key)
    return {"place": ctx.get("place"), "clock": _iso(clock), "usable": usable, "context": ctx, "sources": sources,
            "cross_check": cross, "reconciliation": reconciliation, "conflicts_unresolved": unresolved,
            "notes": notes, "events_added": len(world.store.events) - events_before}
