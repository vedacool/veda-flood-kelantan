"""B-88: the "upstream + local rain" rule (hulu + hilir) - pure functions, no data access.

Kelantan floods come from days of monsoon rain upstream arriving while it also rains heavily in town. VEDA reads the
hourly Open-Meteo rain at every rain point (data/rain_points.csv) and, for each town:

    upstream points   rain points whose gauge lies upstream of the town's controlling gauge (station_links
                      'upstream_of' chain); the arrival window is composed ONLY from known legs (travel_time links
                      and 'upstream_of' lags) - any unknown leg -> "arrival time not known"
    heavy upstream    at any upstream point: 72 h total >= 100 mm OR 24 h >= 50 mm (rain that has fallen; live also
                      checks the forecast hours, which can only lift the town to Keep watching)
    heavy local       >= 30 mm in 12 h at the town's own rain point, past and forecast hours combined (any 12 h window
                      that includes now)
    combined          heavy rain that has fallen upstream with a KNOWN window starting within 24 h + heavy local
                      rain -> the Forecast agent raises the verdict one level (never above ACT); upstream alone ->
                      at least Keep watching (also when the window is unknown: never higher from this rule)
    until             the last forecast hour within 72 h with >= 2.5 mm/h; "heavy" wording only if that period has
                      an hour >= 7.6 mm/h

Every number is TENTATIVE (Cowork 24 Oct) - docs/review_pack_ariff.md section L asks Dr Ariff.
"""
from datetime import timedelta

UPSTREAM_72H_MM = 100.0          # L1 (tentative)
UPSTREAM_24H_MM = 50.0           # L1 (tentative)
LOCAL_12H_MM = 30.0              # L2 (tentative)
ARRIVAL_WITHIN_H = 24.0          # L3 (tentative): a known window that starts within this many hours
UNTIL_MM_H = 2.5                 # L5 (tentative): "rain" hour
HEAVY_MM_H = 7.6                 # L5 (tentative): "heavy rain" hour
HORIZON_H = 72


def _sum(hours, lo, hi):
    """Rain in (lo, hi] from [(t, mm)], unrounded (audit 24 Oct P3: thresholds compare the real sum; 99.96 is not
    100). features() rounds what is shown."""
    return sum(mm for t, mm in hours if lo < t <= hi and mm is not None)


def _r(v):
    return None if v is None else round(v, 1)


def features(hours, now):
    """One rain point's numbers at `now` from its hourly [(aware datetime, mm)] - past only in a replay (no
    hindsight: the caller passes no hour after `now`), past + forecast live."""
    h = timedelta(hours=1)
    forecast = [(t, mm) for t, mm in hours if t > now and mm is not None]
    windows = [_sum(hours, now - 12 * h + k * h, now + k * h) for k in range(13)] if forecast else [
        _sum(hours, now - 12 * h, now)]
    until = heavy = None
    in_horizon = [t for t, _ in forecast if t <= now + HORIZON_H * h]
    rainy = [t for t, mm in forecast if t <= now + HORIZON_H * h and mm >= UNTIL_MM_H]
    if rainy:
        until = max(rainy)
        heavy = any(mm >= HEAVY_MM_H for t, mm in forecast if t <= until)
    raw = {"past_12h_mm": _sum(hours, now - 12 * h, now), "past_24h_mm": _sum(hours, now - 24 * h, now),
           "past_72h_mm": _sum(hours, now - 72 * h, now),
           "next_12h_mm": _sum(hours, now, now + 12 * h) if forecast else None,
           "next_24h_mm": _sum(hours, now, now + 24 * h) if forecast else None,
           "next_72h_mm": _sum(hours, now, now + 72 * h) if forecast else None, "max_12h_mm": max(windows)}
    return {**{k: _r(v) for k, v in raw.items()}, "raw": raw, "has_forecast": bool(forecast),
            "until": until.isoformat() if until else None, "until_heavy": bool(heavy),
            # audit 24 Oct P3: "then easing" only when the rain stops before the forecast data ends
            "until_ends": bool(until and until < max(in_horizon))}


def _key(k):
    return str(k) if k is not None else None


