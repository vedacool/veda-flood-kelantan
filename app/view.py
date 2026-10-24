"""The public answer screen as data (Cowork weekend plan B, 24 Oct): the run's card, forecast and evidence turned into
short plain pieces in English and Bahasa Melayu, for people, not engineers - no rule names, no agent names.

    view = answer_view(result)          # result = loop.run(...); returned by the API as result["view"]
    words()                             # fixed wording for screens that call no engine (emergency, headlines)

Read-only: nothing here changes a verdict, an action or the Coordinator's explanation; it only re-words what the
engine already decided. The user's question and the trace never go into a view (the share text is built from it).
"""
import json
import re
from datetime import datetime

from app import card as card_mod
from app import trace
from app.agents.coordinator import SAFETY
from app.config import MYT, REPLAYS

LANGS = ("en", "ms")
HEADLINE = {  # Cowork 24 Oct; also in docs/review_pack_ariff.md section G
    "NORMAL": {"en": "Normal for now", "ms": "Normal buat masa ini"},
    "WATCH": {"en": "Keep watching", "ms": "Terus berjaga-jaga"},
    "PREPARE": {"en": "Get ready", "ms": "Bersedia"},
    "ACT": {"en": "Act now", "ms": "Bertindak sekarang"},
    "INSUFFICIENT_DATA": {"en": "Can't confirm right now", "ms": "Tidak dapat disahkan sekarang"},
}
LEVEL = {"alert": {"en": "alert", "ms": "Waspada"}, "warning": {"en": "warning", "ms": "Amaran"},
         "danger": {"en": "danger", "ms": "Bahaya"}}
