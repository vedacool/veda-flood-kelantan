"""B-105 (Cowork 26 Oct): the "Signs the river may rise suddenly" box when the town's own river reading is too old.
The verdict stays INSUFFICIENT_DATA; each sign shows only when present and fresh; never a level, never metres."""
import re
from datetime import datetime

import pytest

from app import config, gazetteer, loop, view

NB = " "                                   # number and unit never split (Cowork 26 Oct)
STALE = "the controlling gauge has no fresh, healthy reading"
CARD = {"verdict": "INSUFFICIENT_DATA"}


def sentinel(name="Sg. Golok di Kg. Jenob (F1)", band="normal", change_3h=0.0, freshness="fresh"):
    return {"name": name, "level_m": 20.0, "band": band, "change_3h_m": change_3h, "freshness": freshness,
            "health": {"ok": True}, "travel_time_h": None, "chain_order": 1}


def signs(last=None, rain=None, sentinels=(), met=None, reason=STALE, card=CARD):
    code = "no_reading" if reason == STALE else "no_gauge"                  # the Forecast agent's reason code
    fc = {"no_river": reason, "no_river_code": code, "rain_upstream": rain}
    ev = {"context": {"last_reading": last, "sentinels": list(sentinels)}, "met_warnings": met}
    return view.warning_signs(card, fc, ev)


HEAVY_HERE = {"local": {"heavy": True, "past_12h_mm": 35.0}, "upstream": []}
HEAVY_UP = {"local": {"heavy": False, "past_12h_mm": 0.0}, "upstream": [{"heavy_fallen": True, "past_24h_mm": 60.0}]}
FORECAST_ONLY = {"local": {"heavy": False}, "upstream": [{"heavy_fallen": False, "heavy_forecast": True}]}
MET_BURUK = {"status": "ok", "active": [{"heading": "Continuous rain warning (SEVERE LEVEL) Kelantan"}]}


def test_each_sign_only_when_present_and_fresh():
    assert signs() is None                                                         # nothing -> no box
    assert signs(rain=HEAVY_HERE)["lines"]["en"] == [f"Heavy rain here in the last 12{NB}h."]
    assert signs(rain=HEAVY_UP)["lines"]["ms"] == [f"Hujan lebat di hulu dalam 24{NB}jam lalu."]
    both = {"local": {"heavy": True, "past_12h_mm": 31.0}, "upstream": [{"heavy_fallen": True, "past_24h_mm": 50.0}]}
    assert signs(rain=both)["lines"]["en"] == [f"Heavy rain here and upstream in the last 24{NB}h."]
    assert signs(rain=FORECAST_ONLY) is None                                       # forecast rain is not "in the last"
    up = signs(sentinels=[sentinel(change_3h=0.6)])
    assert up["lines"]["en"] == ["Upstream at Kg. Jenob: rising."] and up["lines"]["ms"] == ["Di hulu, Kg. Jenob: sedang naik."]
    at = signs(sentinels=[sentinel(band="warning")])
    assert at["lines"]["en"] == ["Upstream at Kg. Jenob: at Warning."] and at["lines"]["ms"] == ["Di hulu, Kg. Jenob: paras Amaran."]
    assert signs(met=MET_BURUK)["lines"]["en"] == ["MetMalaysia warning: severe rain."]
    assert signs(met=MET_BURUK)["lines"]["ms"] == ["Amaran MetMalaysia: hujan Buruk."]
    assert signs(met={**MET_BURUK, "status": "stale"}) is None                     # a stale warnings feed is no sign
    last = {"band": "warning", "age_minutes": 840}
    out = signs(last=last)
    assert out["lines"]["en"][0] == f"Last river reading (14{NB}h ago): Warning." and out["lines"]["ms"][0] == \
        f"Bacaan sungai terakhir (14{NB}jam lalu): Amaran."
    assert out["footer"]["en"] == "Signs from: the last JPS reading. No recent river level."
    assert out["footer"]["ms"] == "Tanda daripada: bacaan JPS terakhir. Tiada paras sungai terkini."
    assert signs(last={"band": "alert", "age_minutes": 40})["lines"]["ms"] == [f"Bacaan sungai terakhir (40{NB}minit lalu): Waspada."]


def test_a_stale_upstream_post_is_never_a_sign():
    assert signs(sentinels=[sentinel(band="danger", freshness="stale")]) is None
    assert signs(sentinels=[sentinel(change_3h=0.9, freshness="unknown")]) is None


def test_the_serious_line_is_advice_not_a_sign():
    serious = "Treat this as serious until you can confirm with JPS or the authorities."
    danger = signs(last={"band": "danger", "age_minutes": 200})
    assert danger["advice"]["en"] == serious and serious not in danger["lines"]["en"]      # its own line, not a bullet
    assert signs(last={"band": "alert", "age_minutes": 200})["advice"] is None               # Alert alone: box, no line
    assert signs(rain=HEAVY_HERE)["advice"] is None                                         # one sign
    two = signs(rain=HEAVY_HERE, met=MET_BURUK)
    assert two["advice"]["ms"] == "Anggap ini serius sehingga anda dapat sahkan dengan JPS atau pihak berkuasa."
    assert len(two["lines"]["en"]) == 2


