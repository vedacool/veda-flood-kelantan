"""Answer card (B-21): one forwardable answer per place, in BM and EN, assembled by CODE.

    card = card.build(plan, evidence, forecast)
    text = card.render(card, "ms", explanation=None)     # WhatsApp/SMS-length plain text

Order (user first): what to do now -> verdict + JPS level name -> plain comparison (thresholds, past peaks) ->
range + confidence -> [explanation written by Nemotron, full path only] -> upstream / warnings -> sources with age,
excluded stale sources, unresolved conflicts. The disclaimer + 999 / 991 is the answer's safety line.
Everything except the explanation is inserted verbatim by code (Husaini 22 Oct night); the explanation may only use
numbers that are in the card (`explanation_problem`). Advice texts are TENTATIVE (review pack section G).
"""
import re
from datetime import datetime

from app.config import MYT, REPLAYS

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
    "rain_past": {"en": "Rain past 24 h: {mm} mm (Open-Meteo archive); no rain forecast in a replay",
                  "ms": "Hujan 24 jam lepas: {mm} mm (arkib Open-Meteo); tiada ramalan hujan dalam ulang tayang"},
    "vs2014": {"en": "Compared with 2014: {d} m {rel} the Dec 2014 peak here ({p} m)",
               "ms": "Berbanding 2014: {d} m {rel} puncak Dis 2014 di sini ({p} m)"},
    "archive": {"en": "Open-Meteo archive (real rain up to the replay time)",
                "ms": "arkib Open-Meteo (hujan sebenar sehingga masa ulang tayang)"},
    "trend": {"en": "straight-line trend", "ms": "unjuran garis lurus"},
    "tidal": {"en": "trend not projected (tide-influenced gauge)", "ms": "trend tidak diunjurkan (stesen dipengaruhi pasang surut)"},
    "confidence": {"en": "Confidence", "ms": "Keyakinan"},
    "conf_label": {"high": {"en": "high", "ms": "tinggi"}, "medium": {"en": "medium", "ms": "sederhana"},
                   "low": {"en": "low", "ms": "rendah"}},
    "upstream": {"en": "Upstream", "ms": "Hulu"},
    "may_reach": {"en": "may reach here in {a}-{b} h", "ms": "mungkin sampai ke sini dalam {a}-{b} jam"},
    "rising": {"en": "rising", "ms": "sedang naik"},
    "warning": {"en": "MetMalaysia warning", "ms": "Amaran MetMalaysia"},
    "sources": {"en": "Sources", "ms": "Sumber"},
    "min_ago": {"en": "{n} min ago", "ms": "{n} minit lalu"},
    "h_ago": {"en": "{n} h ago", "ms": "{n} jam lalu"},
    "age_unknown": {"en": "update time unknown", "ms": "masa kemas kini tidak diketahui"},
    "met_today": {"en": "MetMalaysia forecast for today", "ms": "ramalan MetMalaysia hari ini"},
    "excluded": {"en": "Excluded: data.gov.my flood-warning (stale, last update {when})",
                 "ms": "Diketepikan: data.gov.my flood-warning (lapuk, kemas kini terakhir {when})"},
    "conflict": {"en": "Sources disagree on {q}; VEDA did not pick one", "ms": "Sumber tidak sepakat tentang {q}; VEDA tidak memilih"},
    "no_reading": {"en": "no fresh reading from the controlling gauge", "ms": "tiada bacaan terkini dari stesen utama"},
    "backup": {"en": "Note: {primary} {silent} - using the backup gauge {backup}",
               "ms": "Nota: {primary} {silent} - menggunakan stesen ganti {backup}"},
    "silent": {"en": "has no reading since {t}", "ms": "tiada bacaan sejak {t}"},
    "silent_never": {"en": "has no reading", "ms": "tiada bacaan"},
    "last": {"en": "Last reading: {m} m at {t} ({age}) - too old to use", "ms": "Bacaan terakhir: {m} m pada {t} ({age}) - terlalu lama untuk digunakan"},
    "low_conf": {"en": "Low confidence: VEDA's reviewer did not approve the written explanation, so only the checked "
                       "data is shown.",
                 "ms": "Keyakinan rendah: penyemak VEDA tidak meluluskan penjelasan bertulis, jadi hanya data yang "
                       "telah disemak dipaparkan."},
}
BAND = {"below_normal": {"en": "Below normal", "ms": "Bawah normal"}, "normal": {"en": "Normal", "ms": "Normal"},
        "alert": {"en": "Alert", "ms": "Waspada"}, "warning": {"en": "Warning", "ms": "Amaran"},
        "danger": {"en": "Danger", "ms": "Bahaya"}}