W = {
    "river_vs": {"en": "The river is {d} m {side} the {name} level", "ms": "Paras sungai {d} m {side} paras {name}"},
    "above": {"en": "above", "ms": "di atas"}, "below": {"en": "below", "ms": "di bawah"},
    "and": {"en": " and {t}.", "ms": " dan {t}."},
    "trend": {"rising": {"en": "still rising", "ms": "masih naik"}, "falling": {"en": "falling", "ms": "sedang turun"},
              "steady": {"en": "steady", "ms": "stabil"}},
    "no_reading": {"en": "VEDA has no fresh river reading for this place right now.",
                   "ms": "VEDA tiada bacaan sungai terkini untuk tempat ini sekarang."},
    "no_reading_past": {"en": "There is no checked river reading near this time.",
                        "ms": "Tiada bacaan sungai yang disahkan berhampiran masa ini."},
    "water": {"en": "{m} m at {t}", "ms": "{m} m pada {t}"},
    "rate_up": {"en": "rising {r} cm an hour", "ms": "naik {r} cm sejam"},
    "rate_down": {"en": "falling {r} cm an hour", "ms": "turun {r} cm sejam"},
    "rate_flat": {"en": "about the same", "ms": "lebih kurang sama"},
    "change_3h_up": {"en": "up {c} cm in 3 hours", "ms": "naik {c} cm dalam 3 jam"},
    "change_3h_down": {"en": "down {c} cm in 3 hours", "ms": "turun {c} cm dalam 3 jam"},
    "change_3h_flat": {"en": "no change in 3 hours", "ms": "tiada perubahan dalam 3 jam"},
    "tidal": {"en": "the sea tide moves this river, so no trend", "ms": "pasang surut laut menggerakkan sungai ini, "
                                                                        "jadi tiada trend"},
    "vs_level": {"en": "{d} m {side} the {name} level ({t} m)", "ms": "{d} m {side} paras {name} ({t} m)"},
    "up_none": {"en": "No fresh reading upstream ({where}) - VEDA can't see what may be coming.",
                "ms": "Tiada bacaan terkini di hulu ({where}) - VEDA tidak dapat melihat apa yang mungkin sampai."},
    "up_ok": {"en": "{where}: normal", "ms": "{where}: normal"},
    "up_high": {"en": "{where}: at the {name} level", "ms": "{where}: pada paras {name}"},
    "up_rising": {"en": ", rising", "ms": ", sedang naik"},
    "up_window": {"en": "; may reach here in {a}-{b} hours", "ms": "; mungkin sampai ke sini dalam {a}-{b} jam"},
    "rain_next": {"en": "{mm} mm expected in the next 24 hours", "ms": "{mm} mm dijangka dalam 24 jam akan datang"},
    "rain_past": {"en": "{mm} mm fell in the 24 hours before this time", "ms": "{mm} mm turun dalam 24 jam sebelum masa ini"},
    "checked2": {"en": "Double-checked", "ms": "Disemak dua kali"},
    "checked1": {"en": "Checked", "ms": "Disemak"},
    "combined": {"en": "combined from {n} sources: {kinds}", "ms": "digabung daripada {n} sumber: {kinds}"},
    "n_left_out": {"en": "{n} left out", "ms": "{n} diketepikan"},
    "from_live": {"en": "official river gauge", "ms": "stesen sungai rasmi"},
    "from_reported": {"en": "reading reported in the news", "ms": "bacaan yang dilaporkan dalam berita"},
    "from_estimated": {"en": "estimate between reported readings", "ms": "anggaran antara bacaan yang dilaporkan"},
    "from_made_up": {"en": "made-up test reading", "ms": "bacaan ujian rekaan"},
    "calm_note": {"en": "Nothing to do now. VEDA checks again whenever you ask.",
                  "ms": "Tiada apa perlu dibuat sekarang. VEDA menyemak semula setiap kali anda bertanya."},
    "cant_confirm": {"en": "We could not get a fresh river reading, so we will not guess. Check JPS Infobanjir; call 999 "
                           "if you are in danger.",
                     "ms": "Kami tidak dapat bacaan sungai terkini, jadi kami tidak akan meneka. Semak JPS Infobanjir; "
                           "hubungi 999 jika anda dalam bahaya."},
    "covers": {"en": "VEDA covers Rantau Panjang, Pasir Mas, Kota Bharu and Tumpat for now.",
               "ms": "Buat masa ini VEDA meliputi Rantau Panjang, Pasir Mas, Kota Bharu dan Tumpat."},
    "nearest": {"en": " The nearest is {place}.", "ms": " Yang paling dekat ialah {place}."},
    "did_you_mean": {"en": "Did you mean one of these?", "ms": "Adakah maksud anda salah satu daripada ini?"},
    "down": {"en": "VEDA can't answer right now. If you are in danger call 999.",
             "ms": "VEDA tidak dapat menjawab sekarang. Jika anda dalam bahaya, hubungi 999."},
    "combined_why": {"en": "The river here alone would say \u201c{alone}\u201d; it is {who} that {verb} this to \u201c{now}\u201d.",
                     "ms": "Sungai di sini sahaja akan menunjukkan \u201c{alone}\u201d; {who} yang menaikkannya kepada "
                           "\u201c{now}\u201d."},
    "who_upstream": {"en": "the river upstream", "ms": "sungai di hulu"},
    "who_rain": {"en": "the rain forecast", "ms": "ramalan hujan"},
    "who_rain_up": {"en": "the heavy rain upstream", "ms": "hujan lebat di hulu"},
    "who_met": {"en": "the official MetMalaysia rain warning", "ms": "amaran hujan rasmi MetMalaysia"},
    "who_rain_both": {"en": "the heavy rain upstream arriving while it rains heavily here",
                      "ms": "hujan lebat di hulu yang sampai ketika hujan lebat di sini"},
    "and_word": {"en": " and ", "ms": " dan "},
    "from_none": {"en": "no fresh river reading", "ms": "tiada bacaan sungai terkini"},
    "label_replay": {"en": "Past flood replay · {when}", "ms": "Ulang tayang banjir lalu · {when}"},
    "label_synthetic": {"en": "Made-up test scene · {when}", "ms": "Senario ujian rekaan · {when}"},
    "used": {"en": "used", "ms": "digunakan"},
    "left_out": {"en": "left out: {why}", "ms": "diketepikan: {why}"},
    "not_used": {"en": "not used: {why}", "ms": "tidak digunakan: {why}"},
}
WHY = {  # one sentence per verdict rule, plain words (the rule names stay in the trace)
    "level>=danger": {"en": "The river is at or above the danger level.", "ms": "Paras sungai pada atau melebihi paras Bahaya."},
    "level>=warning": {"en": "The river is at or above the warning level.", "ms": "Paras sungai pada atau melebihi paras Amaran."},
    "level>=alert": {"en": "The river is at or above the alert level.", "ms": "Paras sungai pada atau melebihi paras Waspada."},
    "danger<=12h": {"en": "At its current rate the river could reach the danger level in about {h} hours.",
                    "ms": "Pada kadar sekarang, sungai boleh sampai ke paras Bahaya dalam kira-kira {h} jam."},
    "danger<=24h": {"en": "At its current rate the river could reach the danger level in about {h} hours.",
                    "ms": "Pada kadar sekarang, sungai boleh sampai ke paras Bahaya dalam kira-kira {h} jam."},
    "alert<=24h": {"en": "At its current rate the river could reach the alert level in about {h} hours.",
                   "ms": "Pada kadar sekarang, sungai boleh sampai ke paras Waspada dalam kira-kira {h} jam."},
    "sentinel>=danger": {"en": "The river upstream at {where} is at the danger level{window}.",
                         "ms": "Sungai di hulu ({where}) pada paras Bahaya{window}."},
    "sentinel>=alert": {"en": "The river upstream at {where} is high{window}.",
                        "ms": "Sungai di hulu ({where}) tinggi{window}."},
    "window": {"en": "; the water may reach here in {a}-{b} hours", "ms": "; air mungkin sampai ke sini dalam {a}-{b} jam"},
    "upstream-rain": {"en": "Heavy rain has fallen upstream ({where}, {mm} mm in 3 days); {when}.",
                      "ms": "Hujan lebat telah turun di hulu ({where}, {mm} mm dalam 3 hari); {when}."},
    "upstream-rain-fc": {"en": "Heavy rain is forecast upstream ({where}, {mm} mm in 24 hours).",
                         "ms": "Hujan lebat dijangka di hulu ({where}, {mm} mm dalam 24 jam)."},
    "when_known": {"en": "the water may reach here in {a}-{b} hours", "ms": "air mungkin sampai ke sini dalam {a}-{b} jam"},
    "when_unknown": {"en": "when it reaches here is not known", "ms": "bila ia sampai ke sini tidak diketahui"},
    "upstream+local-rain": {"en": "Heavy rain upstream ({where}) may reach here in {a}-{b} hours while it is also raining "
                                  "heavily here ({mm} mm in 12 hours), so VEDA moved up one step.",
                            "ms": "Hujan lebat di hulu ({where}) mungkin sampai ke sini dalam {a}-{b} jam ketika hujan "
                                  "lebat juga di sini ({mm} mm dalam 12 jam), jadi VEDA naikkan satu tahap."},
    "met-warning": {"en": "MetMalaysia has an official {level} rain warning for this district; that sets at least "
                          "“{min}”.",
                    "ms": "MetMalaysia mengeluarkan amaran hujan rasmi tahap {level} untuk daerah ini; ini menetapkan "
                          "sekurang-kurangnya “{min}”."},
    "rain-heavy": {"en": "Heavy rain is forecast: {n24} mm in 24 hours, {n72} mm in 3 days.",
                   "ms": "Hujan lebat dijangka: {n24} mm dalam 24 jam, {n72} mm dalam 3 hari."},
    "rain-wet-ground": {"en": "{n72} mm of rain is forecast in 3 days, on ground already wet from the past week.",
                        "ms": "{n72} mm hujan dijangka dalam 3 hari, di atas tanah yang sudah basah sejak minggu lepas."},
    "rising-fast": {"en": "The river is rising fast, so VEDA moved up one step.",
                    "ms": "Paras sungai naik dengan cepat, jadi VEDA naikkan satu tahap."},
    "no-trigger": {"en": "The river is below the alert level and nothing else points to a flood.",
                   "ms": "Paras sungai di bawah paras Waspada dan tiada tanda lain banjir."},
    "fail-safe": {"en": "VEDA has no fresh, checked river reading for this place, so it will not guess.",
                  "ms": "VEDA tiada bacaan sungai terkini yang disahkan untuk tempat ini, jadi ia tidak meneka."},
}
KIND = {  # the strip's short names for the kinds of source used
    "river": {"en": "river here", "ms": "sungai di sini"}, "upstream": {"en": "river upstream", "ms": "sungai di hulu"},
    "rain": {"en": "rain", "ms": "hujan"}, "forecast": {"en": "forecast", "ms": "ramalan"},
    "warnings": {"en": "warnings", "ms": "amaran"}, "flood_warnings": {"en": "flood warnings", "ms": "amaran banjir"},
    "map": {"en": "map", "ms": "peta"}, "rain_upstream": {"en": "rain upstream", "ms": "hujan di hulu"},
}
SOURCE_NAME = {
    "open_meteo": {"en": "Rain forecast (Open-Meteo)", "ms": "Ramalan hujan (Open-Meteo)"},
    "open_meteo_past": {"en": "Rain record (Open-Meteo archive)", "ms": "Rekod hujan (arkib Open-Meteo)"},
    "mygov_forecast": {"en": "MetMalaysia forecast", "ms": "Ramalan MetMalaysia"},
    "mygov_warning": {"en": "MetMalaysia warnings", "ms": "Amaran MetMalaysia"},
    "cross": {"en": "Flood warnings (data.gov.my)", "ms": "Amaran banjir (data.gov.my)"},
    "osm": {"en": "Map data (OpenStreetMap)", "ms": "Data peta (OpenStreetMap)"},
    "rain_up": {"en": "Rain upstream ({n} rain points, Open-Meteo)", "ms": "Hujan di hulu ({n} titik hujan, Open-Meteo)"},
    "river": {"en": "River level: {name}", "ms": "Paras sungai: {name}"},
    "upstream": {"en": "River upstream: {name}", "ms": "Sungai di hulu: {name}"},
}
NOT_A_DROP = ("not_needed", "quick", "past")      # not asked for, or not kept for a past date: "not used", not "left out"
LEFT_OUT = {
    "no_reading": {"en": "no reading", "ms": "tiada bacaan"},
    "looked_wrong": {"en": "the reading looked wrong", "ms": "bacaan kelihatan salah"},
    "too_old": {"en": "reading too old ({age})", "ms": "bacaan terlalu lama ({age})"},
    "past": {"en": "not available for this date", "ms": "tiada untuk tarikh ini"},       # Cowork 24 Oct
    "unreadable": {"en": "could not be read", "ms": "tidak dapat dibaca"},
    "stale": {"en": "out of date", "ms": "sudah lapuk"},
    "quick": {"en": "not needed for a quick check", "ms": "tidak perlu untuk semakan pantas"},
    "not_needed": {"en": "not needed for this question", "ms": "tidak perlu untuk soalan ini"},
}
EMERGENCY = {  # the stranded steps: the card's ACT advice, one step per sentence (no engine call)
    "title": {"en": "If you are stranded or in danger", "ms": "Jika anda terkandas atau dalam bahaya"},
}


