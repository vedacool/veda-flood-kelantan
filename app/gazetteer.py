"""Place gazetteer: turn what a user typed ("Kota Baru", "psr mas") into a covered VEDA place - or say clearly
that the place is not covered yet. Never guesses a location.

    from app import gazetteer
    r = gazetteer.resolve("Kota Baharu")
    r.status      # 'found' | 'did_you_mean' | 'not_covered'
    r.place       # {'place_id': 'kota_bharu', 'name': 'Kota Bharu', ...} when found
    r.message     # one plain sentence for the user

Reads places and aliases only through Zetaris (run_sql), so the same code replays offline in SAMPLE_MODE.
Matching is plain and explainable: normalise -> exact alias -> alias inside a longer sentence ->
close spelling (difflib, "Did you mean...?") -> known Kelantan place not covered yet -> not covered.
"""
import difflib
import math
import re
from dataclasses import dataclass, field

from app import trace
from app.adapters import zetaris

# Words that do not change which place is meant ("Bandar Kota Bharu", "Jajahan Tumpat", "near Pasir Mas").
FILLER = {"bandar", "jajahan", "daerah", "pekan", "town", "city", "district", "of", "di", "in", "at", "near",
          "dekat", "the", "kawasan", "area"}
CLOSE_MATCH = 0.75          # difflib ratio for "Did you mean ...?" (plain spelling similarity)
AGENT = "Gazetteer"

PLACES_SQL = ("SELECT a.alias_norm, p.place_id, p.name, p.district, p.kind, p.lat, p.lon "
              "FROM veda_pg.place_aliases a JOIN veda_pg.places p ON p.place_id = a.place_id")
# Where each Kelantan district roughly is: the average position of its JPS stations in data.gov.my /flood-warning.
# That feed's LEVELS are frozen since Feb 2024, but station positions do not go stale. Used only to suggest the
# nearest covered place for a known but uncovered district (B-21).
DISTRICT_CENTRES_SQL = ("SELECT s.district, AVG(s.latitude) AS lat, AVG(s.longitude) AS lon "
                        "FROM veda_wx.mygov_flood LATERAL VIEW explode(data) AS s GROUP BY s.district")
KNOWN_KELANTAN_SQL = "SELECT DISTINCT place FROM veda.forecast_kelantan"


@dataclass
class Resolution:
    """Result of resolve(): status, the place (when found), suggestions and a message for the user."""
    query: str
    status: str                      # found | did_you_mean | not_covered
    place: dict | None = None
    suggestions: list = field(default_factory=list)
    message: str = ""
    known: str | None = None         # a Kelantan name VEDA knows but does not cover yet
    nearest: dict | None = None      # {'name', 'km'} - the nearest covered place to `known`, when it can be placed
    covered: list = field(default_factory=list)


def normalize(text):
    """Lower-case, letters/digits only, filler words dropped, single spaces: 'Bandar Kota-Bharu!' -> 'kota bharu'."""
    words = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()
    return " ".join(w for w in words if w not in FILLER)


_cache = {}


def _load(agent):
    """Aliases (veda-pg) and known Kelantan place names, read once per process through Zetaris.
    The known names come from the MetMalaysia forecast list - a data.gov.my REST table that Zetaris may call live.
    They only shape the reply for an UNCOVERED name, so a failure there (e.g. data.gov.my HTTP 429, found live 23 Oct)
    never blocks finding a covered place: it is traced as "not checked" and tried again on the next call."""
    if "aliases" not in _cache:
        rows = zetaris.run_sql(PLACES_SQL, agent=agent, purpose="gazetteer: covered places and aliases").records
        _cache["aliases"] = {r["alias_norm"]: r for r in rows}
    if "known" not in _cache:
        try:
            known = zetaris.run_sql(KNOWN_KELANTAN_SQL, agent=agent,
                                    purpose="gazetteer: known Kelantan place names").rows
            _cache["known"] = {normalize(r[0]): r[0] for r in known if r[0]}
        except zetaris.ZetarisError as e:
            trace.step(agent, "gazetteer.known", output_summary=f"not checked: {e.kind}", status="fallback",
                       source="data.gov.my", decision="Known Kelantan names (MetMalaysia list, data.gov.my) could not "
                       "be read -> covered places are still found; an uncovered name gets the plain 'not covered' "
                       "reply; tried again next time")
            return _cache["aliases"], {}
    return _cache["aliases"], _cache["known"]


