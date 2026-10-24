"""B-88: the upstream + local rain rule (hulu + hilir) - numbers tentative (Cowork 24 Oct, review pack L). Each case:
the sums and windows, the arrival composition from known legs only, the thresholds, the Forecast agent's levels (at
least WATCH, one level up when combined, never above ACT, capped at WATCH with an unknown window), the scene end to
end (trace line, card in EN + BM, Critic), the router, and "rain likely until"."""
import json
from datetime import datetime, timedelta

import pytest

from app import config, gazetteer, loop, rain_rule, router
from app.agents import forecast_agent

MYT = config.MYT
NOW = datetime(2024, 11, 27, 12, 0, tzinfo=MYT)
LINKS = [  # the real station_links shape: a chain, one upstream_of lag (Dabong -> Kuala Krai) and two travel times
    {"from_key": "DABONG", "to_key": "KKRAI", "link_type": "upstream_of", "lag_min_h": 23.0, "lag_max_h": 23.0},
    {"from_key": "KKRAI", "to_key": "KUSIAL", "link_type": "upstream_of", "lag_min_h": None, "lag_max_h": None},
    {"from_key": "KUSIAL", "to_key": 27133, "link_type": "upstream_of", "lag_min_h": None, "lag_max_h": None},
    {"from_key": 27133, "to_key": "TAMBATAN", "link_type": "upstream_of", "lag_min_h": None, "lag_max_h": None},
    {"from_key": "KKRAI", "to_key": "KUSIAL", "link_type": "travel_time", "lag_min_h": 6.0, "lag_max_h": 9.0},
    {"from_key": "KKRAI", "to_key": "TAMBATAN", "link_type": "travel_time", "lag_min_h": 9.0, "lag_max_h": 17.0},
]


def hours(per_hour_mm, back=72, ahead=0):
    """Hourly [(t, mm)] around NOW: a constant rate in the past `back` hours and the next `ahead` hours."""
    return [(NOW + timedelta(hours=k), per_hour_mm) for k in range(-back + 1, ahead + 1)]


def point(name, station, mm_per_h, back=72, ahead=0):
    return {"name": name, "station_key": station, "features": rain_rule.features(hours(mm_per_h, back, ahead), NOW)}


# -- the numbers ------------------------------------------------------------------------------------------------
def test_features_sum_past_and_forecast_without_hindsight():
    f = rain_rule.features(hours(1.0, back=72, ahead=72), NOW)
    assert (f["past_12h_mm"], f["past_24h_mm"], f["past_72h_mm"]) == (12.0, 24.0, 72.0)
    assert (f["next_12h_mm"], f["next_24h_mm"], f["next_72h_mm"]) == (12.0, 24.0, 72.0)
    past_only = rain_rule.features(hours(1.0, back=72), NOW)
    assert past_only["next_24h_mm"] is None and not past_only["has_forecast"] and past_only["until"] is None


def test_local_12h_window_combines_past_and_forecast_hours():
    hs = [(NOW + timedelta(hours=k), 3.0) for k in range(-5, 7)]      # 6 h fallen + 6 h forecast = 36 mm
    f = rain_rule.features(hs, NOW)
    assert f["past_12h_mm"] == 18.0 and f["max_12h_mm"] == 36.0


def test_until_is_the_last_rainy_forecast_hour_and_heavy_only_with_a_heavy_hour():
    hs = [(NOW + timedelta(hours=k), mm) for k, mm in ((1, 3.0), (2, 8.0), (5, 2.5), (6, 2.4), (80, 9.0))]
    f = rain_rule.features(hs, NOW)
    assert f["until"] == (NOW + timedelta(hours=5)).isoformat() and f["until_heavy"]     # 6 h: < 2.5; 80 h: > 72 h
    light = rain_rule.features([(NOW + timedelta(hours=1), 3.0), (NOW + timedelta(hours=2), 7.5)], NOW)
    assert light["until"] and not light["until_heavy"]                                   # 7.5 < 7.6 mm/h


# -- arrival windows: known legs only ---------------------------------------------------------------------------
@pytest.mark.parametrize("start,target,expected", [
    ("KKRAI", "TAMBATAN", (True, {"min": 9.0, "max": 17.0})),            # travel time
    ("DABONG", "TAMBATAN", (True, {"min": 32.0, "max": 40.0})),          # 23 h + 9-17 h
    ("KKRAI", "KUSIAL", (True, {"min": 6.0, "max": 9.0})),
    ("KUSIAL", "TAMBATAN", (True, None)),                                # upstream, but a leg is unknown
    ("DABONG", 27133, (True, None)),                                     # Kuala Krai -> Pasir Mas unknown
    ("TAMBATAN", "KKRAI", (False, None)),                                # downstream, not upstream
    ("TAMBATAN", "TAMBATAN", (False, None)),                             # the town's own gauge
])
def test_arrival_window_from_known_legs_only(start, target, expected):
    assert rain_rule.arrival(start, target, LINKS) == expected


