"""Router (B-17, Husaini 22 Oct night): CODE decides quick vs full and the answer language - before any AI call.

    r = router.route(question, place, world, pre)      -> {effort: quick | full, reasons, language, notes}
    p = router.code_plan(question, resolution, r)      the plan, written by code on BOTH paths (22 Oct night)

Full if ANY of these (the reasons go into the trace):
    a linked gauge (controlling, second controlling or upstream sentinel) is at or above Alert
    a rising trend at a linked gauge (>= RISING_3H_M in 3 h or >= RISING_1H_M in 1 h; tide-influenced gauges excluded)
    an active MetMalaysia rain/thunderstorm warning for the area (a stale warnings feed triggers nothing)
    a stale or missing source (controlling or upstream gauge without a fresh reading; no rain or MET forecast data)
    the question is about evacuation, being cut off, rising water or the coming days (BM, EN, Kelantan dialect)
Otherwise quick. Language: any BM word in the question -> answer in BM (mixed BM/EN is normal in Kelantan).
User type from the question's words: school (sekolah, cikgu...) before family (mak, anak, orang tua...) before
resident (saya, rumah saya...), else unknown.
Word lists and the two rise limits are TENTATIVE (Husaini / Dr Ariff to review).
"""
import re

from app import trace
from app.agents import data_agent
from app.engines.world_model.context import ContextBuilder
from app.engines.world_model.veda_ingest import place_id

AGENT = "Coordinator"            # the routing is the Coordinator's code part, before its AI planning
RISING_3H_M = 0.3
RISING_1H_M = 0.15
ALERT_BANDS = ("alert", "warning", "danger")

# Any of these words -> answer in BM. Standard Malay + common Kelantan dialect words (gapo, demo, kawe, nok...).
BM_WORDS = {
    "saya", "aku", "kami", "kita", "awak", "anda", "rumah", "mak", "ayah", "emak", "abah", "keluarga", "anak",
    "banjir", "sungai", "paras", "naik", "surut", "selamat", "bahaya", "tak", "tidak", "ke", "kah", "ni", "ini",
    "itu", "tu", "malam", "esok", "lusa", "pagi", "petang", "hari", "minggu", "sekarang", "pindah", "perlu",
    "patut", "patutkah", "boleh", "ada", "adakah", "apa", "bila", "bagaimana", "macam", "mana", "kampung",
    "kawasan", "jalan", "hujan", "lebat", "terkandas", "terperangkap", "keluar", "sekolah", "kat", "dekat", "di",
    "dah", "sudah", "akan", "lagi", "nak", "mahu", "risau", "takut", "tolong", "berapa", "tinggi", "air",
    # Kelantan dialect
    "gapo", "demo", "kawe", "ambo", "nok", "bakpo", "dok", "doh", "ore", "molek", "tubik", "guano", "mung", "kito",
    "kalu", "sapa", "leh", "gak",
}
QUESTION_TRIGGERS = {
    "evacuation": ["pindah", "kena pindah", "berpindah", "evacuate", "evacuation", "evacuated", "pps",
                   "pusat pemindahan", "relief centre", "relief center", "move out", "keluar rumah"],
    "cut_off": ["terputus", "terkandas", "terperangkap", "tak boleh keluar", "tak leh keluar", "tidak boleh keluar",
                "cut off", "trapped", "stranded", "jalan tutup", "jalan ditutup", "road closed"],
    "rising_water": ["air naik", "rising", "naik ke"],
    "next_days": ["esok", "lusa", "minggu ni", "minggu ini", "malam ni", "malam ini", "tomorrow", "tonight",
                  "this week", "next days", "coming days", "next few days", "next two days", "next 2 days",
                  "24 jam", "48 jam", "24 hours", "48 hours"],
}


# Who is asking - checked in this order (Husaini 22 Oct night + Claude's list). Phrases match whole words.
USER_TYPES = [
    ("school", ["sekolah", "school", "murid", "pelajar", "cikgu", "guru", "teacher", "student", "students", "pupils",
                "spm", "asrama"]),
    ("family_far_away", ["mak", "emak", "ayah", "abah", "ibu", "bapa", "parents", "mother", "father", "mum", "mom",
                         "dad", "keluarga", "family", "nenek", "atuk", "datuk", "grandma", "grandmother", "grandfather",
                         "anak", "isteri", "suami", "wife", "husband", "rumah mak", "orang tua", "warga emas",
                         "elderly", "adik", "abang", "kakak", "sister", "brother", "relatives", "saudara"]),
    ("resident", ["saya", "aku", "kami", "kita", "rumah saya", "my house", "my home", "i live", "we live", "kawe",
                  "ambo"]),
]


def _words(question):
    return re.findall(r"[a-z0-9']+", (question or "").lower())


def language(question):
    """'ms' if any BM word appears (mixed BM/EN counts as BM), else 'en'."""
    return "ms" if set(_words(question)) & BM_WORDS else "en"


# Someone already in trouble (23 Oct eval): the ACT advice (with "if trapped: ... 999 / 991") comes first,
# whatever the river data says and even when the place is unknown.
EMERGENCY = ["terkandas", "terperangkap", "tak boleh keluar", "tak leh keluar", "tidak boleh keluar",
             "air keliling rumah", "air masuk rumah", "air dalam rumah", "trapped", "stranded", "can't get out",
             "cannot get out", "water around my house", "water in my house"]