def _num(v):
    return card_mod._num(v)


def _place_of(gauge):
    """'Sg. Golok di Kg. Jenob (F1)' -> 'Kg. Jenob' (the place people know); other names lose only '(F1)'."""
    name = re.sub(r"\s*\(F\d\)$", "", gauge or "")
    return name.split(" di ", 1)[1] if " di " in name else name


def _cm(v):
    return int(round(abs(v) * 100))


def _range_cm(lo, hi):
    a, b = sorted((_cm(lo), _cm(hi)))
    return str(a) if a == b else f"{a}-{b}"


def _when(iso, lang, with_year=True):
    """'2024-11-27T19:30:00+08:00' -> '27 Nov 2024, 19:30' (BM months for 'ms')."""
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(MYT)
    except ValueError:
        return None
    text = t.strftime("%d %b %Y, %H:%M" if with_year else "%d %b %H:%M").lstrip("0")
    return card_mod.months_ms(text) if lang == "ms" else text


def _both(fn):
    return {lang: fn(lang) for lang in LANGS}


def _main_gauge(evidence):
    ctx = (evidence or {}).get("context") or {}
    return next((g for g in ctx.get("gauges", []) if g["role"] == "controlling"), None)


def _rate(forecast):
    trend = next((c for c in (forecast or {}).get("controlling", []) if c["role"] == "controlling"), {})
    return trend.get("rate_m_per_h")


def _trend(card, forecast):
    """rising / falling / steady from the same rate as the water row (under 0.5 cm an hour = steady), so the two
    lines never disagree; None when unknown or tide-moved."""
    rate = _rate(forecast)
    if card.get("tidal") or not rate:
        return None
    mid = (rate["min"] + rate["max"]) / 2
    return "steady" if abs(mid) < 0.005 else "rising" if mid > 0 else "falling"