# -- thresholds -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("mm_per_h,back,heavy", [
    (100 / 72, 72, True), (99.9 / 72, 72, False),       # 72 h >= 100 mm
    (50 / 24, 24, True), (49.9 / 24, 24, False),        # 24 h >= 50 mm
])
def test_heavy_upstream_thresholds(mm_per_h, back, heavy):
    f = rain_rule.features(hours(mm_per_h, back=back), NOW)
    assert rain_rule.heavy_upstream(f)[0] is heavy


def test_forecast_heavy_upstream_counts_but_never_as_arriving():
    pts = {"kk": point("Sg. Kelantan di Kuala Krai (F1)", "KKRAI", 0.0, ahead=24),
           "here": point("Tambatan", "TAMBATAN", 3.0)}
    pts["kk"]["features"] = rain_rule.features(hours(0.0, back=72) + [(NOW + timedelta(hours=k), 3.0)
                                                                      for k in range(1, 25)], NOW)   # 72 mm forecast
    a = rain_rule.assess(["TAMBATAN"], "here", pts, LINKS)
    assert a["heavy_upstream"] == ["kk"] and a["arriving_24h"] == [] and not a["combined"]


def test_combined_needs_a_known_window_within_24h_and_heavy_local_rain():
    def town(local_mm_h, up_point="kk", station="KKRAI"):
        pts = {up_point: point("up", station, 2.0), "here": point("Tambatan", "TAMBATAN", local_mm_h)}
        return rain_rule.assess(["TAMBATAN"], "here", pts, LINKS)
    assert town(2.5)["combined"]                                    # 30 mm in 12 h + Kuala Krai 9-17 h
    assert not town(2.4)["combined"]                                # 28.8 mm in 12 h: not heavy here
    assert not town(2.5, "dabong", "DABONG")["combined"]            # Dabong: 32-40 h, not within 24 h
    assert not town(2.5, "kusial", "KUSIAL")["combined"]            # window not known
    assert town(2.5, "kusial", "KUSIAL")["heavy_upstream"] == ["kusial"]


# -- the Forecast agent ---------------------------------------------------------------------------------------
def ctx_with(ru, level=1.0, thresholds=None):
    th = thresholds or {"alert_m": 3.0, "warning_m": 4.0, "danger_m": 5.0}
    g = {"station": "station:jps:TAMBATAN", "name": "Sg. Kelantan di Tambatan D'Raja (F1)", "role": "controlling",
         "level_m": level, "band": "normal", "thresholds": th, "observed_at": "2024-11-27T04:00:00Z", "age_minutes": 5,
         "freshness": "fresh", "health": {"ok": True}, "change_1h_m": 0.0, "change_3h_m": 0.0, "tide_influenced": True}
    return {"usable": True, "place": {"name": "Kota Bharu"}, "context": {"gauges": [g], "sentinels": [],
                                                                         "rain": None, "rain_upstream": ru}}


def ru_of(combined=False, window=True):
    up = {"point": "kk", "name": "Sg. Kelantan di Kuala Krai (F1)", "window": {"min": 9.0, "max": 17.0} if window else None,
          "heavy_fallen": True, "heavy_forecast": False, "past_24h_mm": 60.0, "past_72h_mm": 125.0,
          "next_24h_mm": None, "next_72h_mm": None}
    return {"upstream": [up], "heavy_upstream": ["kk"], "arriving_24h": ["kk"] if combined else [],
            "combined": combined, "local": {"max_12h_mm": 35.0 if combined else 5.0, "heavy": combined},
            "window_known": window, "golok": False}


def verdict(ev, effort="full"):
    return forecast_agent.forecast({"effort": effort}, ev)


def test_upstream_rain_alone_gives_at_least_watch(run_ctx):
    fc = verdict(ctx_with(ru_of()))
    assert fc["verdict"] == "WATCH" and [t["rule"] for t in fc["triggers"]] == ["upstream-rain"]


