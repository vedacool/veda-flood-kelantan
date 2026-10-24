"""Tests for B-09: app/gazetteer.py and scripts/seed_places.py.

Resolver tests replay the committed SAMPLE_MODE fixtures (data/fixtures/zetaris/), so they run offline and in CI.
"""
import importlib.util

import pytest

from app import gazetteer, trace

ROOT = trace.ROOT
spec = importlib.util.spec_from_file_location("seed_places", ROOT / "scripts" / "seed_places.py")
seed_places = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_places)

STATIONS = {"27133", "6021065_DPMS0001", "_DMCG0215", "5521044_DKKI0014", "_DPMS0003", "_DTMH0008", "_DKBR0007",
            "_DKBR0002", "_DTPT0002", "_DPMS0008",
            "5320038_DKKI0003", "5222052_DKKI0005", "_DMCG0001", "5020030_DGMG0016"}     # A7: the five new places


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """SAMPLE_MODE with no credentials: the gazetteer must work from the committed fixtures alone."""
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    trace.start_run("gazetteer test", log_dir=tmp_path, quiet=True)
    yield
    trace.end_run()
    gazetteer.clear_cache()


@pytest.mark.parametrize("raw, expected", [
    ("Kota Bharu", "kota bharu"), ("  BANDAR Kota-Bharu! ", "kota bharu"), ("Jajahan Tumpat", "tumpat"),
    ("near Pasir Mas", "pasir mas"), ("", ""), ("di", ""),
])
def test_normalize(raw, expected):
    assert gazetteer.normalize(raw) == expected


@pytest.mark.parametrize("query, place", [
    ("Kota Bharu", "kota_bharu"), ("kota baru", "kota_bharu"), ("KB", "kota_bharu"), ("Kotabharu", "kota_bharu"),
    ("psr mas", "pasir_mas"), ("Bandar Pasir Mas", "pasir_mas"), ("Rantau Panjng", "rantau_panjang"),
    ("Tumpat", "tumpat"), ("rumah saya di kota baru dekat pasar", "kota_bharu"),
])
def test_found(offline, query, place):
    r = gazetteer.resolve(query)
    assert r.status == "found" and r.place["place_id"] == place


@pytest.mark.parametrize("query, suggestion", [("Kota Baharu", "Kota Bharu"), ("Pasir Mos", "Pasir Mas"),
                                               ("Tumpad", "Tumpat")])
def test_did_you_mean_never_guesses(offline, query, suggestion):
    r = gazetteer.resolve(query)
    assert r.status == "did_you_mean" and r.place is None and suggestion in r.suggestions
    assert r.message.startswith("Did you mean")


@pytest.mark.parametrize("query, in_kelantan", [("Gua Musang", True), ("Jeli", True), ("Kuala Lumpur", False),
                                                ("Penang", False), ("", False)])
def test_not_covered(offline, query, in_kelantan):
    r = gazetteer.resolve(query)
    assert r.status == "not_covered" and r.place is None
    assert ("is in Kelantan" in r.message) is in_kelantan
    assert "Covered places: Kota Bharu, Pasir Mas, Rantau Panjang, Tumpat" in r.message


def test_committed_places_file_is_valid():
    assert seed_places.validate_places(seed_places.load_rows(), STATIONS) == []


def make_place(**overrides):
    row = {"place_id": "p1", "name": "Place One", "kind": "town", "district": "X", "lat": "6.0", "lon": "102.0",
           "coords_source": "test", "forecast_location_id": "Tn001", "controlling": "27133",
           "controlling_secondary": "", "sentinels": "", "aliases": "P One", "status": "tentative", "notes": ""}
    row.update(overrides)
    return row


@pytest.mark.parametrize("overrides, needle", [
    ({"kind": "city"}, "kind must be"), ({"lat": "3.1", "lon": "101.7"}, "outside Kelantan"),
    ({"controlling": ""}, "controlling gauge is required"), ({"controlling": "nope"}, "not in the stations table"),
    ({"sentinels": "27133"}, "listed twice"), ({"forecast_location_id": ""}, "forecast_location_id is empty"),
    ({"aliases": "!!!"}, "empty after normalising"),
])
def test_bad_place_rows(overrides, needle):
    problems = seed_places.validate_places([make_place(**overrides)], STATIONS)
    assert any(needle in p for p in problems), problems


def test_alias_cannot_belong_to_two_places():
    rows = [make_place(), make_place(place_id="p2", name="Place Two", aliases="P One")]
    assert any("belongs to both" in p for p in seed_places.validate_places(rows, STATIONS))


def test_nearest_rain_point():
    points = [(0, 5.0, 102.0), (1, 6.1, 102.2)]
    assert seed_places.nearest_rain_point(6.12, 102.24, points)[0] == 1


@pytest.mark.parametrize("question, known", [("Machang banjir tak?", "Machang"), ("is bachok flooding", "Bachok"),
                                             ("Air naik doh ko Jeli?", "Jeli")])
def test_known_place_inside_a_question_is_recognised(offline, question, known):
    r = gazetteer.resolve(question)
    assert r.status == "not_covered" and r.known == known


# -- A6 (24 Oct evening live test): "Pasir Pekan" got no nearest-town reply -------------------------------------------
@pytest.mark.parametrize("text, norm", [("is pasir pekan will get flooding?", "is pasir pekan will get flooding"),
                                        ("Pekan Tumpat banjir?", "tumpat banjir"), ("Bandar Kota Bharu", "kota bharu"),
                                        ("rumah di pekan tumpat", "rumah tumpat"), ("near Pasir Mas", "pasir mas")])
def test_prefix_words_are_dropped_only_in_front_of_a_name(text, norm):
    assert gazetteer.normalize(text) == norm


def test_a_place_named_by_a_jps_station_gets_its_nearest_covered_town(offline):
    res = gazetteer.resolve("Kuala Besar banjir tak?")
    assert res.status == "not_covered" and res.known == "Kuala Besar"
    assert res.nearest and res.nearest["name"] in ("Kota Bharu", "Tumpat") and res.nearest["km"] >= 5


def test_result_carries_nearest_covered(offline, tmp_path):
    from app import loop, main
    trace.end_run()
    r = loop.run("Is Kuala Besar safe?", quiet=True, log_dir=tmp_path, default_scene=True)
    out = main.result_json(r)
    assert out["nearest_covered"] and set(out["nearest_covered"]) == {"place", "km", "from_place"}
    assert out["nearest_covered"]["from_place"] == "Kuala Besar"
    r = loop.run("Is Tumpat safe?", quiet=True, log_dir=tmp_path, default_scene=True)
    assert main.result_json(r)["nearest_covered"] is None
    trace.start_run("gazetteer test", log_dir=tmp_path, quiet=True)
