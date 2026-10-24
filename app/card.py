"""Answer card (B-21): one forwardable answer per place, in BM and EN, assembled by CODE.

    card = card.build(plan, evidence, forecast)
    text = card.render(card, "ms", explanation=None)     # WhatsApp/SMS-length plain text

Order (user first): what to do now -> verdict + JPS level name -> plain comparison (thresholds, past peaks) ->
range + confidence -> [explanation written by Nemotron, full path only] -> upstream / warnings -> sources with age,
excluded stale sources, unresolved conflicts. The disclaimer + 999 / 991 is the answer's safety line.
Everything except the explanation is inserted verbatim by code (Husaini 22 Oct night); the explanation may only use
numbers that are in the card (`explanation_problem`). Advice texts are TENTATIVE (review pack section G).
"""
import json
import re
from datetime import datetime

from app.config import MYT, REPLAYS, synthetic

ADVICE = {  # Husaini 22 Oct night, tentative - Dr Ariff to check (docs/review_pack_ariff.md section G)
    "NORMAL": {"en": "No action needed. Keep an eye on JPS updates.",
               "ms": "Tiada tindakan diperlukan. Terus pantau maklumat terkini JPS."},
    "WATCH": {"en": "Check again in 3 hours. Get important documents, medicines and a charged phone / power bank "
                    "ready.",
              "ms": "Semak semula dalam 3 jam. Sediakan dokumen penting, ubat-ubatan dan telefon yang dicas / "
                    "power bank."},
    "PREPARE": {"en": "Pack an emergency bag. Move valuables and your vehicle to higher ground. Find your nearest PPS "
                      "(ask the village head / JKKK). Check on elderly or sick neighbours.",
                "ms": "Sediakan beg kecemasan. Alihkan barang berharga dan kenderaan ke tempat tinggi. Kenal pasti "
                      "PPS terdekat (tanya ketua kampung / JKKK). Bantu jiran warga emas atau yang sakit."},
    "ACT": {"en": "Follow APM / police instructions and go to the PPS if told. Switch off the main power. Never walk "
                  "or drive through floodwater. If trapped: stay on high ground, save phone battery, call 999 / 991.",
            "ms": "Ikut arahan APM / polis dan pergi ke PPS jika diarahkan. Matikan suis utama elektrik. Jangan "
                  "meredah air banjir, sama ada berjalan kaki atau memandu. Jika terkandas: kekal di tempat tinggi, "
                  "jimatkan bateri telefon, hubungi 999 / 991."},
    "INSUFFICIENT_DATA": {"en": "VEDA cannot confirm the river level right now. Check JPS Infobanjir; call 999 if "
                                "you are in danger.",
                          "ms": "VEDA tidak dapat mengesahkan paras sungai sekarang. Semak JPS Infobanjir; hubungi "
                                "999 jika anda dalam bahaya."},
}
T = {  # fixed wording, BM + EN
    "action": {"en": "WHAT TO DO NOW", "ms": "APA PERLU DIBUAT SEKARANG"},
    "level": {"en": "JPS level", "ms": "paras JPS"},
    "river": {"en": "River", "ms": "Sungai"},
    "at": {"en": "at", "ms": "pada"},
    "above": {"en": "above", "ms": "di atas"},
    "below": {"en": "below", "ms": "di bawah"},
    "alert": {"en": "Alert", "ms": "Waspada"},
    "danger": {"en": "Danger", "ms": "Bahaya"},
    "peak": {"en": "the {event} peak", "ms": "puncak {event}"},
    "next24": {"en": "Next 24 h", "ms": "24 jam akan datang"},
    "rain": {"en": "Rain next 24 h: {mm} mm (Open-Meteo)", "ms": "Hujan 24 jam akan datang: {mm} mm (Open-Meteo)"},
    "rain_past": {"en": "Rain past 24 h: {mm} mm (Open-Meteo archive, {date}); a past day has no rain forecast",
                  "ms": "Hujan 24 jam lepas: {mm} mm (arkib Open-Meteo, {date}); tiada ramalan hujan dalam ulang tayang"},
    "synthetic_tag": {"en": " (made-up test data · SYNTHETIC)", "ms": " (data ujian rekaan · SYNTHETIC)"},
    "synthetic_src": {"en": "made-up test river levels (SYNTHETIC, not JPS)",
                      "ms": "paras sungai ujian rekaan (SYNTHETIC, bukan JPS)"},
    "vs2014": {"en": "Compared with 2014: {d} m {rel} the Dec 2014 peak here ({p} m)",
               "ms": "Berbanding 2014: {d} m {rel} puncak Dis 2014 di sini ({p} m)"},
    "archive": {"en": "Open-Meteo archive (real rain up to the replay time)",
                "ms": "arkib Open-Meteo (hujan sebenar sehingga masa ulang tayang)"},
    "archive_short": {"en": "Open-Meteo archive", "ms": "arkib Open-Meteo"},
    "trend": {"en": "if it keeps changing at this rate", "ms": "jika terus berubah pada kadar ini"},
    "falling": {"en": "falling", "ms": "sedang turun"},
    "pass_danger": {"en": "expected to pass Danger", "ms": "dijangka melepasi paras Bahaya"},
    # trapped / stranded (Husaini 23 Oct; tentative, review pack G5)
    "stranded": {"en": "If you are stranded: safety first", "ms": "Jika anda terkandas: utamakan keselamatan dahulu"},
    "stranded_normal": {"en": "River level is normal, but local flooding can still trap you",
                        "ms": "Paras sungai normal, tetapi banjir setempat masih boleh memerangkap anda"},
    # above Danger (Husaini 23 Oct): no number range, only the direction (+ 2014 when higher)
    "above_trend": {"rising": {"en": "still rising", "ms": "masih naik"}, "falling": {"en": "falling", "ms": "turun"},
                    "steady": {"en": "steady", "ms": "stabil"}},
    "higher_2014": {"en": "higher than 2014", "ms": "melebihi paras 2014"},
    "tidal": {"en": "the sea tide moves this river, so no trend is shown",
              "ms": "pasang surut laut menggerakkan sungai ini, jadi trend tidak ditunjukkan"},
    "confidence": {"en": "Confidence", "ms": "Keyakinan"},
    "conf_label": {"high": {"en": "high", "ms": "tinggi"}, "medium": {"en": "medium", "ms": "sederhana"},
                   "low": {"en": "low", "ms": "rendah"}},
    "upstream": {"en": "Upstream", "ms": "Hulu"},
    # B-88 (tentative wording + numbers, review pack L)
    "rain_up": {"en": "Heavy rain upstream: {items}", "ms": "Hujan lebat di hulu: {items}"},
    "rain_up_item": {"en": "{name} {mm72} mm in 3 days ({mm24} mm in 24 h)",
                     "ms": "{name} {mm72} mm dalam 3 hari ({mm24} mm dalam 24 jam)"},
    "rain_up_fc_item": {"en": "{name} {mm} mm forecast in 24 h", "ms": "{name} {mm} mm dijangka dalam 24 jam"},
    "arrival_unknown": {"en": "arrival time not known", "ms": "masa sampai tidak diketahui"},
    "rain_here": {"en": "Heavy rain here: {mm} mm in 12 h", "ms": "Hujan lebat di sini: {mm} mm dalam 12 jam"},
    "small_rivers": {"en": "Small rivers and drains can rise fast in heavy rain - keep away from them",
                     "ms": "Sungai kecil dan longkang boleh naik dengan cepat ketika hujan lebat - sila jauhi kawasan itu"},
    "thailand": {"en": "Rain upstream in Thailand is not checked yet", "ms": "Hujan di hulu di Thailand belum disemak"},
    "thai_rain": {"en": "Rain upstream in Thailand: {items} (arrival time not known)",
                  "ms": "Hujan di hulu di Thailand: {items} (masa sampai tidak diketahui)"},
    "thai_item": {"en": "{name} {mm} mm in 3 days", "ms": "{name} {mm} mm dalam 3 hari"},
    "tide": {"en": "High tide can keep water in town longer", "ms": "Air pasang boleh menyebabkan air banjir lambat surut di bandar"},
    "thunder": {"en": "Thunderstorm warning: small streams and drains can rise within an hour or two",
                "ms": "Amaran ribut petir: anak sungai dan longkang boleh naik dalam masa satu atau dua jam"},
    "until": {"en": "Rain likely until about {t}, then easing", "ms": "Hujan dijangka hingga kira-kira {t}, kemudian reda"},
    "until_heavy": {"en": "Heavy rain likely until about {t}, then easing",
                    "ms": "Hujan lebat dijangka hingga kira-kira {t}, kemudian reda"},
    # audit 24 Oct P3: the rain lasts to the end of the forecast data -> no "then easing"
    "until_open": {"en": "Rain likely until at least {t}", "ms": "Hujan dijangka sekurang-kurangnya hingga {t}"},
    "until_heavy_open": {"en": "Heavy rain likely until at least {t}",
                         "ms": "Hujan lebat dijangka sekurang-kurangnya hingga {t}"},
    "may_reach": {"en": "may reach here in {a}-{b} h", "ms": "mungkin sampai ke sini dalam {a}-{b} jam"},
    "rising": {"en": "rising", "ms": "sedang naik"},
    "warning": {"en": "MetMalaysia warning", "ms": "Amaran MetMalaysia"},
    "sources": {"en": "Sources", "ms": "Sumber"},
    "min_ago": {"en": "{n} min ago", "ms": "{n} minit lalu"},
    "h_ago": {"en": "{n} h ago", "ms": "{n} jam lalu"},
    "age_unknown": {"en": "update time unknown", "ms": "masa kemas kini tidak diketahui"},
    "met_today": {"en": "MetMalaysia forecast for today", "ms": "ramalan MetMalaysia hari ini"},
    "excluded": {"en": "Left out: data.gov.my flood warnings (out of date, last update {when})",
                 "ms": "Diketepikan: amaran banjir data.gov.my (sudah lama tidak dikemas kini, kali terakhir {when})"},
    "not_checked": {"en": "Not checked: data.gov.my flood warnings (could not be read)",
                    "ms": "Tidak disemak: amaran banjir data.gov.my (tidak dapat dibaca)"},
    # Husaini 23 Oct: a MetMalaysia source that data.gov.my would not serve (e.g. HTTP 429) is named, never hidden
    "met_not_checked": {"en": "Not checked: MetMalaysia {what} (data.gov.my could not be read)",
                        "ms": "Tidak disemak: {what} MetMalaysia (data.gov.my tidak dapat dibaca)"},
    "met_what": {("mygov_warning",): {"en": "warnings", "ms": "amaran"},
                 ("mygov_forecast",): {"en": "forecast", "ms": "ramalan"},
                 ("mygov_forecast", "mygov_warning"): {"en": "warnings and forecast", "ms": "amaran dan ramalan"}},
    "excluded_short": {"en": "Left out: old data.gov.my flood warnings",   # the Critic still needs to see it; short
                       "ms": "Diketepikan: amaran banjir lama data.gov.my"},   # so a long BM card still fits
    "conflict": {"en": "Sources disagree on {q}; VEDA did not pick one", "ms": "Sumber tidak sepakat tentang {q}; VEDA tidak memilih"},
    "no_reading": {"en": "no fresh reading from this place's main river gauge",
                   "ms": "tiada bacaan terkini dari stesen sungai utama tempat ini"},
    "backup": {"en": "Note: {primary} {silent} - using the backup gauge {backup}",
               "ms": "Nota: {primary} {silent} - menggunakan stesen ganti {backup}"},
    "silent": {"en": "has no reading since {t}", "ms": "tiada bacaan sejak {t}"},
    "silent_never": {"en": "has no reading", "ms": "tiada bacaan"},
    "last": {"en": "Last reading: {m} m at {t} ({age}) - too old to use", "ms": "Bacaan terakhir: {m} m pada {t} ({age}) - terlalu lama untuk digunakan"},
    # replay (Husaini 23 Oct): the gap is in what was reported, not a gauge that went down
    "replay_gap": {"en": "This replay has no verified JPS reading near this time",
                   "ms": "Ulang tayang ini tiada bacaan JPS yang disahkan berhampiran masa ini"},
    "synthetic_gap": {"en": "This SYNTHETIC scene has no reading near this time",
                      "ms": "Senario SYNTHETIC ini tiada bacaan berhampiran masa ini"},
    "synthetic_last": {"en": "Last SYNTHETIC reading: {m} m at {t} ({age}) - too far from this time to use",
                       "ms": "Bacaan SYNTHETIC terakhir: {m} m pada {t} ({age}) - terlalu jauh dari masa ini untuk digunakan"},
    "replay_last": {"en": "Last verified reading: {m} m at {t} ({age}) - too far from this time to use",
                    "ms": "Bacaan disahkan terakhir: {m} m pada {t} ({age}) - terlalu jauh dari masa ini untuk digunakan"},
    # B-71(c): a discovered gauge a person approved for this place - context only, never in the verdict
    "discovered": {"en": "Gauge found by VEDA: {name} (approved by {by}; for information only - it does not change "
                         "the result): {level}",
                   "ms": "Stesen yang ditemui VEDA: {name} (diluluskan oleh {by}; untuk makluman sahaja - tidak "
                         "mengubah keputusan): {level}"},
    # B-71(b): the Critic asked for another upstream source and the Data & Reconciler found none
    "missing": {"en": "Missing: no fresh reading from {gauges}; VEDA looked for another upstream gauge on the same "
                      "river and found none",
                "ms": "Tiada bacaan terkini dari {gauges}; VEDA mencari stesen hulu lain di sungai yang sama, tiada "
                      "ditemui"},
    # B-73 (Husaini 23 Oct): OpenStreetMap lines - possible PPS are never official or open; bridges are facts only
    "pps": {"en": "Possible evacuation centres (PPS) — not an official list, confirm with APM / the village head: "
                  "{items}",
            "ms": "Kemungkinan pusat pemindahan (PPS) — bukan senarai rasmi, sahkan dengan APM / ketua kampung: {items}"},
    "pps_none": {"en": "Possible evacuation centres (PPS): none named in OpenStreetMap within 10 km — ask APM / the "
                       "village head",
                 "ms": "Kemungkinan pusat pemindahan (PPS): tiada yang bernama dalam OpenStreetMap dalam 10 km — tanya "
                       "APM / ketua kampung"},
    "bridge": {"en": "{name} crosses {river} ({km} km); river level there: {level}",
               "ms": "{name} merentasi {river} ({km} km); paras sungai di situ: {level}"},
    "bridge_on": {"en": "Bridge on {road}", "ms": "Jambatan di {road}"},
    "bridge_none": {"en": "Bridges: none over a named river in OpenStreetMap within 10 km",
                    "ms": "Jambatan: tiada yang merentasi sungai bernama dalam OpenStreetMap dalam 10 km"},
    "no_level": {"en": "no recent reading", "ms": "tiada bacaan terkini"},
    "no_gauge": {"en": "no JPS gauge nearby on this river", "ms": "tiada stesen JPS berdekatan di sungai ini"},
    "low_ground": {"en": "VEDA does not know yet which areas are low-lying",
                   "ms": "VEDA belum mengetahui kawasan mana yang rendah"},
    "osm_failed": {"en": "Not checked: OpenStreetMap (could not be read)",
                   "ms": "Tidak disemak: OpenStreetMap (tidak dapat dibaca)"},
    "osm_src": {"en": "© OpenStreetMap contributors (ODbL)", "ms": "© OpenStreetMap contributors (ODbL)"},
    "low_conf": {"en": "Low confidence: VEDA's reviewer did not approve the written explanation, so only the checked "
                       "data is shown.",
                 "ms": "Keyakinan rendah: penyemak VEDA tidak meluluskan penjelasan bertulis, jadi hanya data yang "
                       "telah disemak dipaparkan."},
}
BAND = {"below_normal": {"en": "Normal", "ms": "Normal"}, "normal": {"en": "Normal", "ms": "Normal"},   # JPS names only
        "alert": {"en": "Alert", "ms": "Waspada"}, "warning": {"en": "Warning", "ms": "Amaran"},
        "danger": {"en": "Danger", "ms": "Bahaya"}}