RIVER_RULES = ("level>=", "danger<=", "alert<=", "no-trigger", "rising-fast")
SET_BY = {  # Cowork 24 Oct: the line under the badge says what SET the verdict (never a river line that reads as a
    # contradiction when rain or the river upstream raised it)
    "rain_both": {"en": "Heavy rain upstream is on its way, and it is raining hard here.",
                  "ms": "Hujan lebat dari hulu sedang menuju ke sini, dan hujan turun dengan lebat di sini."},
    "rain_up": {"en": "Heavy rain has fallen upstream, and the water may come this way.",
                "ms": "Hujan lebat telah turun di hulu, dan airnya mungkin mengalir ke sini."},
    "upstream_gauge": {"en": "The river upstream is high, and the water may be on its way.",
                       "ms": "Sungai di hulu tinggi, dan airnya mungkin sedang menuju ke sini."},
    "rain_forecast": {"en": "Heavy rain is forecast.", "ms": "Hujan lebat dijangka."},
    "met_warning": {"en": "MetMalaysia has an official {level} rain warning for this district.",
                    "ms": "MetMalaysia mengeluarkan amaran hujan rasmi tahap {level} untuk daerah ini."},
}


def set_by(forecast):
    """Which kind of source set the verdict: 'river' (this town's river), 'upstream_gauge', 'rain_up', 'rain_both' or
    'rain_forecast' - from the triggers at the verdict's level (rising-fast belongs to the town's river)."""
    fc = forecast or {}
    top = [t["rule"] for t in fc.get("triggers") or [] if t["level"] == fc.get("verdict")]
    if not top or any(r.startswith(RIVER_RULES) for r in top):
        return "river"
    r = top[0]
    return ("rain_both" if r == "upstream+local-rain" else "rain_up" if r == "upstream-rain" else
            "upstream_gauge" if r.startswith("sentinel") else "rain_forecast" if r.startswith("rain") else
            "met_warning" if r == "met-warning" else "river")


MET_LEVEL_WORD = {"waspada": {"en": "alert-level", "ms": "Waspada"}, "buruk": {"en": "severe-level", "ms": "Buruk"},
                  "bahaya": {"en": "danger-level", "ms": "Bahaya"}}


def _met_level(forecast):
    """The MetMalaysia warning level behind a 'met-warning' trigger ('waspada' | 'buruk' | 'bahaya'), or None."""
    t = next((t for t in (forecast or {}).get("triggers") or [] if t["rule"] == "met-warning"), None)
    m = re.search(r"MetMalaysia (\w+) rain warning", (t or {}).get("reason", ""))
    return m.group(1).lower() if m and m.group(1).lower() in MET_LEVEL_WORD else None


def _line(card, forecast, lang):
    """The one line under the verdict badge: the reason that set the verdict, in plain words."""
    if card["verdict"] == "INSUFFICIENT_DATA" or not card.get("gauge"):
        return W["no_reading_past"][lang] if card.get("replay") else W["cant_confirm"][lang]
    by = set_by(forecast)
    if by == "met_warning":
        return SET_BY[by][lang].format(level=MET_LEVEL_WORD[_met_level(forecast) or "waspada"][lang])
    if by != "river":
        return SET_BY[by][lang]
    comp, th = card.get("comparison") or {}, card.get("thresholds") or {}
    if comp.get("danger") is not None and comp["danger"] >= 0:
        key = "danger"
    elif comp.get("alert") is not None and comp["alert"] >= 0 and comp.get("danger") is not None:
        key = "danger"
    else:
        key = "alert" if comp.get("alert") is not None else "danger"
    if comp.get(key) is None:
        return W["water"][lang].format(m=_num(card["gauge"]["level_m"]), t=card["gauge"]["read_at"]) + "."
    d = comp[key]
    text = W["river_vs"][lang].format(d=_num(abs(d)), side=W["above" if d >= 0 else "below"][lang],
                                      name=LEVEL[key][lang])
    trend = _trend(card, forecast)
    return text + (W["and"][lang].format(t=W["trend"][trend][lang]) if trend else ".")


def _water(card, forecast, evidence, lang):
    g = card.get("gauge")
    if not g:
        return None
    origin = W[{"live": "from_live", "reported": "from_reported", "estimated": "from_estimated",
                "made_up": "from_made_up"}[_source_kind(card)]][lang]
    parts = [W["water"][lang].format(m=_num(g["level_m"]), t=g["read_at"].split(" ")[-1]) + f" ({origin})"]
    rate, trend = _rate(forecast), _trend(card, forecast)
    if card.get("tidal"):
        parts.append(W["tidal"][lang])
    elif trend == "steady":
        parts.append(W["rate_flat"][lang])
    elif trend:
        parts.append(W["rate_up" if trend == "rising" else "rate_down"][lang].format(r=_range_cm(rate["min"], rate["max"])))
    main = _main_gauge(evidence) or {}
    c3 = main.get("change_3h_m")
    if c3 is not None and not card.get("tidal"):
        key = "change_3h_flat" if _cm(c3) == 0 else "change_3h_up" if c3 > 0 else "change_3h_down"
        parts.append(W[key][lang].format(c=_cm(c3)))
    compare = []
    for key in ("alert", "danger"):
        d = (card.get("comparison") or {}).get(key)
        if d is not None:
            compare.append(W["vs_level"][lang].format(d=_num(abs(d)), side=W["above" if d >= 0 else "below"][lang],
                                                      name=LEVEL[key][lang], t=_num(card["thresholds"][key])))
    # Cowork 24 Oct: the row says ONE plain thing; the numbers above go to Details ("Water in detail")
    return {"main": _water_plain(card, forecast, lang), "detail": [" · ".join(parts)] + compare}


