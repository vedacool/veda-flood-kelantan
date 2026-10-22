"""ContextBuilder (ContextBuilderService): everything an agent needs about one place, from the World Model only.

    payload = ContextBuilder(world).build(intent="risk_check", place="place:veda:rantau_panjang")

Returns a STRUCTURED payload (spec §10.2), never a pre-written text: the controlling gauge(s), sentinel gauges
with travel times, rain and the MetMalaysia forecast - every item with its value, the time the data refers to,
its age, its provenance (query hash, view, agent, run) and why it was selected. Freshness is not judged here;
the Data & Reconciler agent applies the (tentative) limits to `age_minutes`.
"""
from datetime import datetime, timezone

STRATEGY = "place-centric v1: controlling gauge(s) -> sentinels (upstream first) -> rain -> MET forecast"


def _parse(at):
    try:
        return datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return None


def _age_minutes(at, now):
    t = _parse(at)
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return int((now - t).total_seconds() // 60)


class ContextBuilder:
    """Builds place context from a WorldModel."""

    def __init__(self, world):
        self.world = world

    def _fact(self, about, predicate):
        facts = self.world.facts_about(about, predicate)
        return facts[-1] if facts else None

    def _gauge(self, station_id, role, reason, now, lag=None):
        entity = self.world.entity(station_id) or {"attrs": {}}
        level, band = self._fact(station_id, "water_level_m"), self._fact(station_id, "band")
        item = {"station": station_id, "name": entity["attrs"].get("name"), "role": role,
                "level_m": level["value"] if level else None, "band": band["value"] if band else None,
                "observed_at": level["source"]["at"] if level else None,
                "age_minutes": _age_minutes(level["source"]["at"], now) if level else None,
                "thresholds": {k: entity["attrs"].get(k) for k in ("normal_m", "alert_m", "warning_m", "danger_m")},
                "provenance": level["source"] if level else None,
                "health": level["source"].get("health") if level else None,
                "mapping_status": entity["attrs"].get("mapping_status"), "selection_reason": reason}
        for pred in ("change_1h_m", "change_3h_m"):
            f = self._fact(station_id, pred)
            item[pred] = f["value"] if f else None
        if lag:
            item["travel_time_h"] = {"min": lag.get("lag_min_h"), "max": lag.get("lag_max_h"),
                                     "source": lag.get("lag_source"), "status": lag.get("status")}
        return item

    def build(self, intent, place, now=None):
        """Context payload for one place id (e.g. 'place:veda:rantau_panjang'). Unknown place -> found=False."""
        now = now or datetime.now(timezone.utc)
        entity = self.world.entity(place)
        if not entity or entity["type"] != "place":
            return {"intent": intent, "place": place, "found": False, "items": 0,
                    "trace": {"strategy": STRATEGY, "selection_reason": "place not in the World Model"}}
        controlling = self.world.edges(place, via="controlled_by")
        primary = controlling[0]["to"] if controlling else None
        gauges = [self._gauge(e["to"], "controlling", "controlling gauge for this place", now) for e in controlling]
        gauges += [self._gauge(e["to"], "controlling_secondary", "second river that controls this place", now)
                   for e in self.world.edges(place, via="also_controlled_by")]
        sentinels = []
        for e in self.world.edges(place, via="sentinel_for", direction="in"):
            lag = next((t["attrs"] for t in self.world.edges(e["from"], via="travel_time")
                        if primary and t["to"] == primary), None)
            reason = ("upstream sentinel with a reported travel time" if lag
                      else "upstream sentinel (travel time unknown)")
            sentinels.append((e["attrs"].get("sort_order", 99), self._gauge(e["from"], "sentinel", reason, now, lag)))
        rain, forecast = self._fact(place, "rain_mm"), self._fact(place, "met_forecast_today")
        payload = {
            "intent": intent, "found": True,
            "place": {"id": place, "name": entity["attrs"].get("name"), "district": entity["attrs"].get("district"),
                      "mapping_status": entity["attrs"].get("mapping_status")},
            "gauges": gauges,
            "sentinels": [s for _, s in sorted(sentinels, key=lambda x: x[0])],
            "rain": None if not rain else {**rain["value"], "forecast_until": rain["source"]["at"],
                                           "provenance": rain["source"],
                                           "selection_reason": "nearest rain point to the place"},
            "met_forecast": None if not forecast else {**forecast["value"], "for_date": forecast["source"]["at"],
                                                       "provenance": forecast["source"],
                                                       "selection_reason": "MetMalaysia town forecast for today"},
        }
        payload["items"] = len(gauges) + len(payload["sentinels"]) + bool(rain) + bool(forecast)
        payload["trace"] = {"strategy": STRATEGY, "built_at": now.isoformat(timespec="seconds"),
                            "missing": [k for k in ("rain", "met_forecast") if payload[k] is None]
                            + [g["station"] for g in gauges + payload["sentinels"] if g["level_m"] is None]}
        return payload