# The verdict as the user reads it (Husaini 23 Oct; tentative, review pack G). Not Waspada / Amaran / Bahaya: those
# are JPS's own level names, which the card shows next to the verdict.
VERDICT_LABEL = {"NORMAL": {"en": "NORMAL", "ms": "NORMAL"}, "WATCH": {"en": "WATCH", "ms": "BERJAGA-JAGA"},
                 "PREPARE": {"en": "PREPARE", "ms": "BERSEDIA"}, "ACT": {"en": "ACT", "ms": "BERTINDAK"},
                 "INSUFFICIENT_DATA": {"en": "Can't confirm right now", "ms": "Tidak dapat disahkan sekarang"}}  # = page headline
_CODE_OF = {label: code for code, labels in VERDICT_LABEL.items() for label in labels.values()}
_CODE_OF["INSUFFICIENT_DATA"] = "INSUFFICIENT_DATA"
# Verdict words in capitals, EN or BM (case-sensitive: "Normal" the JPS level and "bersedia" the verb don't count).
VERDICT_WORDS = re.compile(r"\b(BERJAGA-JAGA|DATA TIDAK MENCUKUPI|BERSEDIA|BERTINDAK|NORMAL|WATCH|PREPARE|ACT|"
                           r"INSUFFICIENT[ _]DATA)\b")