def arrival(start, target, links):
    """(is_upstream, window {'min','max'} or None) from gauge `start` to gauge `target`: follow the 'upstream_of'
    chain from start; the window adds known legs only (travel_time links, upstream_of lags)."""
    start, target = _key(start), _key(target)
    nxt = {_key(l["from_key"]): _key(l["to_key"]) for l in links if l["link_type"] == "upstream_of"}
    path, cur = [start], start
    while cur in nxt and cur != target and len(path) < 50:
        cur = nxt[cur]
        path.append(cur)
    if start == target or target not in path:
        return False, None
    pos = {k: i for i, k in enumerate(path)}
    legs = [(_key(l["from_key"]), _key(l["to_key"]), l["lag_min_h"], l["lag_max_h"]) for l in links
            if l["link_type"] in ("travel_time", "upstream_of") and l.get("lag_min_h") is not None]
    best = {start: (0.0, 0.0)}
    for node in path:                                   # path order: every leg goes downstream
        if node not in best:
            continue
        for a, b, lo, hi in legs:
            if a == node and b in pos and pos[b] > pos[node] and pos[b] <= pos[target]:
                cand = (best[node][0] + float(lo), best[node][1] + float(hi if hi is not None else lo))
                if b not in best or cand[0] < best[b][0]:
                    best[b] = cand
    w = best.get(target)
    return True, ({"min": round(w[0], 1), "max": round(w[1], 1)} if w else None)


def heavy_upstream(f):
    """(fallen, forecast): heavy rain that has fallen at this point / heavy rain forecast there."""
    r = f.get("raw") or f                                 # the unrounded sums (older facts: the rounded ones)
    fallen = r["past_72h_mm"] >= UPSTREAM_72H_MM or r["past_24h_mm"] >= UPSTREAM_24H_MM
    forecast = f["has_forecast"] and ((r["next_72h_mm"] or 0) >= UPSTREAM_72H_MM
                                      or (r["next_24h_mm"] or 0) >= UPSTREAM_24H_MM)
    return fallen, bool(forecast)


def assess(controlling, local_point, points, links, golok=False):
    """The town's rain picture. controlling = its controlling gauge keys (primary first); local_point = its own rain
    point key; points = {point_key: {'name', 'station_key', 'features'}}; links = station_links rows; golok = a
    controlling gauge is on Sg. Golok (its upstream is in Thailand - no rain point there)."""
    up = []
    for key, p in sorted(points.items()):
        if key == local_point or not p.get("features"):
            continue
        hits = [arrival(p["station_key"], c, links) for c in controlling]
        hits = [w for is_up, w in hits if is_up] if any(is_up for is_up, _ in hits) else None
        if hits is None:
            continue
        known = [w for w in hits if w]
        window = min(known, key=lambda w: w["min"]) if known else None
        fallen, forecast = heavy_upstream(p["features"])
        up.append({"point": key, "name": p["name"], "window": window, "heavy_fallen": fallen,
                   "heavy_forecast": forecast, **{k: p["features"][k] for k in (
                       "past_24h_mm", "past_72h_mm", "next_24h_mm", "next_72h_mm")}})
    lf = (points.get(local_point) or {}).get("features")
    local = None if not lf else {"point": local_point, "name": points[local_point]["name"],
                                 "max_12h_mm": lf["max_12h_mm"], "past_12h_mm": lf["past_12h_mm"],
                                 "next_12h_mm": lf["next_12h_mm"],
                                 "heavy": (lf.get("raw") or lf)["max_12h_mm"] >= LOCAL_12H_MM,
                                 "until": lf["until"], "until_heavy": lf["until_heavy"],
                                 "until_ends": lf.get("until_ends", True)}
    arriving = [u for u in up if u["heavy_fallen"] and u["window"] and u["window"]["min"] <= ARRIVAL_WITHIN_H]
    heavy = [u for u in up if u["heavy_fallen"] or u["heavy_forecast"]]
    thai = [u["point"] for u in up if points[u["point"]].get("thai")]          # Cowork 24 Oct: Thai-side Golok points
    return {"upstream": up, "local": local, "heavy_upstream": [u["point"] for u in heavy],
            "arriving_24h": [u["point"] for u in arriving],
            "combined": bool(arriving and local and local["heavy"]),
            "window_known": any(u["window"] for u in heavy),
            "no_upstream_points": not up, "thai_points": thai,
            "golok": bool(golok) and not thai,              # "Thailand not checked" only while no Thai point has data
            "rules": {"upstream_72h_mm": UPSTREAM_72H_MM, "upstream_24h_mm": UPSTREAM_24H_MM,
                      "local_12h_mm": LOCAL_12H_MM, "arrival_within_h": ARRIVAL_WITHIN_H,
                      "until_mm_h": UNTIL_MM_H, "heavy_mm_h": HEAVY_MM_H, "status": "tentative - Dr Ariff (L)"}}