def test_no_box_when_nothing_fresh_or_when_the_reading_is_not_the_reason():
    assert signs(last={"band": "normal", "age_minutes": 300}) is None              # only an old Normal reading
    assert signs(rain=HEAVY_HERE, reason="no controlling gauge for this place") is None
    assert signs(rain=HEAVY_HERE, card={"verdict": "WATCH"}) is None


def test_never_a_level_never_metres():
    out = signs(last={"band": "danger", "age_minutes": 90, "level_m": 9.4}, rain=HEAVY_UP,
                sentinels=[sentinel(band="alert")], met=MET_BURUK)
    text = " ".join(out["lines"]["en"] + out["lines"]["ms"] + [out["footer"]["en"], out["footer"]["ms"]]
                    + list(out["advice"].values()))
    assert not re.search(r"\d+(\.\d+)?\s?m\b", text) and "9.4" not in text
    assert not re.search(r"(?i)\b(keep watching|get ready|act now|normal for now|flood is coming)\b", text)


@pytest.mark.parametrize("at, kinds", [("2024-11-27 08:00", ["last", "rain"])])
def test_replay_gap_keeps_cant_confirm_and_shows_the_signs(monkeypatch, tmp_path, at, kinds):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    t = datetime.strptime(at, "%Y-%m-%d %H:%M").replace(tzinfo=config.MYT)
    r = loop.run("Is Rantau Panjang at risk in the next two days?", replay="nov2024", at=t, log_dir=tmp_path, quiet=True)
    v = view.answer_view(r)
    assert r["forecast"]["verdict"] == "INSUFFICIENT_DATA" and v["verdict"] == "INSUFFICIENT_DATA"   # unchanged
    assert v["signs"]["kinds"] == kinds and v["signs"]["serious"]
    assert "Signs shown (they do not set a level): the last river reading, heavy rain." in v["why"]["en"]


def test_rain_only_when_it_fell_inside_the_window_the_sentence_names():
    """Audit 26 Oct (Cowork P1-2, A-P2-10): never forecast rain, never rain older than the 12 / 24 h named."""
    forecast_here = {"local": {"heavy": True, "past_12h_mm": 0.0, "max_12h_mm": 40.0}, "upstream": []}
    assert signs(rain=forecast_here) is None                        # 40 mm FORECAST here: not "in the last 12 h"
    old_upstream = {"local": {"heavy": False, "past_12h_mm": 0.0},
                    "upstream": [{"heavy_fallen": True, "past_24h_mm": 0.0, "past_72h_mm": 110.0}]}
    assert signs(rain=old_upstream) is None                         # 110 mm 2-3 days ago: not "in the last 24 h"
    assert signs(rain={"local": {"past_12h_mm": 29.9}, "upstream": [{"past_24h_mm": 49.9}]}) is None
    edge = signs(rain={"local": {"past_12h_mm": 30.0}, "upstream": [{"past_24h_mm": 50.0}]})
    assert edge["lines"]["en"] == [f"Heavy rain here and upstream in the last 24{NB}h."]


def test_never_a_reading_veda_rejected_as_implausible():
    """Audit 26 Oct (Cowork P1-2): a fresh reading that failed the health check is no "last river reading"."""
    rejected = {"band": "danger", "age_minutes": 10, "health": {"ok": False, "problem": "impossible jump"}}
    assert signs(last=rejected) is None
    rejected_calm = {"band": "normal", "age_minutes": 10, "health": {"ok": False}}
    out = signs(last=rejected_calm, rain=HEAVY_HERE)
    assert out["kinds"] == ["rain"] and not any("Last river reading" in x for x in out["lines"]["en"])
    healthy_old = {"band": "warning", "age_minutes": 840, "health": {"ok": True}}
    assert signs(last=healthy_old)["kinds"] == ["last"]


def test_the_data_agent_keeps_only_a_healthy_last_reading(monkeypatch):
    from app.agents import data_agent
    monkeypatch.setattr(data_agent.trace, "step", lambda *a, **k: None)
    for health, kept in (({"ok": False, "problem": "out of range"}, False), ({"ok": True}, True), (None, True)):
        main = {"name": "G", "role": "controlling", "station": "station:jps:1", "level_m": 5.0, "freshness": "stale",
                "observed_at": None, "health": health, "band": "warning"}
        ctx = {"gauges": [main], "sentinels": []}

        class World:
            store = type("S", (), {"state": {"entities": {}}})()

            def entity(self, _):
                return {"attrs": {}}
        data_agent.heal(ctx, World(), None)
        assert (ctx.get("last_reading") is not None) is kept, health


def test_the_box_keys_on_the_reason_code_and_the_rain_sign_on_the_raw_sum():
    """Audit 27 Oct A-P3-27: the Forecast agent's no_river_code (not its words), and the rule's unrounded sum."""
    fc = {"no_river": "anything at all", "no_river_code": "no_reading", "rain_upstream": HEAVY_HERE}
    assert view.warning_signs(CARD, fc, {"context": {}})["kinds"] == ["rain"]
    fc["no_river_code"] = "no_gauge"
    assert view.warning_signs(CARD, fc, {"context": {}}) is None
    rounded_up = {"local": {"past_12h_mm": 30.0, "past_12h_raw": 29.96}, "upstream": [{"past_24h_mm": 50.0,
                                                                                         "past_24h_raw": 49.96}]}
    assert signs(rain=rounded_up) is None                                   # 29.96 mm is below the 30 mm rule