MONTHS_MS = {"Jan": "Jan", "Feb": "Feb", "Mar": "Mac", "Apr": "Apr", "May": "Mei", "Jun": "Jun", "Jul": "Jul",
             "Aug": "Ogo", "Sep": "Sep", "Oct": "Okt", "Nov": "Nov", "Dec": "Dis"}
_DATE_EN = re.compile(r"\b(\d{1,2} )?(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b(?= \d)")


def verdict_codes(text):
    """The verdict codes a text names, from EN or BM verdict words."""
    return {_CODE_OF.get(w, w) for w in VERDICT_WORDS.findall(text or "")}


def months_ms(text):
    """'27 Nov 19:30', 'Dec 2023' -> BM month names ('Dis 2023'); only month abbreviations followed by a number."""
    return _DATE_EN.sub(lambda m: (m.group(1) or "") + MONTHS_MS[m.group(2)], text)
MAX_EXPLANATION = 200
MAX_CARD_CHARS = 750          # Husaini 23 Oct: ~750 characters (2014 line kept), disclaimer + AI explanation extra
PPS_SHOWN, BRIDGES_SHOWN = 3, 2     # B-73: OSM lines on the card, outside the cap (Husaini 23 Oct)


def _day(iso):
    """'2024-11-25T18:00:00+08:00' -> '25 Nov 2024' (the archive rain's date; BM months applied at render)."""
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(MYT).strftime("%d %b %Y").lstrip("0")
    except ValueError:
        return None


