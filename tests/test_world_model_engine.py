"""VEDA-side tests for the World Model engine (beyond the official conformance port in tests/conformance)."""
import importlib.util
import json

import pytest

from app import trace
from app.engines.world_model import ProvenanceError, WorldModel

SRC = {"kind": "zetaris", "at": "2026-10-22T08:45:00Z", "query_hash": "abc123", "agent": "Data", "run_id": "r1"}

spec = importlib.util.spec_from_file_location("wm_idem", trace.ROOT / "scripts" / "wm_idempotency_check.py")
wm_idem = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wm_idem)


def test_sqlite_log_rebuilds_the_same_world(tmp_path):
    db = tmp_path / "world.sqlite"
    w1 = WorldModel(storage=db, namespace="veda")
    w1.upsert_entity("station", external_key={"system": "jps", "id": "_DPMS0003"}, attrs={"name": "Rantau Panjang"},
                     source=SRC)
    w1.assert_fact("station:jps:_DPMS0003", "water_level_m", 7.26, confidence=0.9, source=SRC)
    shape = w1.state_shape_canonical()
    w1.close()
    w2 = WorldModel(storage=db, namespace="veda")         # canonical reconstruction from the event log
    assert w2.state_shape_canonical() == shape
    assert w2.facts_about("station:jps:_DPMS0003", "water_level_m")[0]["value"] == 7.26
    w2.close()


def test_facts_keep_provenance_and_most_recent_wins():
    w = WorldModel()
    old = w.assert_fact("station:jps:X", "water_level_m", 7.0, source={**SRC, "at": "2026-10-22T08:00:00Z"})
    new = w.assert_fact("station:jps:X", "water_level_m", 7.3, source={**SRC, "at": "2026-10-22T08:45:00Z"})
    late = w.assert_fact("station:jps:X", "water_level_m", 6.9, source={**SRC, "at": "2026-10-22T07:00:00Z"})
    current = w.facts_about("station:jps:X", "water_level_m")
    assert [f["value"] for f in current] == [7.3]
    assert current[0]["source"]["query_hash"] == "abc123" and current[0]["source"]["agent"] == "Data"
    everything = {f["id"]: f for f in w.facts_about("station:jps:X", include_superseded=True)}
    assert everything[old["id"]]["superseded_by"] == new["id"]
    assert everything[late["id"]]["superseded_by"] == new["id"]       # an older reading arriving late never wins


def test_identical_fact_twice_is_a_no_op():
    w = WorldModel()
    a = w.assert_fact("station:jps:X", "band", "alert", source=SRC)
    events = len(w.store.events)
    b = w.assert_fact("station:jps:X", "band", "alert", source=SRC)
    assert a["id"] == b["id"] and len(w.store.events) == events


def test_facts_and_relations_need_provenance():
    w = WorldModel()
    with pytest.raises(ProvenanceError):
        w.assert_fact("station:jps:X", "band", "alert", source={"kind": "zetaris"})       # no 'at'
    with pytest.raises(ProvenanceError):
        w.relate("a", "upstream_of", "b", source=None)


def test_context_scoped_edges_do_not_close_each_other():
    # Kuala Krai is a sentinel for BOTH Kota Bharu and Pasir Mas: scoped by context, neither closes the other
    w = WorldModel()
    for key in ("5521044_DKKI0014",):
        w.upsert_entity("station", external_key={"system": "jps", "id": key}, source=SRC)
    for pid in ("kota_bharu", "pasir_mas"):
        w.upsert_entity("place", external_key={"system": "veda", "id": pid}, source=SRC)
        w.relate("station:jps:5521044_DKKI0014", "sentinel_for", f"place:veda:{pid}", context=pid, source=SRC)
    assert [e["id"] for e in w.neighbors_of("station:jps:5521044_DKKI0014", via="sentinel_for")] == \
        ["place:veda:kota_bharu", "place:veda:pasir_mas"]


def test_near_duplicate_names_auto_merge_or_queue():
    w = WorldModel()
    w.upsert_entity("river", name="Sungai Kelantan", source=SRC)
    merged = w.upsert_entity("river", name="Sungai Kelantann", source=SRC)       # 1 typo in 16 -> 0.94 -> merge
    assert merged["name"] in ("Sungai Kelantan", "Sungai Kelantann")
    assert len([e for e in w.store.state["entities"].values() if e["type"] == "river"]) == 1


def test_audit_mirrors_to_jsonl(tmp_path):
    log = tmp_path / "worldmodel-audit-r1.jsonl"
    w = WorldModel(audit_jsonl=log)
    w.upsert_entity("x", name="One", source=SRC)
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert lines and lines[0]["kind"] == "upsert_entity" and lines[0]["run_id"] == "r1"


def test_manifest_lists_live_and_dormant_services():
    m = WorldModel().manifest()
    assert m["services"]["WorldStoreService"].startswith("live")
    assert m["services"]["EnrichmentService"].startswith("dormant")


def test_idempotency_script_passes_and_can_fail():
    assert wm_idem.main(["x"]) == 0
    assert wm_idem.main(["x", "--mutate"]) == 0          # mutate proves the diff is non-empty
