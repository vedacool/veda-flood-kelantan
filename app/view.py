"""The public answer screen as data (Cowork weekend plan B, 24 Oct): the run's card, forecast and evidence turned into
short plain pieces in English and Bahasa Melayu, for people, not engineers - no rule names, no agent names.

    view = answer_view(result)          # result = loop.run(...); returned by the API as result["view"]
    words()                             # fixed wording for screens that call no engine (emergency, headlines)

Read-only: nothing here changes a verdict, an action or the Coordinator's explanation; it only re-words what the
engine already decided. The user's question and the trace never go into a view (the share text is built from it).
"""
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
    "from_live": {"en": "from the official river gauge, {t}", "ms": "dari stesen sungai rasmi, {t}"},
    "from_reported": {"en": "from a reading reported in the news, {t}", "ms": "dari bacaan yang dilaporkan dalam berita, {t}"},
    "from_estimated": {"en": "from an estimate between reported readings, {t}",
                       "ms": "dari anggaran antara bacaan yang dilaporkan, {t}"},
    "from_made_up": {"en": "from made-up test readings, {t}", "ms": "dari bacaan ujian rekaan, {t}"},
    "from_none": {"en": "no fresh river reading", "ms": "tiada bacaan sungai terkini"},
    "label_replay": {"en": "Past flood replay · {when}", "ms": "Ulang tayang banjir lalu · {when}"},
    "label_synthetic": {"en": "Made-up test scene · {when}", "ms": "Senario ujian rekaan · {when}"},
    "used": {"en": "used", "ms": "digunakan"},
    "left_out": {"en": "left out: {why}", "ms": "diketepikan: {why}"},
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
SOURCE_NAME = {
    "open_meteo": {"en": "Rain forecast (Open-Meteo)", "ms": "Ramalan hujan (Open-Meteo)"},
    "open_meteo_past": {"en": "Rain record (Open-Meteo archive)", "ms": "Rekod hujan (arkib Open-Meteo)"},
    "mygov_forecast": {"en": "MetMalaysia forecast", "ms": "Ramalan MetMalaysia"},
    "mygov_warning": {"en": "MetMalaysia warnings", "ms": "Amaran MetMalaysia"},
    "cross": {"en": "Flood warnings (data.gov.my)", "ms": "Amaran banjir (data.gov.my)"},
    "osm": {"en": "Map data (OpenStreetMap)", "ms": "Data peta (OpenStreetMap)"},
    "river": {"en": "River level: {name}", "ms": "Paras sungai: {name}"},
    "upstream": {"en": "River upstream: {name}", "ms": "Sungai di hulu: {name}"},
}
LEFT_OUT = {
    "no_reading": {"en": "no reading", "ms": "tiada bacaan"},
    "looked_wrong": {"en": "the reading looked wrong", "ms": "bacaan kelihatan salah"},
    "too_old": {"en": "reading too old ({age})", "ms": "bacaan terlalu lama ({age})"},
    "past": {"en": "not kept for past dates", "ms": "tidak disimpan untuk tarikh lepas"},
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


def _line(card, forecast, lang):
    """The one line under the verdict badge."""
    if card["verdict"] == "INSUFFICIENT_DATA" or not card.get("gauge"):
        return W["no_reading_past" if card.get("replay") else "no_reading"][lang]
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
    parts = [W["water"][lang].format(m=_num(g["level_m"]), t=g["read_at"].split(" ")[-1])]
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
    return {"main": " · ".join(parts), "compare": "; ".join(compare)}


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
        else:
            out.append(tmpl[lang])
    if any(t["rule"] == "rising-fast" for t in triggers):
        out.append(WHY["rising-fast"][lang])
    return " ".join(dict.fromkeys(out))


def _source_kind(card):
    if card.get("synthetic"):
        return "made_up"
    label = card.get("reading_label") or ""
    if label.startswith("reconstructed"):
        return "estimated"
    if card.get("replay"):
        return "reported"
    return "live"


def _strip(card, answer, lang):
    g = card.get("gauge")
    tick = W["checked2" if answer.get("approved") else "checked1"][lang]
    if not g:
        return f"✓ {tick} · {W['from_none'][lang]}"
    t = g["read_at"].split(" ")[-1]
    kind = _source_kind(card)
    return f"✓ {tick} · " + W[{"live": "from_live", "reported": "from_reported", "estimated": "from_estimated",
                                "made_up": "from_made_up"}[kind]][lang].format(t=t)


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
            out.append((name, "no_reading", None))
        elif not (g.get("health") or {"ok": True})["ok"]:
            out.append((name, "looked_wrong", None))
        elif g.get("freshness") in ("stale", "unknown"):
            out.append((name, "too_old", g.get("age_minutes")))
        else:
            out.append((name, None, None))
    srcs = ev.get("sources") or {}
    past = bool(ev.get("replay"))
    for key in ("open_meteo", "mygov_forecast", "mygov_warning"):
        s = srcs.get(key) or {}
        name = SOURCE_NAME["open_meteo_past" if key == "open_meteo" and past else key][lang]
        status, note = s.get("status"), (s.get("note") or "")
        if status in ("ok", "stale", "degraded"):
            out.append((name, None, None))
        elif "replay" in note or "archive" in note:
            out.append((name, "past", None))
        elif status == "skipped":
            out.append((name, "not_needed", None))
        else:
            out.append((name, "unreadable", None))
    cross = ev.get("cross_check")
    if cross:
        reason = {"ok": None, "stale": "stale", "not_checked": "unreadable"}.get(cross.get("status"), "unreadable")
        out.append((SOURCE_NAME["cross"][lang], reason, None))
    elif (plan or {}).get("effort") == "quick":
        out.append((SOURCE_NAME["cross"][lang], "quick", None))
    osm = ev.get("osm")
    if osm:
        out.append((SOURCE_NAME["osm"][lang], None if osm["status"] == "ok" else "unreadable", None))
    rows = []
    for name, reason, age in out:
        why_text = None
        if reason:
            why_text = LEFT_OUT[reason][lang].format(age=_age(age, lang)) if reason == "too_old" else LEFT_OUT[reason][lang]
        rows.append({"name": name, "used": reason is None,
                     "note": W["used"][lang] if reason is None else W["left_out"][lang].format(why=why_text)})
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
    lines.append(v["strip"][lang].replace(" · Details ›", ""))
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
    ms = lambda lang, s: card_mod.months_ms(s) if lang == "ms" and s else s       # noqa: E731
    view = {"verdict": verdict, "place": card.get("place"), "headline": HEADLINE[verdict],
            "label": _both(lambda lang: _label(evidence, lang)) if _label(evidence, "en") else None,
            "line": _both(lambda lang: _line(card, forecast, lang)),
            "todo": dict(card["action"]),
            "water": _both(lambda lang: _water(card, forecast, evidence, lang)) if card.get("gauge") else None,
            "upstream": _both(lambda lang: _upstream(forecast, lang)),
            "rain": _both(lambda lang: _rain(card, lang)) if _rain(card, "en") else None,
            "strip": _both(lambda lang: ms(lang, _strip(card, answer, lang))),
            "why": _both(lambda lang: why(forecast, lang)),
            "level_bar": _level_bar(card, evidence),
            "explanation": ({"text": trace.redact(answer["explanation"]), "language": answer.get("language")}
                            if answer.get("explanation") and answer.get("approved") else None),
            "sources": _both(lambda lang: sources(evidence, plan, lang)),
            "double_checked": bool(answer.get("approved")),
            "emergency": bool(card.get("emergency")),
            "synthetic": bool(card.get("synthetic"))}
    view["share"] = _both(lambda lang: share_text(view, lang))
    return view


def words():
    """Fixed wording for screens that call no engine: headlines, the emergency steps, the disclaimer."""
    steps = {lang: [s.strip().rstrip(".") + "." for s in re.split(r"(?<=\.)\s+", card_mod.ADVICE["ACT"][lang]) if s.strip()]
             for lang in LANGS}
    return {"headline": HEADLINE, "emergency": {"title": EMERGENCY["title"], "steps": steps},
            "safety": dict(SAFETY)}