def clear_cache():
    """Forget loaded data (tests, or after re-seeding places)."""
    _cache.clear()


def _place(row):
    return {"place_id": row["place_id"], "name": row["name"], "district": row["district"], "kind": row["kind"]}


def _covered_list(aliases):
    return ", ".join(sorted({r["name"] for r in aliases.values()}))


def _km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def nearest_covered(name, aliases, agent=AGENT):
    """{'name', 'km'} of the covered place nearest to a known Kelantan district, or None if it cannot be placed."""
    if "centres" not in _cache:
        try:
            rows = zetaris.run_sql(DISTRICT_CENTRES_SQL, agent=agent, purpose="gazetteer: district positions").records
        except zetaris.ZetarisError:
            rows = []
        _cache["centres"] = {normalize(r["district"]): r for r in rows if r.get("district") and r.get("lat")}
    centre = _cache["centres"].get(normalize(name))
    if not centre:
        return None
    places = {r["place_id"]: r for r in aliases.values() if r.get("lat") is not None}
    best = min(places.values(), key=lambda r: _km(centre["lat"], centre["lon"], r["lat"], r["lon"]), default=None)
    if best is None:
        return None
    km = _km(centre["lat"], centre["lon"], best["lat"], best["lon"])
    return {"name": best["name"], "km": max(5, int(round(km / 5)) * 5)}


def resolve(text, agent=AGENT):
    """Resolve one place name. Always returns a Resolution (never raises for an unknown place); traced."""
    aliases, known = _load(agent)
    q = normalize(text)
    res = None
    if q in aliases:
        res = Resolution(text, "found", _place(aliases[q]), message=f"Using {aliases[q]['name']}.")
    if res is None and q:
        # alias inside a longer phrase ("rumah saya di kota baru dekat pasar") - longest alias wins
        hits = [a for a in aliases if re.search(rf"\b{re.escape(a)}\b", q)]
        if hits:
            best = aliases[max(hits, key=len)]
            res = Resolution(text, "found", _place(best), message=f"Using {best['name']}.")
    if res is None and q:
        close = difflib.get_close_matches(q, list(aliases), n=5, cutoff=CLOSE_MATCH)
        names = list(dict.fromkeys(aliases[c]["name"] for c in close))[:3]
        if names:
            res = Resolution(text, "did_you_mean", suggestions=names,
                             message="Did you mean " + " or ".join(names) + "?",
                             covered=sorted({r["name"] for r in aliases.values()}))
    if res is None:
        key = q if q in known else next(iter(difflib.get_close_matches(q, list(known), n=1, cutoff=0.85)), None)
        if key is None and q:       # a known name inside a longer question ("machang banjir tak") - longest wins
            inside = [k for k in known if k and re.search(rf"\b{re.escape(k)}\b", q)]
            key = max(inside, key=len) if inside else None
        where = f"{known[key]} is in Kelantan but" if key else f"'{text.strip()}' is"
        near = nearest_covered(known[key], aliases, agent) if key else None
        res = Resolution(text, "not_covered",
                         message=f"{where} not covered by VEDA yet. "
                                 + (f"Nearest covered place: {near['name']} (about {near['km']} km away). " if near else "")
                                 + f"Covered places: {_covered_list(aliases)}.",
                         known=known[key] if key else None, nearest=near,
                         covered=sorted({r["name"] for r in aliases.values()}))
    trace.step(agent, "gazetteer.resolve", input_summary=text, output_summary=f"{res.status}: {res.message}",
               details={"normalized": q, "place_id": res.place["place_id"] if res.place else None,
                        "suggestions": res.suggestions})
    return res