def _hhmm(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(MYT).strftime("%d %b %H:%M")
    except ValueError:
        return None


def _num(v):
    return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def build(plan, evidence, forecast):
    """The card as data (both languages derive from it). Never raises for missing pieces - they are left out."""
    ctx = (evidence or {}).get("context") or {}
    fc = forecast or {}
    main = next((g for g in ctx.get("gauges", []) if g["role"] == "controlling"), None)
    trend = next((c for c in fc.get("controlling", []) if c["role"] == "controlling"), {})
    verdict = fc.get("verdict", "INSUFFICIENT_DATA")
    card = {"place": ((evidence or {}).get("place") or {}).get("name") or (plan.get("place") or {}).get("name"),
            "verdict": verdict, "level_name": fc.get("level_name"), "action": ADVICE[verdict],
            "confidence": (fc.get("confidence") or {}).get("label", "low"), "gauge": None, "comparison": {},
            "thresholds": {}, "rain_24h_mm": None,
            "range_24h": None, "tidal": bool(trend.get("tide_influenced")), "falling": bool(trend.get("falling")),
            "trend": _trend_word(trend),
            "peak": None, "upstream": [],
            "warnings": [w["heading"] for w in ((evidence or {}).get("met_warnings") or {}).get("active", [])],
            "sources": [], "excluded": None, "conflicts": [], "vs_2014": None, "rain_past_24h_mm": None,
            "replay": (REPLAYS.get(((evidence or {}).get("replay") or {}).get("scenario")) or {}).get("title"),
            "reading_label": None, "backup": None, "last_reading": None}
    if main and main["level_m"] is not None and verdict != "INSUFFICIENT_DATA" and not fc.get("no_river"):
        th = main["thresholds"]
        card["gauge"] = {"name": main["name"], "level_m": main["level_m"], "read_at": _hhmm(main["observed_at"])}
        card["reading_label"] = ((main.get("provenance") or {}).get("replay") or {}).get("label")
        for key in ("alert", "danger"):
            if th.get(f"{key}_m") is not None:
                card["comparison"][key] = round(main["level_m"] - th[f"{key}_m"], 2)
                card["thresholds"][key] = th[f"{key}_m"]
        rng = (trend.get("projection_m") or {}).get("24h")
        card["above_danger"] = th.get("danger_m") is not None and main["level_m"] >= th["danger_m"]
        card["range_24h"] = None if card["above_danger"] else rng      # Husaini 23 Oct: no number above Danger
        # Husaini 23 Oct: a number range only while the projection stays below Danger; reaching it -> words only
        # (a straight line projected past Danger is not a level anyone can stand behind - review pack A5)
        card["pass_danger"] = bool(rng and not card["above_danger"] and th.get("danger_m") is not None
                                   and rng["max"] >= th["danger_m"])
        if card["pass_danger"]:
            card["range_24h"] = None
        hist = fc.get("history") or []
        if hist:
            top = max(hist, key=lambda h: h["peak_m"])
            card["peak"] = {"event": top["event"], "peak_m": top["peak_m"],
                            "diff_m": round(main["level_m"] - top["peak_m"], 2)}
        y2014 = next((h for h in hist if h["event"] == "Dec 2014"), None)
        if y2014 and y2014 is not top:            # the explicit "bigger than 2014?" line (B-70)
            card["vs_2014"] = {"peak_m": y2014["peak_m"], "diff_m": round(main["level_m"] - y2014["peak_m"], 2)}
    for u in fc.get("upstream", []):
        if u.get("band") in ("alert", "warning", "danger") or u.get("rising"):
            card["upstream"].append({"gauge": u["gauge"], "band": u.get("band"), "rising": u.get("rising"),
                                     "arrives_in_h": u.get("arrives_in_h")})
    if main and main.get("backup_for"):              # B-15: say plainly that a backup gauge stands in
        silent = (ctx.get("silent") or [{}])[0]
        card["backup"] = {"primary": main["backup_for"], "backup": main["name"],
                          "since": _hhmm(silent["observed_at"]) if silent.get("observed_at") else None}
    last = ctx.get("last_reading")
    if last and (verdict == "INSUFFICIENT_DATA" or (fc.get("no_river") and not card["gauge"])):
        card["last_reading"] = {"level_m": last["level_m"], "at": _hhmm(last["observed_at"]),
                                "age_minutes": last["age_minutes"]}
    scene = ((evidence or {}).get("replay") or {})
    card["synthetic"] = synthetic(scene.get("scenario"))
    if main and main["age_minutes"] is not None:
        card["sources"].append(("synthetic", None) if card["synthetic"] else ("jps", main["age_minutes"]))
    rain = ctx.get("rain")
    if rain and card["replay"]:
        card["sources"].append(("archive", None))
        card["rain_past_24h_mm"] = rain.get("rain_past_24h_mm")
        card["rain_date"] = _day(scene.get("at"))
    elif rain:
        card["sources"].append(("open_meteo", rain.get("age_minutes")))
        card["rain_24h_mm"] = rain.get("rain_next_24h_mm")
    if ctx.get("met_forecast"):
        card["sources"].append(("met_forecast", None))
    cross = (evidence or {}).get("cross_check") or {}
    if cross.get("status") == "stale":
        card["excluded"] = (cross.get("newest") or "").split(" ")[0] or "?"
    card["not_checked"] = cross.get("status") == "not_checked"
    card["met_not_checked"] = tuple(sorted(k for k, s in ((evidence or {}).get("sources") or {}).items()
                                           if k in ("mygov_forecast", "mygov_warning") and s.get("status") == "not_checked"))
    card["conflicts"] = [c["quantity"] for c in (evidence or {}).get("conflicts_unresolved", [])]
    card["discovered"] = list((evidence or {}).get("discovered_context") or [])   # B-71(c): context only
    osm, intent = (evidence or {}).get("osm"), plan.get("intent")
    card["osm"] = None
    if osm:                                            # B-73: only for evacuation / cut-off questions (data agent)
        card["osm"] = {"status": osm["status"],
                       "pps": osm["pps"][:PPS_SHOWN] if intent == "evacuation" else None,
                       "bridges": osm["bridges"][:BRIDGES_SHOWN] if intent == "cut_off" else None}
        if osm["status"] == "ok":
            card["sources"].append(("osm", None))
    card["rain_up"] = rain_up(fc.get("rain_upstream"))
    # Cowork 24 Oct: a tide-influenced town (Kota Bharu, Tumpat) at Keep watching or higher - advice only, no verdict change
    card["tide_advice"] = card["tidal"] and verdict in ("WATCH", "PREPARE", "ACT")
    card["thunder_advice"] = bool(fc.get("thunderstorm"))      # Cowork 24 Oct: at any verdict, no verdict change
    # Cowork 24 Oct: Get ready from a Buruk / Bahaya warning with no river reading - the card still says what is missing
    card["no_river"] = fc.get("no_river") if verdict != "INSUFFICIENT_DATA" and not card["gauge"] else None
    rules = [t.get("rule") or "" for t in fc.get("triggers", [])]     # lines behind the verdict are never trimmed
    card["keep"] = sorted({"upstream" for r in rules if r.startswith("sentinel")}
                          | {"rain" for r in rules if r.startswith("rain")})
    return card


WORDS = {  # key facts as words (Husaini 23 Oct): JPS level names, no minus signs, no rule names
    "level_vs": {"en": "{d} m {side} the {name} level ({t} m)", "ms": "{d} m {side} paras {name} ({t} m)"},
    "trend": {"rising": {"en": "rising", "ms": "naik"}, "falling": {"en": "falling", "ms": "turun"},
              "steady": {"en": "steady", "ms": "stabil"}},
    "vs2014": {"en": "{d} m {side} the Dec 2014 peak ({p} m)", "ms": "{d} m {side} puncak Dis 2014 ({p} m)"},
    "excluded": {"en": "data.gov.my flood warnings (out of date, left out)",
                 "ms": "amaran banjir data.gov.my (sudah lama tidak dikemas kini, diketepikan)"},
    "no_verified": {"en": "no verified reading near this time", "ms": "tiada bacaan yang disahkan berhampiran masa ini"},
    "last": {"en": "{m} m at {t}, too old to use", "ms": "{m} m pada {t}, terlalu lama untuk digunakan"},
}


DAYS_MS = {"Mon": "Isnin", "Tue": "Selasa", "Wed": "Rabu", "Thu": "Khamis", "Fri": "Jumaat", "Sat": "Sabtu",
           "Sun": "Ahad"}


def gauge_place(name):
    """'Sg. Kelantan di Kuala Krai (F1)' -> 'Kuala Krai' (the place people know)."""
    name = re.sub(r"\s*\(F\d\)$", "", name or "")
    return name.split(" di ", 1)[1] if " di " in name else name


def rain_up(ru):
    """B-88: the card's rain picture - heavy rain upstream (and when it may arrive), heavy rain here, until when."""
    if not ru:
        return None
    heavy = [u for u in ru.get("upstream", []) if u["point"] in ru.get("heavy_upstream", [])]
    local = ru.get("local") or {}
    return {"heavy": [{"name": gauge_place(u["name"]), "past_72h_mm": u["past_72h_mm"], "past_24h_mm": u["past_24h_mm"],
                       "next_24h_mm": u.get("next_24h_mm"), "fallen": u["heavy_fallen"], "window": u["window"]}
                      for u in sorted(heavy, key=lambda u: -(u["past_72h_mm"] or 0))[:2]],
            "local_12h_mm": local.get("max_12h_mm"), "local_heavy": bool(local.get("heavy")),
            "until": local.get("until"), "until_heavy": bool(local.get("until_heavy")),
            "until_ends": local.get("until_ends", True),
            "golok": bool(ru.get("golok")), "combined": bool(ru.get("combined")),
            # Cowork 24 Oct: the Thai-side Golok points' rain when it is not heavy (heavy rain is in "heavy" above)
            "thai": [{"name": gauge_place(u["name"]), "past_72h_mm": u["past_72h_mm"]} for u in ru.get("upstream", [])
                     if u["point"] in ru.get("thai_points", []) and u["point"] not in ru.get("heavy_upstream", [])]}


def when_text(iso, lang):
    """'2024-11-27T14:00:00+08:00' -> 'Wed 27 Nov, 14:00' / 'Rabu 27 Nov, 14:00' (BM month added at render)."""
    try:
        t = datetime.fromisoformat(str(iso)).astimezone(MYT)
    except ValueError:
        return None
    day = t.strftime("%a")
    return f"{DAYS_MS[day] if lang == 'ms' else day} {t.strftime('%d %b, %H:%M').lstrip('0')}"


def rain_lines(card, lang):
    """B-88 lines (outside the length cap, like the OSM lines: the line behind a raised verdict is never cut)."""
    out = [("tide", T["tide"][lang] + ".")] if card.get("tide_advice") else []
    if card.get("thunder_advice"):
        out.append(("thunder", T["thunder"][lang] + "."))
    r = card.get("rain_up")
    if not r:
        return out
    if r["heavy"]:
        items = []
        for u in r["heavy"]:
            item = (T["rain_up_item"][lang].format(name=u["name"], mm72=_num(u["past_72h_mm"]), mm24=_num(u["past_24h_mm"]))
                    if u["fallen"] else T["rain_up_fc_item"][lang].format(name=u["name"], mm=_num(u["next_24h_mm"])))
            w = u["window"]
            items.append(item + ", " + (T["may_reach"][lang].format(a=_num(w["min"]), b=_num(w["max"])) if w
                                        else T["arrival_unknown"][lang]))
        out.append(("rain_up", T["rain_up"][lang].format(items="; ".join(items)) + "."))
    if r["local_heavy"]:
        out.append(("rain_here", T["rain_here"][lang].format(mm=_num(r["local_12h_mm"])) + "."))
        out.append(("small_rivers", T["small_rivers"][lang] + "."))
    if r["until"]:
        key = ("until_heavy" if r["until_heavy"] else "until") + ("" if r.get("until_ends", True) else "_open")
        out.append(("until", T[key][lang].format(t=when_text(r["until"], lang)) + "."))
    if r["golok"]:
        out.append(("thailand", T["thailand"][lang] + "."))
    elif r.get("thai"):
        out.append(("thailand", T["thai_rain"][lang].format(items="; ".join(
            T["thai_item"][lang].format(name=u["name"], mm=_num(u["past_72h_mm"])) for u in r["thai"])) + "."))
    return out


STEADY_M_PER_H = 0.005     # under 0.5 cm an hour (the mean of the 1 h and 3 h rates) = steady - card AND screen


def _trend_word(trend):
    """'rising' / 'falling' / 'steady' from the controlling gauge's rates, None when unknown or tide-influenced.
    The same rule as the answer screen (view._trend): 24 Oct evening live test, Rantau Panjang -2 cm in 1 h and +4 cm
    in 3 h - the card said 'turun' while the screen said steady, and the AI repeated 'turun'."""
    rate = trend.get("rate_m_per_h") or {}
    if not rate or trend.get("tide_influenced"):
        return None
    mid = (rate.get("min", 0) + rate.get("max", 0)) / 2
    return "steady" if abs(mid) < STEADY_M_PER_H else "rising" if mid > 0 else "falling"


def key_facts(card, forecast=None, lang="en"):
    """The card's key facts in the answer's language, as words (Husaini 23 Oct): what the Critic's AI review and
    the draft call get instead of the whole card / evidence. Only facts the card shows; no signed numbers."""
    lang = lang if lang in ("en", "ms") else "en"
    g = card.get("gauge") or {}
    side = lambda d: T["above" if d >= 0 else "below"][lang]          # noqa: E731
    f = {"place": card.get("place"), "verdict": VERDICT_LABEL[card["verdict"]][lang],
         "jps_level": (card.get("level_name") or {}).get(lang),
         "river": f"{_num(g['level_m'])} m {T['at'][lang]} {g['read_at']}" if g else None,
         "confidence": T["conf_label"].get(card.get("confidence"), T["conf_label"]["low"])[lang]}
    for key in ("alert", "danger"):
        d = card["comparison"].get(key)
        if d is not None:
            f[f"vs_{key}"] = WORDS["level_vs"][lang].format(d=_num(abs(d)), side=side(d), name=T[key][lang],
                                                           t=_num(card["thresholds"][key]))
    if card.get("trend"):
        f["trend"] = WORDS["trend"][card["trend"]][lang]
    if card.get("range_24h"):
        r = card["range_24h"]
        f["next_24h"] = f"{_num(r['min'])}-{_num(r['max'])} m ({T['trend'][lang]})"
    elif card.get("pass_danger"):
        f["next_24h"] = T["pass_danger"][lang]
    if card.get("vs_2014"):
        v = card["vs_2014"]
        f["vs_2014"] = WORDS["vs2014"][lang].format(d=_num(abs(v["diff_m"])), side=side(v["diff_m"]),
                                                    p=_num(v["peak_m"]))
    ups = []
    for u in card.get("upstream", []):
        bits = ([BAND.get(u["band"], {}).get(lang, u["band"])] if u.get("band") else []) + (
            [T["rising"][lang]] if u.get("rising") else [])
        ups.append(f"{u['gauge']} ({', '.join(bits)})")
    f["upstream"] = ups
    rain = [t.rstrip(".") for _, t in rain_lines(card, lang)]          # B-88: rain upstream / here / until
    if rain:
        f["rain_upstream_and_here"] = rain
    if card.get("warnings"):
        f["met_warnings"] = card["warnings"]
    if card.get("excluded"):
        f["excluded"] = [WORDS["excluded"][lang]]
    if card.get("conflicts"):
        f["conflicts"] = card["conflicts"]
    if card["verdict"] == "INSUFFICIENT_DATA":
        f["note"] = WORDS["no_verified"][lang] if card.get("replay") else T["no_reading"][lang]
        lr = card.get("last_reading")
        if lr:
            f["last_reading"] = WORDS["last"][lang].format(m=_num(lr["level_m"]), t=lr["at"])
    osm = card.get("osm") or {}
    if osm.get("status") == "ok" and osm.get("pps"):
        f["possible_pps"] = {"note": T["pps"][lang].split(":")[0],
                             "places": [f"{p['name']} ({_num(p['km'])} km)" for p in osm["pps"]]}
    if osm.get("status") == "ok" and osm.get("bridges"):
        f["bridges"] = [bridge_text(b, lang) for b in osm["bridges"]] + [T["low_ground"][lang]]
    if card.get("replay"):
        f["replay"] = card["replay"]
    out = {k: v for k, v in f.items() if v not in (None, [], "")}
    return json.loads(months_ms(json.dumps(out, ensure_ascii=False))) if lang == "ms" else out


LABEL_BM = (("SYNTHETIC reading - made up for the offline demo, not a real JPS reading",
             "bacaan SYNTHETIC - direka untuk demo luar talian, bukan bacaan JPS sebenar"),
            ("estimated: reconstructed between the verified JPS readings",
             "anggaran: dibina semula antara bacaan JPS yang disahkan"),
            ("reported JPS reading (", "bacaan JPS dilaporkan ("), ("; time approximate", "; masa anggaran"),
            (" and ", " dan "))


def label_text(label, lang):
    """A replay reading's label (written in English in the data) in the answer's language - same facts. A
    reconstructed reading always says estimated / anggaran on the card (Husaini 23 Oct)."""
    if label.startswith("reconstructed"):
        label = "estimated: " + label
    if lang == "ms":
        for en, ms in LABEL_BM:
            label = label.replace(en, ms)
    return label


def _age(minutes, lang):
    if minutes is None:
        return T["age_unknown"][lang]
    return T["min_ago"][lang].format(n=minutes) if minutes < 120 else T["h_ago"][lang].format(n=minutes // 60)


# Over MAX_CARD_CHARS, these are applied one by one until the card fits (Husaini 23 Oct): shorter gauge name and
# replay source, shorter reading label (still with its reading time), drop the "vs peak" part when the 2014 line is
# there, shorten the excluded-source line (the Critic checks it is there), then drop the rain and upstream lines.
# A line whose rule fired the verdict (card["keep"]: upstream / rain) is never dropped. The action, verdict, river
# level, the 2014 line, range + confidence, MET warnings and sources always stay.
FIT_STEPS = ("short_gauge", "short_source", "short_label", "peak_part", "excluded", "rain", "upstream")
# B-73 (Husaini 23 Oct): the OSM lines answer what the user asked (evacuation / cut-off questions only - the card has
# them for no other intent), so they sit outside the cap like the explanation: up to 3 possible PPS and 2 bridges.
OSM_LINES = ("pps", "bridge", "low_ground", "osm",
             "rain_up", "rain_here", "small_rivers", "until", "thailand", "tide", "thunder")   # + B-88 lines, outside the cap


def bridge_name(name, lang):
    """'Jambatan Sultan Yahya Petra' stays; a road name or ref -> 'Jambatan di Jalan Pasir Mas' / 'Bridge on ...'."""
    if re.match(r"(jambatan|bridge)\b", name or "", re.IGNORECASE):
        return name
    return T["bridge_on"][lang].format(road=name)


def bridge_text(b, lang):
    """One bridge as a fact: what it crosses, how far, and the river level at the nearest JPS gauge on that river."""
    if not b.get("has_gauge"):
        level = T["no_gauge"][lang]
    elif b.get("band"):
        level = BAND.get(b["band"], {}).get(lang, b["band"])
    else:
        level = T["no_level"][lang]
    return T["bridge"][lang].format(name=bridge_name(b["name"], lang), river=b["river"], km=_num(b["km"]), level=level)


def _osm_lines(card, lang):
    """B-73 lines: possible PPS (evacuation question) or bridges + low ground (cut-off question)."""
    osm = card.get("osm")
    if not osm:
        return []
    if osm["status"] != "ok":
        return [("osm", T["osm_failed"][lang] + ".")]
    out = []
    if osm.get("pps") is not None:
        pps = osm["pps"]
        out.append(("pps", T["pps"][lang].format(items="; ".join(f"{p['name']} ({_num(p['km'])} km)" for p in pps))
                    + "." if pps else T["pps_none"][lang] + "."))
    if osm.get("bridges") is not None:
        bridges = osm["bridges"]
        out += [("bridge", bridge_text(b, lang) + ".") for b in bridges] or [("bridge", T["bridge_none"][lang] + ".")]
        out.append(("low_ground", T["low_ground"][lang] + "."))
    return out


def render(card, lang, explanation=None, low_confidence=False):
    """Plain text for WhatsApp / SMS in 'en' or 'ms', at most ~MAX_CARD_CHARS (the explanation is extra). Only
    `explanation` comes from a model."""
    lang = lang if lang in ("en", "ms") else "en"
    drop = set()
    lines = _lines(card, lang, explanation, low_confidence, drop)
    for step in FIT_STEPS:
        if _length(lines) <= MAX_CARD_CHARS:
            break
        if step not in card.get("keep", ()):
            drop.add(step)
            lines = _lines(card, lang, explanation, low_confidence, drop)
    text = "\n".join(t for _, t in lines)
    return months_ms(text) if lang == "ms" else text


def _length(lines):
    return len("\n".join(t for key, t in lines if key != "explanation" and key not in OSM_LINES))


def short_label(label, read_at):
    """'reported JPS reading (Kosmo, 27 Nov 2024 20:19 (citing ...)); time approximate' -> 'reported JPS reading
    (Kosmo), 27 Nov 19:30; time approximate' - the reading time stays: it shows nothing later was used (Husaini
    23 Oct). Other labels unchanged."""
    m = re.match(r"reported JPS reading \(([^,(]+)", label or "")
    if not m:
        return label
    return (f"reported JPS reading ({m.group(1).strip()}), {read_at}"
            + ("; time approximate" if "time approximate" in label else ""))


def short_gauge(name, place):
    """'Sg. Golok di Rantau Panjang (F1)' at Rantau Panjang -> 'Sg. Golok'; other gauges lose only '(F1)'."""
    name = re.sub(r"\s*\(F\d\)$", "", name or "")
    tail = f" di {place}"
    return name[:-len(tail)] if place and name.endswith(tail) else name


def _lines(card, lang, explanation, low_confidence, drop):
    """The card's lines as (key, text) in reading order; `drop` = the FIT_STEPS applied so far."""
    out = [("replay", card["replay"])] if card.get("replay") else []     # a replay always says so first
    if low_confidence:
        out.append(("low_conf", T["low_conf"][lang]))
    if card.get("emergency"):                                            # safety first, labelled (Husaini 23 Oct)
        out.append(("stranded", T["stranded"][lang] + "."))
    out.append(("action", f"{T['action'][lang]}: {card['action'][lang]}"))
    level = (card.get("level_name") or {}).get(lang)
    out.append(("verdict", f"{card['place']}: {VERDICT_LABEL[card['verdict']][lang]}"
                            + (f" - {T['level'][lang]} {level}" if level else "")))
    if card.get("emergency") and card["verdict"] == "NORMAL":          # so the card does not look contradictory
        out.append(("stranded_note", T["stranded_normal"][lang] + "."))
    g = card.get("gauge")
    if g:
        parts = []
        for key in ("alert", "danger"):
            d = card["comparison"].get(key)
            if d is not None:
                parts.append(f"{_num(abs(d))} m {T['above' if d >= 0 else 'below'][lang]} {T[key][lang]} "
                             f"({_num(card['thresholds'][key])} m)")
        if card.get("peak") and not ("peak_part" in drop and card.get("vs_2014")):
            p = card["peak"]
            parts.append(f"{_num(abs(p['diff_m']))} m {T['above' if p['diff_m'] >= 0 else 'below'][lang]} "
                         f"{T['peak'][lang].format(event=p['event'])} ({_num(p['peak_m'])} m)")
        gauge = short_gauge(g["name"], card.get("place")) if "short_gauge" in drop else g["name"]
        tag = T["synthetic_tag"][lang] if card.get("synthetic") else ""
        out.append(("river", f"{T['river'][lang]}{tag}: {_num(g['level_m'])} m {T['at'][lang]} {g['read_at']} ({gauge})"
                    + ("; " + ", ".join(parts) if parts else "") + "."))
        if card.get("reading_label"):
            label = (short_label(card["reading_label"], g["read_at"]) if "short_label" in drop
                     else card["reading_label"])
            out.append(("label", f"({label_text(label, lang)})"))
        if card.get("vs_2014"):
            v = card["vs_2014"]
            out.append(("vs2014", T["vs2014"][lang].format(d=_num(abs(v["diff_m"])), p=_num(v["peak_m"]),
                                                          rel=T["above" if v["diff_m"] >= 0 else "below"][lang])
                        + tag + "."))
    elif card["verdict"] == "INSUFFICIENT_DATA" or card.get("no_river"):
        replay = bool(card.get("replay"))
        gap = "synthetic_gap" if card.get("synthetic") else "replay_gap"
        out.append(("no_reading", (T[gap][lang] if replay else T["no_reading"][lang].capitalize()) + "."))
        if card.get("last_reading"):
            lr = card["last_reading"]
            last = "synthetic_last" if card.get("synthetic") else "replay_last" if replay else "last"
            out.append(("last_reading", T[last][lang].format(
                m=_num(lr["level_m"]), t=lr["at"], age=_age(lr["age_minutes"], lang)) + "."))
    if card.get("backup"):
        b = card["backup"]
        silent = T["silent"][lang].format(t=b["since"]) if b.get("since") else T["silent_never"][lang]
        out.append(("backup", T["backup"][lang].format(primary=b["primary"], silent=silent, backup=b["backup"]) + "."))
    conf = T["conf_label"].get(card["confidence"], T["conf_label"]["low"])[lang]
    if card.get("range_24h"):
        r = card["range_24h"]
        out.append(("range", f"{T['next24'][lang]}{T['synthetic_tag'][lang] if card.get('synthetic') else ''}: "
                             f"{_num(r['min'])}-{_num(r['max'])} m ({T['trend'][lang]}). "
                             f"{T['confidence'][lang]}: {conf}."))
    elif card.get("pass_danger") and g:
        out.append(("range", f"{T['next24'][lang]}{T['synthetic_tag'][lang] if card.get('synthetic') else ''}: "
                             f"{T['pass_danger'][lang]}. {T['confidence'][lang]}: {conf}."))
    elif card.get("above_danger") and g:
        words = [T["above_trend"][card["trend"]][lang]] if card.get("trend") else []
        peak = card.get("peak") or {}
        above_2014 = (card.get("vs_2014") or {}).get("diff_m", -1) > 0 or (
            peak.get("event") == "Dec 2014" and peak.get("diff_m", -1) > 0)
        if above_2014:
            words.append(T["higher_2014"][lang])
        out.append(("range", (f"{T['next24'][lang]}: {', '.join(words)}. " if words else "")
                    + f"{T['confidence'][lang]}: {conf}."))
    elif card.get("falling") and g:
        out.append(("range", f"{T['next24'][lang]}: {T['falling'][lang]}. {T['confidence'][lang]}: {conf}."))
    else:
        out.append(("range", (f"{T['tidal'][lang].capitalize()}. " if card.get("tidal") and g else "")
                    + f"{T['confidence'][lang]}: {conf}."))
    if card.get("rain_24h_mm") is not None and "rain" not in drop:
        out.append(("rain", T["rain"][lang].format(mm=_num(card["rain_24h_mm"])) + "."))
    if card.get("rain_past_24h_mm") is not None and "rain" not in drop:
        out.append(("rain", T["rain_past"][lang].format(mm=_num(card["rain_past_24h_mm"]),
                                                        date=card.get("rain_date") or "?") + "."))
    out += rain_lines(card, lang)
    if explanation:
        out.append(("explanation", explanation.strip()))
    for u in ([] if "upstream" in drop else card.get("upstream", [])):
        bits = [BAND.get(u["band"], {}).get(lang, u["band"])] if u.get("band") else []
        if u.get("rising"):
            bits.append(T["rising"][lang])
        a = u.get("arrives_in_h")
        tail = f", {T['may_reach'][lang].format(a=_num(a['min']), b=_num(a['max']))}" if a and a.get("min") is not None else ""
        out.append(("upstream", f"{T['upstream'][lang]}: {u['gauge']} ({', '.join(bits)}){tail}."))
    for w in card.get("warnings", []):
        out.append(("warning", f"{T['warning'][lang]}: {w}."))
    out += _osm_lines(card, lang)
    names = {"jps": "JPS", "open_meteo": "Open-Meteo", "met_forecast": None, "archive": None, "synthetic": None,
             "osm": None}
    archive = "archive_short" if "short_source" in drop else "archive"
    other = {"archive": archive, "met_forecast": "met_today", "synthetic": "synthetic_src", "osm": "osm_src"}
    srcs = [f"{names[k]} {_age(m, lang)}" if names[k] else T[other[k]][lang] for k, m in card.get("sources", [])]
    if srcs:
        out.append(("sources", f"{T['sources'][lang]}: " + "; ".join(srcs) + "."))
    if card.get("excluded"):                         # shortened, never dropped: the Critic checks it is mentioned
        out.append(("excluded", (T["excluded_short"][lang] if "excluded" in drop else
                                 T["excluded"][lang].format(when=card["excluded"])) + "."))
    if card.get("not_checked"):
        out.append(("not_checked", T["not_checked"][lang] + "."))
    for d in card.get("discovered") or []:            # B-71(c): approved discovered gauges, context only
        level = (f"{T['level'][lang]} {BAND.get(d['band'], {}).get(lang, d['band'])}" if d.get("band")
                 else T["no_level"][lang])
        out.append(("discovered", T["discovered"][lang].format(name=d["name"], by=d.get("approved_by") or "?",
                                                               level=level) + "."))
    if card.get("missing"):                          # B-71(b): never dropped - a gap is said plainly
        out.append(("missing", T["missing"][lang].format(gauges=", ".join(m["gauge"] for m in card["missing"])) + "."))
    if card.get("met_not_checked"):                  # never dropped: an unread source is never hidden
        out.append(("met_not_checked", T["met_not_checked"][lang].format(
            what=T["met_what"][tuple(card["met_not_checked"])][lang]) + "."))
    for q in card.get("conflicts", []):
        out.append(("conflict", T["conflict"][lang].format(q=q) + "."))
    return out


def _values(text):
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text or "")}


