"""B-71(c): unmapped JPS gauges become "discovered" in the World Model with a proposed fit; never used until a person
approves (then context only, never the verdict). SAMPLE_MODE finds one SYNTHETIC gauge, labelled."""
import json

import pytest

from app import discover, gazetteer, loop, trace
from app.agents import data_agent
from app.engines.world_model import WorldModel
from app.engines.world_model.stable_ids import external_id

SYN = external_id(data_agent.DISCOVERED, "jps", "_SYN0001")


@pytest.fixture
def sample(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    gazetteer.clear_cache()
    yield tmp_path
    gazetteer.clear_cache()


def test_the_data_agent_notices_the_unmapped_gauge_on_every_run(sample):
    world = WorldModel()
    r = loop.run("Pasir Mas banjir tak esok?", world=world, log_dir=sample, quiet=True)
    line = next(json.loads(x) for x in open(r["trace"], encoding="utf-8") if '"data.discover"' in x)
    assert line["agent_name"] == "Data & Reconciler" and line["output_summary"].startswith(
        "1 unmapped JPS gauge(s) noticed (1 new) - discovered, not used until a person approves")
    attrs = world.entity(SYN)["attrs"]
    assert attrs["status"] == "discovered" and attrs["name"].endswith("(SYNTHETIC)")
    assert attrs["fit"]["place"] == {"place_id": "pasir_mas", "name": "Pasir Mas"} and attrs["fit"]["river"] == "Sg. Kelantan"
    assert "Kg. Contoh" not in r["answer"]["text"]                              # never used while only discovered


def test_a_later_scan_never_resets_the_status(sample):
    world = WorldModel()
    trace.start_run("t", log_dir=sample, quiet=True)
    try:
        discover.scan(world)
        world.upsert_entity(data_agent.DISCOVERED, external_key={"system": "jps", "id": "_SYN0001"},
                            attrs={"status": "approved"}, source={"kind": "person", "at": "2026-10-24T00:00:00Z"})
        assert discover.scan(world) == ["Sg. Kelantan di Kg. Contoh (SYNTHETIC)"]
        assert world.entity(SYN)["attrs"]["status"] == "approved"
    finally:
        trace.end_run()


def test_list_shows_the_proposed_fit_and_the_rule(sample, capsys):
    assert discover.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "1 discovered gauge(s) - not used until a person approves; context only, never the verdict" in out
    assert "_SYN0001 | Sg. Kelantan di Kg. Contoh (SYNTHETIC) | discovered | river Sg. Kelantan, district Pasir Mas, " \
           "near Pasir Mas" in out