def emergency(question):
    """The emergency phrase in the question, or None (whole words / phrases only)."""
    text = " " + " ".join(_words(question)) + " "
    return next((ph for ph in EMERGENCY if f" {' '.join(_words(ph))} " in text), None)


def question_triggers(question):
    """[(kind, phrase)] for each trigger phrase in the question (whole words / whole phrases only)."""
    text = " " + " ".join(_words(question)) + " "
    return [(kind, ph) for kind, phrases in QUESTION_TRIGGERS.items() for ph in phrases if f" {ph} " in text]


def data_triggers(ctx, warnings, clock, scene=False):
    """Reasons from the data for one place (World Model context + MetMalaysia warnings)."""
    reasons = []
    linked = ctx.get("gauges", []) + ctx.get("sentinels", [])
    for g in linked:
        if g["band"] in ALERT_BANDS:
            reasons.append(f"{g['name']} is at {g['band']} ({g['level_m']} m)")
        if not g.get("tide_influenced") and ((g.get("change_3h_m") or 0) >= RISING_3H_M
                                             or (g.get("change_1h_m") or 0) >= RISING_1H_M):
            reasons.append(f"{g['name']} is rising ({g.get('change_1h_m')} m in 1 h, {g.get('change_3h_m')} m in 3 h)")
        fresh = data_agent.freshness("jps_levels", g["age_minutes"])
        if g["level_m"] is None or fresh in ("stale", "unknown"):
            reasons.append(f"{g['name']} has no fresh reading ({'none' if g['level_m'] is None else fresh})")
    if not ctx.get("gauges"):
        reasons.append("no controlling gauge data")
    if ctx.get("rain") is None:
        reasons.append("no rain forecast data")
    if ctx.get("met_forecast") is None and not scene:   # a scene has no MET data on purpose (no 2024 archive)
        reasons.append("no MetMalaysia forecast for today")
    for w in (warnings or {}).get("active", []):
        reasons.append(f"active MetMalaysia warning: {w['heading']}")
    ru = ctx.get("rain_upstream") or {}                 # B-88: heavy rain upstream or here -> the full path
    if ru.get("heavy_upstream"):
        reasons.append(f"heavy rain upstream ({', '.join(ru['heavy_upstream'])})")
    if (ru.get("local") or {}).get("heavy"):
        reasons.append(f"heavy rain here ({ru['local']['max_12h_mm']} mm in 12 h)")
    return reasons


def route(question, place, world, pre):
    """quick or full for this question and place. pre = the Data & Reconciler prefetch result. Traced."""
    lang = language(question)
    asked = question_triggers(question)
    reasons = [f"question mentions '{ph}' ({kind.replace('_', ' ')})" for kind, ph in asked]
    notes = []
    if pre.get("error"):
        reasons.append(f"data could not be loaded ({pre['error'].kind})")
    else:
        clock = pre["clock"]
        ctx = ContextBuilder(world).build("route", place_id(place["place_id"]), now=clock)
        warnings = data_agent.met_warnings(pre["results"].get(data_agent.WARNING_SQL), place, clock, world)
        if warnings["status"] != "ok":
            notes.append(warnings["note"])
        reasons += data_triggers(ctx, warnings, clock, scene=bool(pre.get("replay")))
    effort = "full" if reasons else "quick"
    trace.step(AGENT, "route", input_summary=question,
               output_summary=f"{effort} path, answer in {'BM' if lang == 'ms' else 'English'}",
               source="code", target_agent="Data & Reconciler",
               decision=("full: " + "; ".join(reasons)) if reasons else
               "quick: linked gauges below Alert and steady, no active warning, data fresh, simple question",
               details={"effort": effort, "reasons": reasons, "language": lang, "notes": notes,
                        "question_triggers": [k for k, _ in asked]})
    return {"effort": effort, "reasons": reasons, "language": lang, "notes": notes,
            "intent": next((k for k, _ in asked if k in ("evacuation", "cut_off")), "risk_check")}


def user_type(question):
    """'school' | 'family_far_away' | 'resident' | 'unknown' from the question's words."""
    text = " " + " ".join(_words(question)) + " "
    return next((kind for kind, words in USER_TYPES if any(f" {w} " in text for w in words)), "unknown")


def code_plan(question, resolution, r):
    """The plan, written by code on both paths (Husaini 22 Oct night: no AI planning - saves a 12-29 s call)."""
    from app.agents.coordinator import QUICK_SOURCES
    from app.agents.data_agent import SOURCES
    quick = r["effort"] == "quick"
    p = {"question_language": r["language"], "intent": r["intent"], "user_type": user_type(question),
         "effort": r["effort"], "sources": list(QUICK_SOURCES if quick else SOURCES), "place": resolution.place,
         "place_status": resolution.status, "place_message": resolution.message, "planned_by": "code",
         "reason": (f"{r['effort'].capitalize()} path decided by code: "
                    + (r["reasons"][0] if r["reasons"] else "nothing calls for more"))}
    trace.step(AGENT, "plan", input_summary=question,
               output_summary=(f"intent={p['intent']} user={p['user_type']} place={resolution.place['name']} "
                               f"effort={p['effort']} sources={','.join(p['sources'])} language={p['question_language']}"),
               source="code", target_agent="Data & Reconciler", decision=p["reason"], details={"plan": p})
    return p