def numbers(card):
    """Every number the card shows, in either language, as values ('7.0' = '7') - what an explanation may use."""
    return _values(render(card, "en") + "\n" + render(card, "ms"))


SIDE = r"(above|below|over|under|di atas|di bawah|melebihi|bawah)"
MARK = r"(alert|warning|danger|waspada|amaran|bahaya|peak|puncak)"
COMPARISON = re.compile(rf"\b(?P<side>{SIDE})\s+(?:[\w.]+\s+){{0,3}}?(?P<mark>{MARK})\b", re.IGNORECASE)
SIDE_OF = {"above": "above", "over": "above", "di atas": "above", "melebihi": "above",
           "below": "below", "under": "below", "di bawah": "below", "bawah": "below"}
MARK_OF = {"waspada": "alert", "amaran": "warning", "bahaya": "danger", "puncak": "peak"}
# Words that tell a worried resident all is well - never under a WATCH / PREPARE / ACT card (audit 23 Oct).
REASSURE = re.compile(
    r"\b(calm|nothing to worry|no need to (worry|move|evacuate|leave|act|prepare)|no (danger|risk)|"
    r"(is|are|stays?|remains?|still) (safe|fine|okay|ok|under control)|all (is )?(safe|fine|clear)|"
    r"tenang|tiada (bahaya|risiko)|tidak perlu (risau|bimbang|pindah|berpindah|keluar|bersedia)|"
    r"tak perlu (risau|bimbang|pindah|keluar)|jangan (risau|bimbang)|(masih|adalah|kekal) (selamat|terkawal)|"
    r"keadaan (selamat|terkawal|normal))\b", re.IGNORECASE)


