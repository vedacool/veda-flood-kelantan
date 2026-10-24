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


# -- part 2: a person approves; then context on the card only ---------------------------------------------------
def _world_with_discovered(sample):
    world = WorldModel()
    trace.start_run("t", log_dir=sample, quiet=True)
    discover.scan(world)
    return world


def test_approve_is_refused_in_sample_mode(sample, capsys):
    assert discover.main(["approve", "_SYN0001", "--place", "pasir_mas", "--by", "Husaini"]) == 1
    assert "SAMPLE_MODE" in capsys.readouterr().out


def test_approve_checks_the_gauge_the_place_and_the_person(sample, monkeypatch):
    world = _world_with_discovered(sample)
    try:
        assert discover.approve(world, "_NOPE", "pasir_mas", "Husaini") == (
            False, "_NOPE is not a discovered gauge - run: python -m app.discover list")
        assert not discover.approve(world, "_SYN0001", "pasir_mas", "  ")[0]
        assert discover.approve(world, "_SYN0001", "gua_musang", "Husaini")[1].startswith("gua_musang is not a covered")
        ok, msg = discover.approve(world, "_SYN0001", "pasir_mas", "Husaini")
        assert ok and msg.endswith("(context only, not the verdict)")
        a = world.entity(SYN)["attrs"]
        assert (a["status"], a["approved_by"], a["approved_place"]) == ("approved", "Husaini", "pasir_mas")
    finally:
        trace.end_run()


def test_an_approved_gauge_is_context_on_the_card_and_never_changes_the_verdict(sample):
    from app import card
    from app.agents import forecast_agent
    from app.engines.world_model.veda_ingest import station_id
    world = _world_with_discovered(sample)
    try:
        plan = {"intent": "risk_check", "effort": "full", "place": gazetteer.resolve("Pasir Mas").place,
                "sources": ["jps_levels", "open_meteo"]}
        before = data_agent.gather(plan, world)
        verdict_before = forecast_agent.forecast(plan, before, world)["verdict"]
        discover.approve(world, "_SYN0001", "pasir_mas", "Husaini")
        src = {"kind": "zetaris", "at": before["clock"], "agent": "test", "health": {"ok": True}}
        world.assert_fact(station_id("_SYN0001"), "water_level_m", 9.9, confidence=0.9, source=src)
        world.assert_fact(station_id("_SYN0001"), "band", "danger", confidence=0.9, source=src)
        ev = data_agent.gather(plan, world)
        assert ev["discovered_context"] == [{"name": "Sg. Kelantan di Kg. Contoh (SYNTHETIC)", "band": "danger",
                                             "age_minutes": 0, "approved_by": "Husaini"}]
        names = [g["name"] for g in ev["context"]["gauges"] + ev["context"]["sentinels"]]
        assert "Sg. Kelantan di Kg. Contoh (SYNTHETIC)" not in names           # never one of the Forecast's gauges
        fc = forecast_agent.forecast(plan, ev, world)
        assert fc["verdict"] == verdict_before                                  # a Danger reading changes nothing
        text = card.render(card.build(plan, ev, fc), "en")
        assert ("Gauge found by VEDA: Sg. Kelantan di Kg. Contoh (SYNTHETIC) (approved by Husaini; for information only - "
                "it does not change the result): JPS level Danger.") in text
    finally:
        trace.end_run()