WP = {
    "rising": {"en": "Rising about {r} cm an hour.", "ms": "Naik kira-kira {r} cm sejam."},
    "falling": {"en": "Falling about {r} cm an hour.", "ms": "Turun kira-kira {r} cm sejam."},
    "steady": {"en": "Steady.", "ms": "Stabil."},
    "tidal": {"en": "The sea tide moves this river, so we don't show a trend.",
              "ms": "Pasang surut laut menggerakkan sungai ini, jadi kami tidak menunjukkan trend."},
    "over_danger": {"en": "Already {d} m over the danger mark.", "ms": "Sudah {d} m melebihi paras bahaya."},
    "over_alert": {"en": "Over the alert mark, {d} m under the danger mark.",
                   "ms": "Melebihi paras waspada, {d} m di bawah paras bahaya."},
    "under_alert": {"en": "{d} m under the alert mark.", "ms": "{d} m di bawah paras waspada."},
    "calm": {"en": "Calm, below the alert mark.", "ms": "Tenang, di bawah paras waspada."},
}


def _water_plain(card, forecast, lang):
    """The Water row in plain words: how it moves, and where it stands against the alert / danger marks."""
    comp = card.get("comparison") or {}
    d_alert, d_danger = comp.get("alert"), comp.get("danger")
    if d_danger is not None and d_danger >= 0:
        where = WP["over_danger"][lang].format(d=_num(d_danger))
    elif d_alert is not None and d_alert >= 0:
        where = WP["over_alert"][lang].format(d=_num(abs(d_danger))) if d_danger is not None else ""
    else:
        where = None                                                   # below the alert mark (or no marks)
    if card.get("tidal"):
        return WP["tidal"][lang] + (f" {where}" if where else "")
    trend, rate = _trend(card, forecast), _rate(forecast)
    if where is None and trend != "rising":
        return WP["calm"][lang] if d_alert is not None else WP["steady"][lang]
    move = (WP[trend][lang].format(r=_range_cm(rate["min"], rate["max"])) if trend in ("rising", "falling")
            else WP["steady"][lang] if trend else "")
    if where is None:
        where = WP["under_alert"][lang].format(d=_num(abs(d_alert))) if d_alert is not None else ""
    return " ".join(x for x in (move, where) if x)


def _upstream(forecast, lang):
    rows = []
    for u in (forecast or {}).get("upstream", []):
        where = _place_of(u["gauge"])
        if u.get("status") == "no fresh reading":
            rows.append(W["up_none"][lang].format(where=where))
            continue
        band = u.get("band")
        text = (W["up_high"][lang].format(where=where, name=LEVEL[band][lang]) if band in LEVEL
                else W["up_ok"][lang].format(where=where))
        if u.get("rising"):
            text += W["up_rising"][lang]
        a = u.get("arrives_in_h")
        if a and (band in LEVEL or u.get("rising")):
            text += W["up_window"][lang].format(a=_num(a["min"]), b=_num(a["max"]))
        rows.append(text + ".")
    return rows


def _rain(card, lang):
    if card.get("rain_24h_mm") is not None:
        return W["rain_next"][lang].format(mm=_num(card["rain_24h_mm"]))
    if card.get("rain_past_24h_mm") is not None:
        return W["rain_past"][lang].format(mm=_num(card["rain_past_24h_mm"]))
    return None


def _why_rain(ru, rule, lang):
    """B-88 Why sentences, from the rain picture the Forecast agent used."""
    up = [u for u in ru.get("upstream", []) if u["point"] in ru.get("heavy_upstream", [])]
    if rule == "upstream+local-rain":
        u = next((u for u in up if u["point"] in ru.get("arriving_24h", [])), None)
        if u:
            return WHY[rule][lang].format(where=_place_of(u["name"]), a=_num(u["window"]["min"]),
                                          b=_num(u["window"]["max"]), mm=_num((ru.get("local") or {}).get("max_12h_mm")))
    u = next((u for u in sorted(up, key=lambda u: -(u["past_72h_mm"] or 0)) if u["heavy_fallen"]), None)
    if u:
        w = u["window"]
        when = (WHY["when_known"][lang].format(a=_num(w["min"]), b=_num(w["max"])) if w else WHY["when_unknown"][lang])
        return WHY["upstream-rain"][lang].format(where=_place_of(u["name"]), mm=_num(u["past_72h_mm"]), when=when)
    u = next(iter(up), None)
    return WHY["upstream-rain-fc"][lang].format(where=_place_of(u["name"]), mm=_num(u["next_24h_mm"])) if u else ""


def _rain_text(card, lang, keys):
    """B-88: the card's rain lines (same words as the card), for the Upstream / Rain rows."""
    out = [t for k, t in card_mod.rain_lines(card, lang) if k in keys]
    return [card_mod.months_ms(t) for t in out] if lang == "ms" else out


