"""World Model conformance - Python port of the Meterless conformance cases.

Source: github.com/Meterless/Meterless, engines/world-model/conformance/runner.ts (Apache-2.0). The official runner
loads TypeScript only, so each check is ported one-for-one: same ids, same inputs, same thresholds, same assertions.
Field names follow Python style (external_id, external_key, valid_from); behaviour is unchanged.
Run:  python -m pytest tests/conformance -v --junitxml=logs/conformance.xml
"""
import pytest

from app.engines.world_model import ProvenanceError, WorldModel, decide, entity_id_from_name, normalize_name

OBSERVATIONS = [
    {"external_id": "a1", "title": "Fed holds rates", "at": "2026-05-17T14:00:00.000Z",
     "source": {"kind": "rss", "at": "2026-05-17T14:00:00.000Z"}, "entities": [{"type": "person", "name": "Jerome Powell"}]},
    {"external_id": "a2", "title": "Powell signals patience", "at": "2026-05-17T16:30:00.000Z",
     "source": {"kind": "rss", "at": "2026-05-17T16:30:00.000Z"}, "entities": [{"type": "person", "name": "Jerome Powell"}]},
]


def test_sid_001_diacritics_and_nbsp_normalize_identically():
    """stable ids: diacritics and NBSP normalize identically (NFKD + strip marks)"""
    assert normalize_name("José  García") == normalize_name("Jose Garcia")
    assert entity_id_from_name("person", "José García") == entity_id_from_name("person", "jose garcia")


def test_sid_002_distinct_names_stay_distinct():
    """stable ids: distinct names stay distinct (no over-normalization)"""
    assert entity_id_from_name("org", "Acme Corp") != entity_id_from_name("org", "Acme Corporation")
    assert entity_id_from_name("person", "x") != entity_id_from_name("org", "x")      # type participates in the key


def test_band_001_merge_bands_at_the_boundaries():
    """merge bands at the boundaries: 0.85 auto, 0.84 review, 0.82 review, 0.81 new"""
    assert decide(0.85) == "auto-merge"
    assert decide(0.84) == "review"
    assert decide(0.82) == "review"
    assert decide(0.81) == "new"


def test_prov_001_writes_without_provenance_are_rejected():
    """writes without provenance are rejected"""
    world = WorldModel(storage="memory", namespace="conf")
    with pytest.raises(ProvenanceError):
        world.upsert_entity("person", name="No Provenance", source=None)


def test_idem_001_same_batch_twice_produces_an_empty_diff():
    """ingest idempotency: same batch twice produces an empty diff"""
    world = WorldModel(storage="memory", namespace="conf")
    world.ingest(OBSERVATIONS)
    shape1 = world.state_shape_canonical()
    second = world.ingest(OBSERVATIONS)
    assert second["changed"] is False
    assert world.state_shape_canonical() == shape1


def test_idem_002_a_mutated_batch_changes_the_shape():
    """the idempotency check can fail: a mutated batch changes the shape"""
    world = WorldModel(storage="memory", namespace="conf")
    world.ingest(OBSERVATIONS)
    shape1 = world.state_shape_canonical()
    mutated = [{**OBSERVATIONS[0], "title": OBSERVATIONS[0]["title"] + " (edited)"}, OBSERVATIONS[1]]
    run = world.ingest(mutated)
    assert run["changed"] is True
    assert world.state_shape_canonical() != shape1


def test_bitemp_001_superseding_edge_closes_the_old_one():
    """bitemporal edges: a superseding edge closes the old one; point-in-time queries respect validity"""
    world = WorldModel(storage="memory", namespace="conf")

    def at(s):
        return {"kind": "manual", "at": s}

    world.upsert_entity("player", external_key={"system": "g", "id": "p1"}, attrs={}, source=at("2087-01-01T00:00:00.000Z"))
    world.upsert_entity("team", external_key={"system": "g", "id": "a"}, attrs={}, source=at("2087-01-01T00:00:00.000Z"))
    world.upsert_entity("team", external_key={"system": "g", "id": "b"}, attrs={}, source=at("2088-03-01T00:00:00.000Z"))
    world.relate("player:g:p1", "plays-for", "team:g:a", valid_from="2087-01-01T00:00:00.000Z",
                 source=at("2087-01-01T00:00:00.000Z"))
    world.relate("player:g:p1", "plays-for", "team:g:b", valid_from="2088-03-01T00:00:00.000Z",
                 source=at("2088-03-01T00:00:00.000Z"))
    now = world.neighbors_of("player:g:p1", via="plays-for")
    assert [e["id"] for e in now] == ["team:g:b"]
    then = world.neighbors_of("player:g:p1", via="plays-for", at="2087-06-01T00:00:00.000Z")
    assert [e["id"] for e in then] == ["team:g:a"]


def test_audit_001_every_mutation_writes_an_audit_entry_in_order():
    """every mutation writes an audit entry in order"""
    world = WorldModel(storage="memory", namespace="conf")
    world.upsert_entity("x", name="Audit One", source={"kind": "manual", "at": "2026-01-01T00:00:00.000Z"})
    world.upsert_entity("x", name="Audit Two", source={"kind": "manual", "at": "2026-01-02T00:00:00.000Z"})
    audit = world.audit()
    assert len(audit) >= 2
    assert all(audit[i]["seq"] > audit[i - 1]["seq"] for i in range(1, len(audit)))
