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
import re
from dataclasses import dataclass, field

from app import trace
from app.adapters import zetaris

# Words that do not change which place is meant ("Bandar Kota Bharu", "Jajahan Tumpat", "near Pasir Mas").
FILLER = {"bandar", "jajahan", "daerah", "pekan", "town", "city", "district", "of", "di", "in", "at", "near",
          "dekat", "the", "kawasan", "area"}
CLOSE_MATCH = 0.75          # difflib ratio for "Did you mean ...?" (plain spelling similarity)
AGENT = "Gazetteer"

PLACES_SQL = ("SELECT a.alias_norm, p.place_id, p.name, p.district, p.kind "
              "FROM veda_pg.place_aliases a JOIN veda_pg.places p ON p.place_id = a.place_id")
KNOWN_KELANTAN_SQL = "SELECT DISTINCT place FROM veda.forecast_kelantan"


@dataclass
class Resolution:
    """Result of resolve(): status, the place (when found), suggestions and a message for the user."""
    query: str
    status: str                      # found | did_you_mean | not_covered
    place: dict | None = None
    suggestions: list = field(default_factory=list)
    message: str = ""


def normalize(text):
    """Lower-case, letters/digits only, filler words dropped, single spaces: 'Bandar Kota-Bharu!' -> 'kota bharu'."""
    words = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()
    return " ".join(w for w in words if w not in FILLER)


_cache = {}


def _load(agent):
    """Aliases and known Kelantan place names, read once per process through Zetaris."""
    if "aliases" not in _cache:
        rows = zetaris.run_sql(PLACES_SQL, agent=agent, purpose="gazetteer: covered places and aliases").records
        _cache["aliases"] = {r["alias_norm"]: r for r in rows}
        known = zetaris.run_sql(KNOWN_KELANTAN_SQL, agent=agent, purpose="gazetteer: known Kelantan place names").rows
        _cache["known"] = {normalize(r[0]): r[0] for r in known if r[0]}
    return _cache["aliases"], _cache["known"]


def clear_cache():
    """Forget loaded data (tests, or after re-seeding places)."""
    _cache.clear()


def _place(row):
    return {"place_id": row["place_id"], "name": row["name"], "district": row["district"], "kind": row["kind"]}


def _covered_list(aliases):
    return ", ".join(sorted({r["name"] for r in aliases.values()}))


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
                             message="Did you mean " + " or ".join(names) + "?")
    if res is None:
        key = q if q in known else next(iter(difflib.get_close_matches(q, list(known), n=1, cutoff=0.85)), None)
        where = f"{known[key]} is in Kelantan but" if key else f"'{text.strip()}' is"
        res = Resolution(text, "not_covered",
                         message=f"{where} not covered by VEDA yet. Covered places: {_covered_list(aliases)}.")
    trace.step(agent, "gazetteer.resolve", input_summary=text, output_summary=f"{res.status}: {res.message}",
               details={"normalized": q, "place_id": res.place["place_id"] if res.place else None,
                        "suggestions": res.suggestions})
    return res
