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
    # Cowork 24 Oct (demo UI round): plain rows on the screen, the numbers in Details
    assert v["upstream"]["en"][0] == ("Very heavy rain upstream over the last 3 days. That water flows down towards "
                                      "here. It may reach here in about 9 to 17 hours.")
    assert v["rain"]["en"] == "Heavy rain here in the last day." and v["strip"]["en"] == "✓ Checked twice, using 6 sources"
    assert not any(c.isdigit() for c in v["rain"]["en"] + " ".join(v["rain_more"]["en"]).split("until")[0])
    assert any(x.startswith("Heavy rain upstream: Kuala Krai") for x in v["rain_detail"]["en"])
    assert "Heavy rain here: 34.7 mm in 12 h." in v["rain_detail"]["en"]
    assert v["share"]["en"].splitlines()[:2] == ["🟠 Kota Bharu: GET READY (level 3 of 4)",
                                                 "Heavy rain upstream is on its way, and it is raining hard here."]
    assert "Kuala Krai" not in v["share"]["en"] and "SYNTHETIC" in v["share"]["en"]


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
    assert "Air pasang boleh menyebabkan air banjir lambat surut di bandar." in r["answer"]["text"]
    assert r["forecast"]["verdict"] == "PREPARE"                # same as without the line


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
    assert met["output_summary"] == "rain warning (Waspada) → minimum WATCH" and met["status"] == "success"


@pytest.mark.parametrize("heading,expected", [
    ("CONTINUOUS RAIN WARNING (ALERT LEVEL)", ("waspada", "WATCH")),
    ("CONTINUOUS RAIN WARNING (SEVERE LEVEL)", ("buruk", "PREPARE")),
    ("Amaran Hujan Berterusan (Tahap Buruk)", ("buruk", "PREPARE")),
    ("CONTINUOUS RAIN WARNING (DANGER LEVEL)", ("bahaya", "PREPARE")),
    ("THUNDERSTORMS WARNING", (None, None)),                     # no level -> sets nothing
])
def test_warning_level_from_the_heading(heading, expected):
    assert forecast_agent.warning_level(heading) == expected


def test_met_warning_only_raises_never_lowers(run_ctx):
    ev = ctx_with(None, level=5.5)                               # river above Danger: ACT
    ev["met_warnings"] = {"status": "ok", "active": [{"heading": "Amaran Hujan Berterusan (Tahap Waspada)"}]}
    assert verdict(ev)["verdict"] == "ACT"
    ev = ctx_with(None)
    ev["met_warnings"] = {"status": "ok", "active": [{"heading": "THUNDERSTORMS WARNING"}]}
    assert verdict(ev)["verdict"] == "NORMAL"


def test_line_under_the_verdict_names_the_warning(run_ctx):
    from app import view
    ev = ctx_with(None)
    ev["met_warnings"] = {"status": "ok", "active": [{"heading": "CONTINUOUS RAIN WARNING (DANGER LEVEL)"}]}
    fc = verdict(ev)
    assert fc["verdict"] == "PREPARE" and view.set_by(fc) == "met_warning"
    card = {"verdict": "PREPARE", "gauge": {"level_m": 1.0, "read_at": "24 Oct 10:00"}, "comparison": {}, "replay": None}
    assert view._line(card, fc, "en") == "MetMalaysia has an official danger-level rain warning for this district."
    assert view._line(card, fc, "ms") == "MetMalaysia mengeluarkan amaran hujan rasmi tahap Bahaya untuk daerah ini."
    assert view.why(fc, "en").endswith("that sets at least “Get ready”.")


# -- Cowork 24 Oct: no river reading + Buruk / Bahaya -> Get ready; thunderstorm -> flash-flood advice ----------
def no_river(heading):
    ev = ctx_with(None)
    ev["usable"] = False
    ev["met_warnings"] = {"status": "ok", "active": [{"heading": heading}]}
    return ev


@pytest.mark.parametrize("heading,expected", [("Amaran Hujan Berterusan (Tahap Bahaya)", "PREPARE"),
                                              ("CONTINUOUS RAIN WARNING (SEVERE LEVEL)", "PREPARE"),
                                              ("CONTINUOUS RAIN WARNING (ALERT LEVEL)", "INSUFFICIENT_DATA"),
                                              ("THUNDERSTORMS WARNING", "INSUFFICIENT_DATA")])
def test_no_river_reading_with_a_severe_warning_gets_ready(run_ctx, heading, expected):
    fc = verdict(no_river(heading))
    assert fc["verdict"] == expected and fc["no_river"]
    if expected == "PREPARE":
        assert fc["triggers"][0]["rule"] == "met-warning-no-river" and fc["confidence"]["label"] == "low"


def test_no_river_get_ready_card_and_screen(run_ctx):
    from app import card as card_mod, view
    ev = no_river("Amaran Hujan Berterusan (Tahap Bahaya)")
    fc = verdict(ev)
    c = card_mod.build({"place": {"name": "Kota Bharu"}}, ev, fc)
    assert c["gauge"] is None and c["no_river"]                 # a stale level is never shown as current
    text = card_mod.render(c, "en")
    assert "Kota Bharu: PREPARE" in text and "No fresh reading from this place's main river gauge." in text
    assert view._line(c, fc, "en") == ("MetMalaysia has an official danger-level rain warning for this district. We could "
                                       "not get a river reading, so please get ready now.")
    assert view._line(c, fc, "ms").endswith("Kami tidak dapat bacaan sungai, jadi sila bersedia sekarang.")
    assert view.combined(fc, "en") is None
    from app import trace
    rec = [json.loads(x) for x in trace.current_run().path.read_text(encoding="utf-8").splitlines()]
    assert any(x["output_summary"] == "rain warning (Bahaya) + no river reading → PREPARE" for x in rec)