def test_unknown_window_never_above_watch_even_with_heavy_local_rain(run_ctx):
    ru = ru_of(window=False)
    ru["local"] = {"max_12h_mm": 40.0, "heavy": True}
    assert verdict(ctx_with(ru))["verdict"] == "WATCH"


def test_combined_raises_one_level(run_ctx):
    fc = verdict(ctx_with(ru_of(combined=True)))
    assert fc["verdict"] == "PREPARE" and fc["triggers"][-1]["rule"] == "upstream+local-rain"
    assert "one level up" in fc["triggers"][-1]["reason"]


def test_combined_never_above_act(run_ctx):
    fc = verdict(ctx_with(ru_of(combined=True), level=5.5))              # river at Danger already
    assert fc["verdict"] == "ACT" and not any(t["rule"] == "upstream+local-rain" for t in fc["triggers"])


def test_quick_path_and_no_data_use_no_rain_rule(run_ctx):
    assert verdict(ctx_with(ru_of(combined=True)), effort="quick")["verdict"] == "NORMAL"
    ev = ctx_with(ru_of(combined=True))
    ev["usable"] = False
    fc = verdict(ev)
    assert fc["verdict"] == "INSUFFICIENT_DATA" and fc["rain_upstream"]["combined"]       # context on the card only


def test_router_takes_the_full_path_on_heavy_rain():
    reasons = router.data_triggers({"gauges": [], "rain": {}, "met_forecast": {}, "rain_upstream": ru_of(combined=True)},
                                   None, NOW, scene=True)
    assert "heavy rain upstream (kk)" in reasons and "heavy rain here (35.0 mm in 12 h)" in reasons


@pytest.fixture
def run_ctx(tmp_path):
    from app import trace
    trace.start_run("rain rule", log_dir=tmp_path, quiet=True)
    yield
    trace.end_run()


# -- the SYNTHETIC scene end to end ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("SAMPLE_MODE", "true")
    gazetteer.clear_cache()
    out = {}
    try:
        for q in ("Kota Bharu selamat tak?", "Is Pasir Mas at risk?", "Is Tumpat at risk?"):
            out[q.split()[0] if "selamat" in q else q.split()[1]] = loop.run(
                q, quiet=True, replay="synthetic_upstream_rain", at=NOW, log_dir=tmp_path_factory.mktemp("logs"))
    finally:
        gazetteer.clear_cache()
        mp.undo()
    return out


def lines(r):
    return [json.loads(x) for x in open(r["trace"], encoding="utf-8")]


def test_scene_kota_bharu_is_raised_to_prepare_by_the_rain(scene):
    r = scene["Kota"]
    assert r["forecast"]["verdict"] == "PREPARE"
    assert [t["rule"] for t in r["forecast"]["triggers"]] == ["upstream-rain", "upstream+local-rain"]
    rain = next(x for x in lines(r) if x["action"] == "rain.upstream")
    assert rain["target_agent"] == "Forecast" and rain["details"]["combined"] and "Kuala Krai" in rain["output_summary"]
    assert "Hujan lebat di hulu: Kuala Krai" in r["answer"]["text"] and "Sungai kecil" in r["answer"]["text"]
    assert r["answer"]["approved"] and not r["answer"]["safety"]


def test_scene_pasir_mas_capped_and_tumpat_says_thailand_not_checked(scene):
    assert scene["Pasir"]["forecast"]["verdict"] == "WATCH"
    assert "masa sampai" not in scene["Pasir"]["answer"]["text"] and "arrival time not known" in scene["Pasir"]["answer"]["text"]
    t = scene["Tumpat"]
    assert t["forecast"]["verdict"] == "WATCH" and "(Waeng; Thailand)" in t["answer"]["text"]
    assert "not checked yet" not in t["answer"]["text"]               # Thai-side points have data now


def test_scene_uses_no_rain_after_the_scene_time(scene):
    ru = scene["Kota"]["forecast"]["rain_upstream"]
    assert ru["archive"] and all(u["next_24h_mm"] is None for u in ru["upstream"]) and ru["local"]["until"] is None


def test_public_screen_says_why_in_plain_words(scene):
    from app import view
    v = view.answer_view(scene["Kota"])
    assert v["headline"]["en"] == "Get ready" and v["why"]["en"].startswith(
        "Heavy rain upstream (Kuala Krai) may reach here in 9-17 hours while it is also raining heavily here")
    assert "hujan lebat di hulu yang sampai ketika hujan lebat di sini" in v["combined"]["ms"]
    assert v["upstream"]["en"][0].startswith("Heavy rain upstream: Kuala Krai") and "rain upstream" in v["strip"]["en"]
    assert "Heavy rain here: 34.7 mm in 12 h." in v["rain_more"]["en"] and "Heavy rain upstream" in v["share"]["en"]