def why(forecast, lang):
    """The Why sentence: the rule(s) that set the verdict, in plain words (rising-fast added when it moved it up)."""
    fc = forecast or {}
    triggers = fc.get("triggers") or []
    verdict = fc.get("verdict", "INSUFFICIENT_DATA")
    top = [t for t in triggers if t["level"] == verdict and t["rule"] != "rising-fast"] or \
          [t for t in triggers if t["rule"] != "rising-fast"][:1]
    out = []
    for t in top[:2]:
        rule = t["rule"]
        tmpl = WHY.get(rule)
        if not tmpl:
            continue
        if rule in ("danger<=12h", "danger<=24h", "alert<=24h"):
            m = re.search(r"about ([\d.]+) h", t.get("reason", ""))
            out.append(tmpl[lang].format(h=m.group(1) if m else "?"))
        elif rule.startswith("sentinel"):
            band = "danger" if rule.endswith("danger") else None
            up = next((u for u in fc.get("upstream", []) if u.get("band") and (u["band"] == band if band else
                                                                                u["band"] in ("alert", "warning"))), {})
            a = up.get("arrives_in_h")
            window = WHY["window"][lang].format(a=_num(a["min"]), b=_num(a["max"])) if a else ""
            out.append(tmpl[lang].format(where=_place_of(up.get("gauge", "")), window=window))
        elif rule.startswith("rain"):
            r = fc.get("rain") or {}
            out.append(tmpl[lang].format(n24=_num(r.get("next_24h_mm")), n72=_num(r.get("next_72h_mm"))))
        elif rule in ("upstream-rain", "upstream+local-rain"):
            out.append(_why_rain(fc.get("rain_upstream") or {}, rule, lang))
        elif rule == "met-warning":
            out.append(tmpl[lang].format(level=MET_LEVEL_WORD[_met_level(fc) or "waspada"][lang],
                                         min=HEADLINE[t["level"]][lang]))
        else:
            out.append(tmpl[lang])
    if any(t["rule"] == "rising-fast" for t in triggers):
        out.append(WHY["rising-fast"][lang])
    return " ".join(dict.fromkeys(out))


GAUGE_RULES = ("level>=", "danger<=", "alert<=")
LEVELS = ("NORMAL", "WATCH", "PREPARE", "ACT")


def combined(forecast, lang):
    """Track 1 (Cowork 24 Oct): when the verdict needed more than the river here, one plain sentence saying which
    other source raised it; None when the river here alone gives the same verdict."""
    fc = forecast or {}
    verdict = fc.get("verdict")
    if verdict not in LEVELS:
        return None
    triggers = fc.get("triggers") or []
    alone = max((LEVELS.index(t["level"]) for t in triggers if t["rule"].startswith(GAUGE_RULES)
                 and t["level"] in LEVELS), default=0)
    if any(t["rule"] == "rising-fast" for t in triggers):
        alone = min(alone + 1, len(LEVELS) - 1)
    if alone >= LEVELS.index(verdict):
        return None
    raisers = [t["rule"] for t in triggers if t["level"] == verdict]
    who = [W[k][lang] for k, pre in (("who_upstream", "sentinel"), ("who_rain", "rain")) if any(r.startswith(pre) for r in raisers)]
    if "met-warning" in raisers:                               # rule A
        who.append(W["who_met"][lang])
    if "upstream+local-rain" in raisers:                       # B-88
        who.append(W["who_rain_both"][lang])
    elif "upstream-rain" in raisers:
        who.append(W["who_rain_up"][lang])
    if not who:
        return None
    return W["combined_why"][lang].format(alone=HEADLINE[LEVELS[alone]][lang], who=W["and_word"][lang].join(who),
                                          now=HEADLINE[verdict][lang], verb="raises" if len(who) == 1 else "raise")


def other_view(result):
    """The screens without a place card: place not covered (with the nearest covered place), did you mean, or VEDA
    cannot answer (its data cannot be reached)."""
    plan = result.get("plan") or {}
    status = plan.get("place_status")
    if status == "unavailable":
        return {"kind": "down", "text": dict(W["down"])}
    if status == "did_you_mean":
        sug = [x.get("name") if isinstance(x, dict) else x for x in (plan.get("suggestions") or [])]
        return {"kind": "did_you_mean", "text": dict(W["did_you_mean"]), "suggestions": [x for x in sug if x]}
    if status == "not_covered":
        near = (plan.get("nearest") or {}).get("name")
        return {"kind": "not_covered", "nearest": near,
                "text": {lang: W["covers"][lang] + (W["nearest"][lang].format(place=near) if near else "")
                         for lang in LANGS}}
    return None


def _source_kind(card):
    if card.get("synthetic"):
        return "made_up"
    label = card.get("reading_label") or ""
    if label.startswith("reconstructed"):
        return "estimated"
    if card.get("replay"):
        return "reported"
    return "live"


def _strip(answer, rows, lang):
    """Cowork 24 Oct: '✓ Double-checked · combined from N sources: river here, river upstream, rain · 1 left out'."""
    tick = W["checked2" if answer.get("approved") else "checked1"][lang]
    used = [r for r in rows if r["used"]]
    kinds = list(dict.fromkeys(KIND[r["kind"]][lang] for r in used))
    text = f"✓ {tick} · " + (W["combined"][lang].format(n=len(used), kinds=", ".join(kinds)) if used
                             else W["from_none"][lang])
    out = sum(1 for r in rows if r["left_out"])
    return text + (f" · {W['n_left_out'][lang].format(n=out)}" if out else "")


def _label(evidence, lang):
    scene = (evidence or {}).get("replay") or {}
    sc = REPLAYS.get(scene.get("scenario"))
    if not sc:
        return None
    when = _when(scene.get("at"), lang) or ""
    return W["label_synthetic" if sc["kind"] == "synthetic" else "label_replay"][lang].format(when=when)


def _age(minutes, lang):
    return card_mod._age(minutes, lang)