VERDICT_WORDS = re.compile(r"\b(NORMAL|WATCH|PREPARE|ACT|INSUFFICIENT[ _]DATA)\b")
MAX_EXPLANATION = 400
MAX_CARD_CHARS = 900          # about one phone screen in WhatsApp (BM ACT card with the agreed advice: ~760)


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
            "range_24h": None, "tidal": bool(trend.get("tide_influenced")), "peak": None, "upstream": [],
            "warnings": [w["heading"] for w in ((evidence or {}).get("met_warnings") or {}).get("active", [])],
            "sources": [], "excluded": None, "conflicts": [], "vs_2014": None, "rain_past_24h_mm": None,
            "replay": (REPLAYS.get(((evidence or {}).get("replay") or {}).get("scenario")) or {}).get("title"),
            "reading_label": None, "backup": None, "last_reading": None}
    if main and main["level_m"] is not None and verdict != "INSUFFICIENT_DATA":
        th = main["thresholds"]
        card["gauge"] = {"name": main["name"], "level_m": main["level_m"], "read_at": _hhmm(main["observed_at"])}
        card["reading_label"] = ((main.get("provenance") or {}).get("replay") or {}).get("label")
        for key in ("alert", "danger"):
            if th.get(f"{key}_m") is not None:
                card["comparison"][key] = round(main["level_m"] - th[f"{key}_m"], 2)
                card["thresholds"][key] = th[f"{key}_m"]
        rng = (trend.get("projection_m") or {}).get("24h")
        card["range_24h"] = rng
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
    if last and verdict == "INSUFFICIENT_DATA":
        card["last_reading"] = {"level_m": last["level_m"], "at": _hhmm(last["observed_at"]),
                                "age_minutes": last["age_minutes"]}
    if main and main["age_minutes"] is not None:
        card["sources"].append(("jps", main["age_minutes"]))
    rain = ctx.get("rain")
    if rain and card["replay"]:
        card["sources"].append(("archive", None))
        card["rain_past_24h_mm"] = rain.get("rain_past_24h_mm")
    elif rain:
        card["sources"].append(("open_meteo", rain.get("age_minutes")))
        card["rain_24h_mm"] = rain.get("rain_next_24h_mm")
    if ctx.get("met_forecast"):
        card["sources"].append(("met_forecast", None))
    cross = (evidence or {}).get("cross_check") or {}
    if cross.get("status") == "stale":
        card["excluded"] = (cross.get("newest") or "").split(" ")[0] or "?"
    card["conflicts"] = [c["quantity"] for c in (evidence or {}).get("conflicts_unresolved", [])]
    return card


LABEL_BM = (("reconstructed between the verified JPS readings", "dibina semula antara bacaan JPS yang disahkan"),
            ("reported JPS reading", "bacaan JPS yang dilaporkan"), ("; time approximate", "; masa anggaran"),
            (" and ", " dan "))


def label_text(label, lang):
    """A replay reading's label (written in English in the data) in the answer's language - same facts."""
    if lang == "ms":
        for en, ms in LABEL_BM:
            label = label.replace(en, ms)
    return label


