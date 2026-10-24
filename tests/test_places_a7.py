"""A7 (Cowork 24 Oct evening): five more places in LIVE mode - each with coordinates (and their source), its own
Open-Meteo point (the nearest rain point, set by scripts/seed_places.py), a MetMalaysia forecast id, gauges from the
curated network, status 'tentative - needs Dr Ariff'. Offline scenes keep the four towns (Home stays 4 buttons)."""
import csv
import sys
from pathlib import Path

from app import gazetteer, trace

ROOT = trace.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import seed_places  # noqa: E402

NEW = {"kuala_krai": ("Kuala Krai", "5521044_DKKI0014", "Tn045"), "tanah_merah": ("Tanah Merah", "_DMCG0215", "Tn038"),
       "dabong": ("Dabong", "5320038_DKKI0003", "Ds034"), "wakaf_bharu": ("Wakaf Bharu", "_DKBR0007", "Ds022"),
       "pasir_pekan": ("Pasir Pekan", "_DKBR0007", "Ds022")}


def stations():
    with (ROOT / "data" / "stations_mapping.csv").open(encoding="utf-8") as f:
        return {r["station_key"]: r for r in csv.DictReader(f) if r["record_type"] == "gauge"}


def test_five_new_places_are_complete_and_tentative():
    rows = {r["place_id"]: r for r in seed_places.load_rows()}
    assert set(NEW) <= set(rows) and len(rows) == 9
    for pid, (name, controlling, forecast) in NEW.items():
        r = rows[pid]
        assert r["name"] == name and r["controlling"] == controlling and r["forecast_location_id"] == forecast
        assert r["status"] == "tentative - needs Dr Ariff" and r["needs_review_by"] == "Dr Ariff"
        assert r["coords_source"] and 4.5 <= float(r["lat"]) <= 6.4 and 101.3 <= float(r["lon"]) <= 102.8
    assert rows["pasir_pekan"]["controlling_secondary"] == "_DTPT0002"          # Kok Majid (asked for as backup)
    assert seed_places.validate_places(list(rows.values()), set(stations())) == []


def test_each_new_place_gets_its_own_rain_point():
    with (ROOT / "data" / "rain_points.csv").open(encoding="utf-8") as f:
        pts = [(r["point_key"], float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)]
    rows = {r["place_id"]: r for r in seed_places.load_rows()}
    got = {pid: seed_places.nearest_rain_point(float(rows[pid]["lat"]), float(rows[pid]["lon"]), pts)[0] for pid in NEW}
    assert got == {"kuala_krai": "kuala_krai", "tanah_merah": "kusial", "dabong": "dabong",
                   "wakaf_bharu": "tambatan_diraja", "pasir_pekan": "tambatan_diraja"}


def test_aliases_normalize_to_their_names():
    rows = {r["place_id"]: r for r in seed_places.load_rows()}
    assert gazetteer.normalize("Pasir Pekan") == "pasir pekan"                   # A6: not "pasir"
    for pid in NEW:
        for alias in seed_places.split(rows[pid]["aliases"]):
            assert gazetteer.normalize(alias), alias


def test_home_still_has_four_town_buttons():
    page = (ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'const TOWNS = ["Rantau Panjang", "Pasir Mas", "Kota Bharu", "Tumpat"];' in page