# -- Cowork 24 Oct: Thai-side Golok rain points, tide advice, MetMalaysia warnings (rule A) -------------------------
GOLOK = [{"from_key": "JENOB", "to_key": "RP", "link_type": "upstream_of", "lag_min_h": None, "lag_max_h": None}]


def thai_town(mm_per_h):
    pts = {"golok_buketa": {**point("Sg. Golok di Buke Ta (Waeng; Thailand)", "JENOB", mm_per_h), "thai": True},
           "rp": point("Sg. Golok di Rantau Panjang (F1)", "RP", 0.2)}
    return rain_rule.assess(["RP"], "rp", pts, GOLOK, golok=True)


def test_thai_points_are_upstream_of_rantau_panjang_with_unknown_arrival(run_ctx):
    a = thai_town(2.0)                                         # 144 mm in 72 h: heavy
    assert a["thai_points"] == ["golok_buketa"] and a["heavy_upstream"] == ["golok_buketa"]
    assert a["upstream"][0]["window"] is None and not a["golok"]      # data exists -> no "not checked" line
    ev = ctx_with(a)
    assert verdict(ev)["verdict"] == "WATCH"                    # unknown arrival: never above Keep watching


def test_thai_rain_line_replaces_not_checked(run_ctx):
    from app import card as card_mod
    light = card_mod.rain_up(thai_town(0.05))                  # 3.6 mm in 72 h: not heavy
    lines = dict(card_mod.rain_lines({"rain_up": light}, "en"))
    assert lines["thailand"] == "Rain upstream in Thailand: Buke Ta (Waeng; Thailand) 3.6 mm in 3 days (arrival time not known)."
    none = card_mod.rain_up(rain_rule.assess(["RP"], "rp", {"rp": point("RP", "RP", 0.2)}, GOLOK, golok=True))
    assert dict(card_mod.rain_lines({"rain_up": none}, "ms"))["thailand"] == "Hujan di hulu di Thailand belum disemak."


@pytest.mark.parametrize("verdict_,tidal,shown", [("WATCH", True, True), ("ACT", True, True), ("NORMAL", True, False),
                                                  ("PREPARE", False, False)])
def test_tide_advice_for_tidal_towns_at_keep_watching_or_higher(verdict_, tidal, shown):
    from app import card as card_mod
    c = {"tide_advice": tidal and verdict_ in ("WATCH", "PREPARE", "ACT"), "rain_up": None}
    assert (("tide", "High tide can keep water in town longer.") in card_mod.rain_lines(c, "en")) is shown


def test_scene_tide_line_on_kota_bharu_and_no_verdict_change(scene):
    r = scene["Kota"]
    assert "Air pasang boleh membuat air bertakung lebih lama di bandar." in r["answer"]["text"]
    assert r["forecast"]["verdict"] == "PREPARE"                # same as without the line


@pytest.mark.xfail(strict=True, reason="Rule A (review pack): MET Waspada -> at least WATCH, Buruk/Bahaya -> at least "
                                       "PREPARE. Not applied in the verdict yet (warnings only pick the full path) - "
                                       "reported to Cowork 24 Oct; not changed without Cowork.")
@pytest.mark.parametrize("heading,expected", [("Amaran Hujan Berterusan (Tahap Waspada)", "WATCH"),
                                              ("Amaran Hujan Berterusan (Tahap Bahaya)", "PREPARE")])
def test_met_warning_raises_the_verdict_as_rule_a_says(run_ctx, heading, expected):
    ev = ctx_with(None)
    ev["met_warnings"] = {"status": "ok", "active": [{"heading": heading}]}
    assert verdict(ev)["verdict"] == expected


def test_trace_lines_for_tide_advice_and_met_warning(scene, run_ctx):
    assert any(x["action"] == "card.advice" and "High tide" in x["output_summary"] for x in lines(scene["Kota"]))
    ev = ctx_with(None)
    ev["met_warnings"] = {"status": "ok", "active": [{"heading": "Amaran Hujan Berterusan (Tahap Waspada)"}]}
    verdict(ev)
    from app import trace
    rec = [json.loads(x) for x in trace.current_run().path.read_text(encoding="utf-8").splitlines()]
    met = next(x for x in rec if x["action"] == "forecast.met_warning")
    assert "not in the verdict yet" in met["decision"] and met["status"] == "fallback"