def _age(minutes, lang):
    if minutes is None:
        return T["age_unknown"][lang]
    return T["min_ago"][lang].format(n=minutes) if minutes < 120 else T["h_ago"][lang].format(n=minutes // 60)


def render(card, lang, explanation=None, low_confidence=False):
    """Plain text for WhatsApp / SMS in 'en' or 'ms'. Only `explanation` comes from a model."""
    lang = lang if lang in ("en", "ms") else "en"
    out = [card["replay"]] if card.get("replay") else []          # a replay always says so first
    if low_confidence:
        out.append(T["low_conf"][lang])
    out.append(f"{T['action'][lang]}: {card['action'][lang]}")
    level = (card.get("level_name") or {}).get(lang)
    out.append(f"{card['place']}: {card['verdict']}" + (f" - {T['level'][lang]} {level}" if level else ""))
    g = card.get("gauge")
    if g:
        parts = []
        for key in ("alert", "danger"):
            d = card["comparison"].get(key)
            if d is not None:
                parts.append(f"{_num(abs(d))} m {T['above' if d >= 0 else 'below'][lang]} {T[key][lang]} "
                             f"({_num(card['thresholds'][key])} m)")
        if card.get("peak"):
            p = card["peak"]
            parts.append(f"{_num(abs(p['diff_m']))} m {T['above' if p['diff_m'] >= 0 else 'below'][lang]} "
                         f"{T['peak'][lang].format(event=p['event'])} ({_num(p['peak_m'])} m)")
        out.append(f"{T['river'][lang]}: {_num(g['level_m'])} m {T['at'][lang]} {g['read_at']} ({g['name']})"
                   + ("; " + ", ".join(parts) if parts else "") + ".")
        if card.get("reading_label"):
            out.append(f"({label_text(card['reading_label'], lang)})")
        if card.get("vs_2014"):
            v = card["vs_2014"]
            out.append(T["vs2014"][lang].format(d=_num(abs(v["diff_m"])), p=_num(v["peak_m"]),
                                                rel=T["above" if v["diff_m"] >= 0 else "below"][lang]) + ".")
    elif card["verdict"] == "INSUFFICIENT_DATA":
        out.append(T["no_reading"][lang].capitalize() + ".")
        if card.get("last_reading"):
            lr = card["last_reading"]
            out.append(T["last"][lang].format(m=_num(lr["level_m"]), t=lr["at"], age=_age(lr["age_minutes"], lang))
                       + ".")
    if card.get("backup"):
        b = card["backup"]
        silent = T["silent"][lang].format(t=b["since"]) if b.get("since") else T["silent_never"][lang]
        out.append(T["backup"][lang].format(primary=b["primary"], silent=silent, backup=b["backup"]) + ".")
    conf = T["conf_label"].get(card["confidence"], T["conf_label"]["low"])[lang]
    if card.get("range_24h"):
        r = card["range_24h"]
        out.append(f"{T['next24'][lang]}: {_num(r['min'])}-{_num(r['max'])} m ({T['trend'][lang]}). "
                   f"{T['confidence'][lang]}: {conf}.")
    else:
        out.append((f"{T['tidal'][lang].capitalize()}. " if card.get("tidal") and g else "")
                   + f"{T['confidence'][lang]}: {conf}.")
    if card.get("rain_24h_mm") is not None:
        out.append(T["rain"][lang].format(mm=_num(card["rain_24h_mm"])) + ".")
    if card.get("rain_past_24h_mm") is not None:
        out.append(T["rain_past"][lang].format(mm=_num(card["rain_past_24h_mm"])) + ".")
    if explanation:
        out.append(explanation.strip())
    for u in card.get("upstream", []):
        bits = [BAND.get(u["band"], {}).get(lang, u["band"])] if u.get("band") else []
        if u.get("rising"):
            bits.append(T["rising"][lang])
        a = u.get("arrives_in_h")
        tail = f", {T['may_reach'][lang].format(a=_num(a['min']), b=_num(a['max']))}" if a and a.get("min") is not None else ""
        out.append(f"{T['upstream'][lang]}: {u['gauge']} ({', '.join(bits)}){tail}.")
    for w in card.get("warnings", []):
        out.append(f"{T['warning'][lang]}: {w}.")
    names = {"jps": "JPS", "open_meteo": "Open-Meteo", "met_forecast": None, "archive": None}
    srcs = [f"{names[k]} {_age(m, lang)}" if names[k] else T["archive" if k == "archive" else "met_today"][lang]
            for k, m in card.get("sources", [])]
    if srcs:
        out.append(f"{T['sources'][lang]}: " + "; ".join(srcs) + ".")
    if card.get("excluded"):
        out.append(T["excluded"][lang].format(when=card["excluded"]) + ".")
    for q in card.get("conflicts", []):
        out.append(T["conflict"][lang].format(q=q) + ".")
    return "\n".join(out)


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


def explanation_problem(text, card):
    """None if Nemotron's explanation may be inserted, else why not (Husaini 22 Oct night: numbers from the card)."""
    if not isinstance(text, str) or not text.strip():
        return "empty explanation"
    if len(text) > MAX_EXPLANATION:
        return f"explanation too long ({len(text)} > {MAX_EXPLANATION} characters)"
    said = {w.replace(" ", "_") for w in VERDICT_WORDS.findall(text)}
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
    return None


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
                "ms": f"{known} di Kelantan tetapi belum diliputi VEDA. Tempat terdekat yang diliputi: {near['name']} "
                      f"(kira-kira {near['km']} km). Tempat yang diliputi: {covered}."}[lang]
    if known:
        return {"en": f"{known} is in Kelantan but not covered by VEDA yet. Covered places: {covered}.",
                "ms": f"{known} di Kelantan tetapi belum diliputi VEDA. Tempat yang diliputi: {covered}."}[lang]
    return {"en": f"That place is not covered by VEDA yet. Covered places: {covered}.",
            "ms": f"Tempat itu belum diliputi VEDA. Tempat yang diliputi: {covered}."}[lang]