def _comparisons(text):
    return {(MARK_OF.get(m["mark"].lower(), m["mark"].lower()), SIDE_OF[m["side"].lower()])
            for m in COMPARISON.finditer(text or "")}


# Husaini 23 Oct (tentative, review pack G4): Indonesian words that should not appear in a Malaysian BM
# explanation. Not "aman" (normal BM) and never "Waspada" (a JPS level name).
INDONESIAN = ("alarm", "aturan", "kondisi", "terpicu", "bisa", "mengungsi", "pengungsian", "siaga", "rumah sakit",
              "ponsel", "kabupaten", "banget", "telepon", "tingkat air")
STYLE_PLACE = "tanah merah"     # the place in the draft prompt's style examples - never in a real explanation
_INDONESIAN = re.compile(r"\b(" + "|".join(re.escape(w) for w in INDONESIAN) + r")\b", re.IGNORECASE)
_INTERNAL = re.compile(r"\b(rules?|trigger(?:s|ed)?|verdicts?|sentinels?)\b", re.IGNORECASE)
_TREND = re.compile(r"\b(naik|turun|surut|meningkat|menurun|rising|falling|rises|falls|risen|fallen)\b", re.IGNORECASE)
# A1 (24 Oct evening): the words that say which way the river here is going, per computed trend
_TREND_WORDS = {"rising": re.compile(r"\b(naik|meningkat|rising|rises|risen)\b", re.IGNORECASE),
                "falling": re.compile(r"\b(turun|surut|menurun|falling|falls|fallen|dropping|receding)\b", re.IGNORECASE),
                "steady": re.compile(r"\b(stabil|steady|unchanged|tidak berubah)\b", re.IGNORECASE)}