def sources(evidence, plan, lang):
    """Every source looked at: used, or left out with why (built from the same evidence as the trace line)."""
    ev = evidence or {}
    ctx = ev.get("context") or {}
    out = []
    for g in ctx.get("gauges", []) + ctx.get("sentinels", []):
        key = "upstream" if g["role"] == "sentinel" else "river"
        name = SOURCE_NAME[key][lang].format(name=re.sub(r"\s*\(F\d\)$", "", g["name"]))
        if g["level_m"] is None:
            out.append((key, name, "no_reading", None))
        elif not (g.get("health") or {"ok": True})["ok"]:
            out.append((key, name, "looked_wrong", None))
        elif g.get("freshness") in ("stale", "unknown"):
            out.append((key, name, "too_old", g.get("age_minutes")))
        else:
            out.append((key, name, None, None))
    srcs = ev.get("sources") or {}
    past = bool(ev.get("replay"))
    for key in ("open_meteo", "mygov_forecast", "mygov_warning"):
        s = srcs.get(key) or {}
        name = SOURCE_NAME["open_meteo_past" if key == "open_meteo" and past else key][lang]
        status, note = s.get("status"), (s.get("note") or "")
        kind = {"open_meteo": "rain", "mygov_forecast": "forecast", "mygov_warning": "warnings"}[key]
        if status in ("ok", "stale", "degraded"):
            out.append((kind, name, None, None))
        elif "replay" in note or "archive" in note:
            out.append((kind, name, "past", None))
        elif status == "skipped":
            out.append((kind, name, "not_needed", None))
        else:
            out.append((kind, name, "unreadable", None))
    cross = ev.get("cross_check")
    if cross:
        reason = {"ok": None, "stale": "stale", "not_checked": "unreadable"}.get(cross.get("status"), "unreadable")
        out.append(("flood_warnings", SOURCE_NAME["cross"][lang], reason, None))
    elif (plan or {}).get("effort") == "quick":
        out.append(("flood_warnings", SOURCE_NAME["cross"][lang], "quick", None))
    osm = ev.get("osm")
    if osm:
        out.append(("map", SOURCE_NAME["osm"][lang], None if osm["status"] == "ok" else "unreadable", None))
    ru = ctx.get("rain_upstream")
    if ru and ru.get("upstream"):                          # B-88: the rain points upstream of this place
        out.append(("rain_upstream", SOURCE_NAME["rain_up"][lang].format(n=len(ru["upstream"])), None, None))
    rows = []
    for kind, name, reason, age in out:
        why_text = None
        if reason:
            why_text = LEFT_OUT[reason][lang].format(age=_age(age, lang)) if reason == "too_old" else LEFT_OUT[reason][lang]
        dropped = reason is not None and reason not in NOT_A_DROP       # looked at and left out (counted on the strip)
        rows.append({"kind": kind, "name": name, "used": reason is None, "left_out": dropped,
                     "note": W["used"][lang] if reason is None else
                     W["left_out" if dropped else "not_used"][lang].format(why=why_text)})
    return rows


def _level_bar(card, evidence):
    g = card.get("gauge")
    main = _main_gauge(evidence) or {}
    th = main.get("thresholds") or {}
    if not g or not th:
        return None
    return {"level_m": g["level_m"], "alert_m": th.get("alert_m"), "warning_m": th.get("warning_m"),
            "danger_m": th.get("danger_m")}


def share_text(view, lang):
    """Plain text for WhatsApp: verdict, what to do, the river line, the label, the disclaimer. Never the question
    or the trace."""
    v = view
    lines = [f"VEDA · {v['place'] or '-'}: {v['headline'][lang]}"]
    if v.get("label"):
        lines.append(v["label"][lang])
    lines.append(f"{card_mod.T['action'][lang].capitalize()}: {v['todo'][lang]}")
    lines.append(v["line"][lang])
    if v.get("water"):
        lines.append(v["water"][lang]["main"])
    lines += v.get("rain_share", {}).get(lang, [])                  # B-88: the rain lines behind the verdict
    lines.append(v["strip"][lang])
    lines.append(SAFETY[lang])
    return trace.redact("\n".join(lines))


def answer_view(result):
    """loop.run() result -> the public answer screen's data, both languages."""
    card = result.get("card") or {}
    forecast = result.get("forecast") or {}
    evidence = result.get("evidence") or {}
    answer = result.get("answer") or {}
    plan = result.get("plan") or {}
    if not card:
        return None
    verdict = card.get("verdict", "INSUFFICIENT_DATA")
    view = {"verdict": verdict, "place": card.get("place"), "headline": HEADLINE[verdict],
            "label": _both(lambda lang: _label(evidence, lang)) if _label(evidence, "en") else None,
            "line": _both(lambda lang: _line(card, forecast, lang)),
            "todo": dict(card["action"]),
            "water": _both(lambda lang: _water(card, forecast, evidence, lang)) if card.get("gauge") else None,
            "upstream": _both(lambda lang: _rain_text(card, lang, ("rain_up",)) + _upstream(forecast, lang)),
            "rain": _both(lambda lang: _rain(card, lang)) if _rain(card, "en") else None,
            "rain_more": _both(lambda lang: _rain_text(card, lang, ("rain_here", "until", "small_rivers", "thailand"))),
            "rain_share": _both(lambda lang: _rain_text(card, lang, ("rain_up", "rain_here", "until"))),
            "todo_more": _both(lambda lang: _rain_text(card, lang, ("tide",))),       # Cowork 24 Oct: tide advice
            "why": _both(lambda lang: why(forecast, lang)),
            "combined": _both(lambda lang: combined(forecast, lang)) if combined(forecast, "en") else None,
            "note": dict(W["calm_note"]) if verdict == "NORMAL" else None,
            "level_bar": _level_bar(card, evidence),
            "explanation": ({"text": trace.redact(answer["explanation"]), "language": answer.get("language")}
                            if answer.get("explanation") and answer.get("approved") else None),
            "sources": _both(lambda lang: sources(evidence, plan, lang)),
            "double_checked": bool(answer.get("approved")),
            "emergency": bool(card.get("emergency")),
            "synthetic": bool(card.get("synthetic"))}
    view["strip"] = _both(lambda lang: _strip(answer, view["sources"][lang], lang))
    view["share"] = _both(lambda lang: share_text(view, lang))
    return view


