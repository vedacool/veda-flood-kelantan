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
    fc = {"no_river": reason, "rain_upstream": rain}
    ev = {"context": {"last_reading": last, "sentinels": list(sentinels)}, "met_warnings": met}
    return view.warning_signs(card, fc, ev)


HEAVY_HERE = {"local": {"heavy": True}, "upstream": []}
HEAVY_UP = {"local": {"heavy": False}, "upstream": [{"heavy_fallen": True}]}
FORECAST_ONLY = {"local": {"heavy": False}, "upstream": [{"heavy_fallen": False, "heavy_forecast": True}]}
MET_BURUK = {"status": "ok", "active": [{"heading": "Continuous rain warning (SEVERE LEVEL) Kelantan"}]}


def test_each_sign_only_when_present_and_fresh():
    assert signs() is None                                                         # nothing -> no box
    assert signs(rain=HEAVY_HERE)["lines"]["en"] == [f"Heavy rain here in the last 12{NB}h."]
    assert signs(rain=HEAVY_UP)["lines"]["ms"] == [f"Hujan lebat di hulu dalam 24{NB}jam lalu."]
    both = {"local": {"heavy": True}, "upstream": [{"heavy_fallen": True}]}
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
    assert out["footer"]["en"] == "Signs from: the last JPS reading. River level not available."
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