_NOT_HERE = re.compile(r"\b(hulu|upstream|hujan|rain|rainfall)\b", re.IGNORECASE)   # upstream / rain sentences
_MINUS = re.compile(r"(?<![\w.])[-−–]\s?\d")             # "-0.57" - not the dash in a range "5.3-5.47"


# B-73 (approved 23 Oct): no text may say a PPS is open, or predict a road / bridge being cut off or flooded - OSM
# knows neither, and no cut-off rule is approved yet (review pack, Dr Ariff).
PPS_OPEN = re.compile(
    r"\b(PPS|pusat pemindahan|relief cent(?:re|er)s?|evacuation cent(?:re|er)s?)\b[^.\n]{0,60}?"
    r"\b(dibuka|beroperasi|is open|are open|(?:has|have) opened|now open|operating|open now)\b|"
    r"\b(dibuka|opened)\b[^.\n]{0,20}?\b(PPS|pusat pemindahan)\b", re.IGNORECASE)
CUT_OFF = re.compile(
    r"\b(akan|boleh|mungkin|pasti|dijangka)\s+(ter)?putus\b|"
    r"\b(will|may|might|could|is likely to|are likely to)\s+be\s+cut\s+off\b|"
    r"\b(jalan|jambatan|roads?|bridges?)\b[^.\n]{0,30}?\b(akan|boleh|mungkin|will|may|might|could)\s+(be\s+)?"
    r"(ditenggelami|tenggelam|dinaiki air|ditutup|flood(?:ed)?|closed|submerged)\b", re.IGNORECASE)