def hide_question(value, question, mark="(question not shown)"):
    """value with every string that holds the question - or a shortened copy of it (trace summaries are cut), or
    the place finder's 'normalized' copy - replaced by `mark`. Dicts and lists are walked."""
    q = (question or "").strip()

    def hide(v, key=None):
        if isinstance(v, dict):
            return {k: hide(x, k) for k, x in v.items()}
        if isinstance(v, list):
            return [hide(x) for x in v]
        if isinstance(v, str) and q:
            cut = v.rstrip(".… ")
            shortened = len(cut) >= 12 and cut in q and (v.endswith(("...", "…")) or len(cut) >= 0.6 * len(q))
            if key == "normalized" or q in v or shortened:          # not a place name that merely appears in it
                return mark
        return v
    return hide(value)


STEP_NAME = {  # the loop's states, for the "How VEDA worked this out" screen
    "plan": {"en": "Understand the question", "ms": "Memahami soalan"},
    "gather": {"en": "Gather the data", "ms": "Mengumpul data"},
    "forecast": {"en": "Work out the risk", "ms": "Menilai risiko"},
    "draft": {"en": "Write the answer", "ms": "Menulis jawapan"},
    "critique": {"en": "Double-check the answer", "ms": "Menyemak semula jawapan"},
    "revise": {"en": "Fix the answer", "ms": "Membetulkan jawapan"},
    "safety": {"en": "Safety check", "ms": "Semakan keselamatan"},
}
STEP_WHO = {"plan": "Coordinator", "gather": "Data & Reconciler", "forecast": "Forecast", "draft": "Coordinator",
            "critique": "Critic", "revise": "Coordinator", "safety": "System"}
STEP_SHOWN = {  # which trace lines each row repeats (outputs and decisions only - never an input, which can hold the question)
    "gazetteer.resolve": "output", "route": "both", "data.sources": "decision", "data.cross_check": "output",
    "data.reconcile": "output", "forecast.verdict": "both", "draft": "decision", "critic.code_checks": "both",
    "critic.requery": "both", "critic.review": "both", "critic.request": "output", "data.request": "output",
    "verdict.recomputed": "output", "ai.fallback": "output", "safety": "both",
}


def how_it_worked(trace_path):
    """One row per loop step from the run's trace: who did it, how long it took, what it found, which model answered
    (with Nightshift's receipt and seconds) and how many data queries went through Zetaris. Never the question."""
    try:
        recs = [json.loads(x) for x in open(trace_path, encoding="utf-8") if x.strip()]
    except (OSError, ValueError):
        return None
    recs = [r for r in recs if "action" in r]
    question = next((r.get("input_summary") for r in recs if r["action"] == "run_start"), None)
    timing = next(((r.get("details") or {}).get("timing") for r in recs if r["action"] == "timing"), None) or {}
    rows, cur = [], None
    for r in recs:
        a = r["action"]
        if a == "state":
            key = r.get("input_summary")
            cur = next((x for x in rows if x["key"] == key), None)
            if cur is None:
                cur = {"key": key, "name": STEP_NAME.get(key, {"en": key, "ms": key}), "who": STEP_WHO.get(key, ""),
                       "seconds": timing.get(key), "lines": [], "ai": [], "queries": 0}
                rows.append(cur)
            continue
        if a == "safety":
            cur = {"key": "safety", "name": STEP_NAME["safety"], "who": "System", "seconds": None, "lines": [], "ai": [],
                   "queries": 0}
            rows.append(cur)
        if cur is None:
            continue
        if a == "zetaris.run_sql":
            cur["queries"] += 1                    # a count only: the queries run in parallel
        elif a == "nightshift.chat":
            d = r.get("details") or {}
            cur["ai"].append({"agent": r.get("agent_name"), "model": d.get("served_model"), "receipt": d.get("receipt_id"),
                              "seconds": round((r.get("duration_ms") or 0) / 1000, 1), "status": r.get("status"),
                              "note": None if r.get("status") == "success" else r.get("output_summary")})
        elif a in STEP_SHOWN:
            show = STEP_SHOWN[a]
            parts = ([r.get("output_summary")] if show in ("output", "both") else []) + (
                [r.get("decision")] if show in ("decision", "both") else [])
            text = " - ".join(p for p in parts if p)
            if text:
                cur["lines"].append({"agent": r.get("agent_name"), "action": a, "status": r.get("status"), "text": text})
    out = {"rows": rows, "total_s": timing.get("total"),
           "fallbacks": next(((r.get("details") or {}).get("ai_fallbacks") for r in recs if r["action"] == "run_end"), [])}
    return json.loads(trace.redact(json.dumps(hide_question(out, question), ensure_ascii=False)))


def words():
    """Fixed wording for screens that call no engine: headlines, the emergency steps, the disclaimer."""
    steps = {lang: [s.strip().rstrip(".") + "." for s in re.split(r"(?<=\.)\s+", card_mod.ADVICE["ACT"][lang]) if s.strip()]
             for lang in LANGS}
    return {"headline": HEADLINE, "emergency": {"title": EMERGENCY["title"], "steps": steps},
            "safety": dict(SAFETY)}
