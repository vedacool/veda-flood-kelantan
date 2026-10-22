"""Edge-case unit tests for World Model helpers (B-10). Offline only."""
import pytest

from app.engines.world_model.resolve import decide, levenshtein, name_similarity
from app.engines.world_model.stable_ids import (
    canonical_json,
    context_id_from_attrs,
    entity_id_from_name,
    external_id,
    fact_id,
    normalize_name,
    relationship_id,
)
from app.engines.world_model.store import EventStore


def test_normalize_name_zero_width_whitespace_empty_no_abbrev():
    # accents + NBSP (thin check; full case lives in conformance)
    assert normalize_name("Jose\u00a0Garcia") == normalize_name("Jose Garcia")
    zw = "Jo\u200bse\u200c \u200dGar\ufeffcia"
    assert normalize_name(zw) == "jose garcia"
    assert normalize_name("  Acme   Corp  ") == "acme corp"
    assert normalize_name("") == ""
    assert normalize_name("Acme Corp") != normalize_name("Acme Corporation")
    assert normalize_name("José  García") == "jose garcia"          # accents stripped (NFKD)
    assert normalize_name("Kg.  Kok Majid ") == "kg. kok majid"            # Malay names: only case/space change


def test_canonical_json_drops_none_sorts_nested_stable():
    assert canonical_json({"b": 1, "a": None, "c": 2}) == '{"b":1,"c":2}'
    nested = {"z": [{"b": 2, "a": 1}], "y": "caf\u00e9"}
    assert canonical_json(nested) == '{"y":"caf\u00e9","z":[{"a":1,"b":2}]}'
    a = canonical_json({"x": [1, {"k": "v"}], "y": "ok"})
    b = canonical_json({"y": "ok", "x": [1, {"k": "v"}]})
    assert a == b


def test_external_and_entity_ids():
    assert external_id("station", "jps", "_DKBR0007") == "station:jps:_DKBR0007"
    assert external_id("station", "jps", "5521044_DKKI0014") == "station:jps:5521044_DKKI0014"   # kept as given
    a = entity_id_from_name("person", "Jose Garcia")
    assert a == entity_id_from_name("person", "Jose Garcia")
    assert a.startswith("ent_") and len(a) == 4 + 16
    assert entity_id_from_name("person", "x") != entity_id_from_name("org", "x")


def test_fact_relationship_context_ids_stable_and_sensitive():
    f1 = fact_id("e1", "level_m", 1.2, "2026-01-01T00:00:00Z", "rss", None)
    f2 = fact_id("e1", "level_m", 1.2, "2026-01-01T00:00:00Z", "rss", "")
    assert f1 == f2 and f1.startswith("fact_")
    assert fact_id("e1", "level_m", 1.3, "2026-01-01T00:00:00Z", "rss") != f1

    r1 = relationship_id("a", "upstream_of", "b", None, None)
    r2 = relationship_id("a", "upstream_of", "b", "", "")
    assert r1 == r2 and r1.startswith("rel_")
    assert relationship_id("a", "upstream_of", "c") != r1

    c1 = context_id_from_attrs("basin", {"name": "Kelantan"}, None)
    c2 = context_id_from_attrs("basin", {"name": "Kelantan"}, "")
    assert c1 == c2 and c1.startswith("ctx_")
    assert context_id_from_attrs("basin", {"name": "Other"}) != c1


@pytest.mark.parametrize("a,b,dist", [
    ("kitten", "sitting", 3),
    ("abc", "abc", 0),
    ("", "abc", 3),
    ("abc", "", 3),
    ("", "", 0),
])
def test_levenshtein_known_distances(a, b, dist):
    assert levenshtein(a, b) == dist


def test_name_similarity_edges():
    assert name_similarity("Jose", "Jose") == 1.0
    assert name_similarity("", "") == 1.0
    assert name_similarity("", "a") < 1.0
    assert name_similarity("kitten", "sitting") == pytest.approx(1 - 3 / len("sitting"))


@pytest.mark.parametrize("sim,want", [
    (0.85, "auto-merge"),
    (0.849, "review"),
    (0.82, "review"),
    (0.819, "new"),
    (1.0, "auto-merge"),
    (0.0, "new"),
])
def test_decide_default_boundaries(sim, want):
    assert decide(sim) == want


def test_decide_custom_thresholds():
    assert decide(0.90, auto_merge_at=0.95, review_lower=0.80) == "review"
    assert decide(0.96, auto_merge_at=0.95, review_lower=0.80) == "auto-merge"
    assert decide(0.79, auto_merge_at=0.95, review_lower=0.80) == "new"


def test_resolve_alias_chain_and_cycle():
    store = EventStore()
    store.append("alias", {"alias_id": "A", "primary_id": "B"}, at="t1")
    store.append("alias", {"alias_id": "B", "primary_id": "C"}, at="t2")
    assert store.resolve_alias("A") == "C"
    assert store.resolve_alias("C") == "C"

    cyclic = EventStore()
    cyclic.append("alias", {"alias_id": "X", "primary_id": "Y"}, at="t1")
    cyclic.append("alias", {"alias_id": "Y", "primary_id": "X"}, at="t2")
    assert cyclic.resolve_alias("X") in ("X", "Y")  # stops; does not hang


def test_mark_stale_only_listed_unknown_ignored():
    store = EventStore()
    store.append("observation", {"external_id": "o1", "title": "a"}, at="t1")
    store.append("observation", {"external_id": "o2", "title": "b"}, at="t2")
    store.append("mark_stale", {"observation_ids": ["o1", "missing"]}, at="t3")
    assert store.state["observations"]["o1"].get("stale") is True
    assert store.state["observations"]["o2"].get("stale") is not True
    assert "missing" not in store.state["observations"]