def osm_claim(text):
    """None, or the claim VEDA may never make: an open PPS, or a road / bridge predicted to be cut off."""
    for pattern, what in ((PPS_OPEN, "says a PPS is open (VEDA cannot know)"),
                          (CUT_OFF, "predicts a road / bridge being cut off (no approved rule)")):
        m = pattern.search(text or "")
        if m:
            return f"{what}: {m.group(0)!r}"
    return None


def trend_problem(text, card):
    """No trend known for the controlling gauge (tidal, no rates) -> the explanation may not say the river is rising
    or falling (Husaini 23 Oct: Tumpat 'tahap air turun' was invented). An upstream gauge that is rising is a fact."""
    if card.get("trend") or any(u.get("rising") for u in card.get("upstream", [])):
        return None
    m = _TREND.search(text or "")
    return f"wording: says {m.group(0)!r} but no trend is known for this gauge" if m else None


def trend_match_problem(text, card):
    """A1 (safety, 24 Oct evening): rising / falling / steady words about the river HERE must match the card's computed
    trend. Sentences about upstream or rain are skipped (an upstream gauge may rise while this one falls; 'hujan turun'
    is rain falling). No trend known is trend_problem's job."""
    trend = card.get("trend")
    if not trend:
        return None
    upstream = [gauge_place(u.get("gauge") or "").lower().replace(".", "") for u in card.get("upstream", [])]
    plain = re.sub(r"\b(Kg|Sg|Kpg|Jln|Bt)\.", r"\1", text or "")      # "Kg. Jenob" is not a sentence end
    for sentence in re.split(r"(?<=[.!?])\s+", plain):
        low = sentence.lower()
        if _NOT_HERE.search(sentence) or any(p and p in low for p in upstream):
            continue
        for other, rx in _TREND_WORDS.items():
            m = rx.search(sentence) if other != trend else None
            if m:
                return f"trend: says {m.group(0)!r} about the river here, but its computed trend is {trend}"
    return None


def wording_problem(text, lang, place=None):
    """None, or why the explanation's wording is not fit for residents (code check, no model)."""
    if STYLE_PLACE in (text or "").lower() and (place or "").strip().lower() != STYLE_PLACE:
        return "wording: copied the style example's place (Tanah Merah) - write about the user's place"
    m = _MINUS.search(text or "")
    if m:
        return f"wording: a minus sign before a number ({m.group(0)!r})"
    m = _INTERNAL.search(text or "")
    if m:
        return f"wording: internal term {m.group(0)!r}"
    if lang == "ms":
        m = _INDONESIAN.search(text or "")
        if m:
            return f"wording: Indonesian word {m.group(0)!r} - use standard Malaysian BM"
    return None


def explanation_problem(text, card, lang=None):
    """None if Nemotron's explanation may be inserted, else why not (Husaini 22 Oct night: numbers from the card)."""
    if not isinstance(text, str) or not text.strip():
        return "empty explanation"
    if len(text) > MAX_EXPLANATION:
        return f"explanation too long ({len(text)} > {MAX_EXPLANATION} characters)"
    said = verdict_codes(text)
    if said - {card["verdict"]}:
        return f"names a verdict ({', '.join(sorted(said))}) that is not the card's ({card['verdict']})"
    unknown = sorted(_values(text) - numbers(card))
    if unknown:
        return f"number(s) not in the card: {', '.join(_num(u) for u in unknown[:4])}"
    shown = _comparisons(render(card, "en") + "\n" + render(card, "ms"))
    flipped = sorted(f"{s} {m}" for m, s in _comparisons(text) - shown if any(m == k for k, _ in shown))
    if flipped:
        return f"says the river is {', '.join(flipped)}, but the card says otherwise"
    if card["verdict"] in ("WATCH", "PREPARE", "ACT") and REASSURE.search(text):
        return f"reassuring words ({REASSURE.search(text).group(0)!r}) under a {card['verdict']} card"
    return (osm_claim(text) or trend_problem(text, card) or trend_match_problem(text, card)
            or wording_problem(text, lang, card.get("place")))


def emergency_reply(lang, rest):
    """Someone trapped / stranded and no place found: the ACT advice first (it ends with 'if trapped: stay on high
    ground, save phone battery, call 999 / 991'), then the usual place reply."""
    return f"{T['stranded'][lang]}.\n{T['action'][lang]}: {ADVICE['ACT'][lang]}\n{rest}"


def unavailable_reply(lang):
    """The reply when VEDA's data (Zetaris) cannot be reached at all - no place, no verdict (audit 23 Oct)."""
    return {"en": "VEDA cannot reach its river data right now, so it cannot check any place. Check JPS "
                  "Infobanjir; call 999 if you are in danger.",
            "ms": "VEDA tidak dapat mencapai data sungai sekarang, jadi tidak dapat menyemak mana-mana tempat. "
                  "Semak JPS Infobanjir; hubungi 999 jika anda dalam bahaya."}[lang]


def place_reply(res, lang):
    """The reply when the place is not found: 'Did you mean...?' or 'not covered yet' + the nearest covered place,
    in the user's language."""
    covered = ", ".join(res.covered) if getattr(res, "covered", None) else ""
    if res.status == "did_you_mean":
        names = " / ".join(res.suggestions)
        return {"en": f"Did you mean {names}?", "ms": f"Adakah maksud anda {names}?"}[lang]
    known, near = getattr(res, "known", None), getattr(res, "nearest", None)
    if known and known.strip().lower() == "kelantan":       # the whole state: ask for a town or district
        return {"en": f"Please name a town or district in Kelantan. Covered places: {covered}.",
                "ms": f"Sila nyatakan bandar atau daerah di Kelantan. Tempat yang diliputi: {covered}."}[lang]
    if known and near:
        return {"en": f"{known} is in Kelantan but not covered by VEDA yet. Nearest covered place: {near['name']} "
                      f"(about {near['km']} km away). Covered places: {covered}.",
                "ms": f"{known} terletak di Kelantan tetapi belum diliputi VEDA. Tempat terdekat yang diliputi: {near['name']} "
                      f"(kira-kira {near['km']} km). Tempat yang diliputi: {covered}."}[lang]
    if known:
        return {"en": f"{known} is in Kelantan but not covered by VEDA yet. Covered places: {covered}.",
                "ms": f"{known} terletak di Kelantan tetapi belum diliputi VEDA. Tempat yang diliputi: {covered}."}[lang]
    return {"en": f"That place is not covered by VEDA yet. Covered places: {covered}.",
            "ms": f"Tempat itu belum diliputi VEDA. Tempat yang diliputi: {covered}."}[lang]