def test_thunderstorm_warning_adds_advice_at_any_verdict_and_changes_nothing(run_ctx):
    from app import card as card_mod
    ev = ctx_with(None)
    ev["met_warnings"] = {"status": "ok", "active": [{"heading": "THUNDERSTORMS WARNING"}]}
    fc = verdict(ev)
    assert fc["verdict"] == "NORMAL" and fc["thunderstorm"]
    c = card_mod.build({"place": {"name": "Kota Bharu"}}, ev, fc)
    assert ("thunder", "Thunderstorm warning: small streams and drains can rise within an hour or two.") in \
        card_mod.rain_lines(c, "en")
    assert dict(card_mod.rain_lines(c, "ms"))["thunder"].startswith("Amaran ribut petir:")
    from app import trace
    rec = [json.loads(x) for x in trace.current_run().path.read_text(encoding="utf-8").splitlines()]
    assert any(x["action"] == "forecast.thunderstorm" and x["output_summary"] == "thunderstorm warning → flash-flood advice"
               for x in rec)
    assert not forecast_agent.thunderstorm([{"heading": "CONTINUOUS RAIN WARNING (ALERT LEVEL)"}])


# -- audit 24 Oct P1-2: an old rain_upstream fact is never reused as current ------------------------------------
@pytest.mark.parametrize("second", [("synthetic_calm", datetime(2024, 6, 15, 10, 0, tzinfo=MYT)),
                                    ("synthetic_upstream_rain", NOW)])
def test_rain_upstream_not_read_this_run_is_not_used(tmp_path, monkeypatch, second):
    """Repro: the upstream-rain scene, then a second run on the same World Model whose hourly-rain query gives
    nothing -> the old rain picture must not raise the verdict, and the source list says it was not read."""
    from app import view
    from app.agents import data_agent
    from app.engines.world_model.world import WorldModel
    monkeypatch.setenv("SAMPLE_MODE", "true")
    gazetteer.clear_cache()
    world = WorldModel()
    first = loop.run("Kota Bharu selamat tak?", quiet=True, replay="synthetic_upstream_rain", at=NOW, world=world,
                     log_dir=tmp_path)
    assert first["forecast"]["verdict"] == "PREPARE"
    monkeypatch.setattr(data_agent.veda_ingest, "ingest_rain_hours", lambda *a, **k: None)
    scene, at = second
    r = loop.run("Kota Bharu selamat tak?", quiet=True, replay=scene, at=at, world=world, log_dir=tmp_path)
    gazetteer.clear_cache()
    assert r["forecast"]["verdict"] != "PREPARE" and not r["forecast"].get("rain_upstream")
    assert "upstream-rain" not in [t["rule"] for t in r["forecast"]["triggers"]]
    assert "Kuala Krai" not in r["answer"]["text"]
    row = next(s for s in view.sources(r["evidence"], r["plan"], "en") if s["kind"] == "rain_upstream")
    assert not row["used"] and "could not be read" in row["note"]


# -- audit 24 Oct P3 --------------------------------------------------------------------------------------------
def test_thresholds_compare_the_unrounded_sum():
    """99.96 mm in 72 h is shown as 100.0 but is not >= 100 mm."""
    f = rain_rule.features([(NOW - timedelta(hours=k), 99.96 / 72) for k in range(72)], NOW)
    assert f["past_72h_mm"] == 100.0 and rain_rule.heavy_upstream(f) == (False, False)
    f = rain_rule.features([(NOW - timedelta(hours=k), 100.0 / 72) for k in range(72)], NOW)
    assert rain_rule.heavy_upstream(f)[0]


def test_then_easing_only_when_the_rain_stops_inside_the_data():
    from app import card
    stops = rain_rule.features(hours(0, back=1) + [(NOW + timedelta(hours=k), 5.0 if k <= 3 else 0.0)
                                                   for k in range(1, 13)], NOW)
    lasts = rain_rule.features(hours(5.0, back=1, ahead=12), NOW)
    assert stops["until_ends"] and not lasts["until_ends"]
    for f, easing in ((stops, True), (lasts, False)):
        r = {"heavy": [], "local_12h_mm": None, "local_heavy": False, "until": f["until"], "until_heavy": False,
             "until_ends": f["until_ends"], "golok": False, "combined": False, "thai": []}
        text = " ".join(t for _, t in card.rain_lines({"rain_up": r}, "en"))
        assert ("then easing" in text) is easing and ("at least" in text) is not easing


def test_met_warning_names_bahaya_when_buruk_is_also_active(run_ctx):
    ev = ctx_with(None)
    ev["met_warnings"] = {"status": "ok", "active": [{"heading": "Amaran Hujan Berterusan (Tahap Buruk)"},
                                                     {"heading": "Amaran Hujan Berterusan (Tahap Bahaya)"}]}
    fc = verdict(ev)
    assert fc["verdict"] == "PREPARE" and any("Bahaya" in t["reason"] for t in fc["triggers"])
    assert not any("Buruk" in t["reason"] for t in fc["triggers"])
