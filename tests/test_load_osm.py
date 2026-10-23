"""B-73 tests for scripts/load_osm.py (offline): river names, possible-PPS categories, line crossing, and the rows
built from a small MADE-UP Overpass-shaped answer (invented names - not OpenStreetMap data)."""
import importlib.util

from app import trace

spec = importlib.util.spec_from_file_location("load_osm", trace.ROOT / "scripts" / "load_osm.py")
load_osm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(load_osm)

PLACE = {"place_id": "contoh", "name": "Contoh", "lat": "6.0", "lon": "102.0"}


def way(i, pts, **tags):
    return {"type": "way", "id": i, "tags": tags, "geometry": [{"lat": a, "lon": b} for a, b in pts]}


def node(i, lat, lon, **tags):
    return {"type": "node", "id": i, "lat": lat, "lon": lon, "tags": tags}


RIVER = way(1, [(5.99, 102.01), (6.01, 102.01)], waterway="river", name="Sungai Contoh")
STATIONS = [{"station_key": "_NEAR", "river": "Sg. Contoh", "lat": 6.0, "lon": 102.02},
            {"station_key": "_OTHER", "river": "Sg. Lain", "lat": 6.0, "lon": 102.011}]


def test_river_names_as_jps_writes_them():
    assert load_osm.river_name({"name": "แม่น้ำโกลก / Sungai Golok"}) == "Sg. Golok"
    assert load_osm.river_name({"name": "Sungai Kelantan"}) == "Sg. Kelantan"
    assert load_osm.river_name({"name": "Sg Lebir"}) == "Sg. Lebir"
    assert load_osm.river_name({"name": "x", "name:ms": "Sungai Galas"}) == "Sg. Galas"
    assert load_osm.river_name({"name": "แม่น้ำโกลก"}) is None and load_osm.river_name({}) is None


def test_possible_pps_categories():
    cat = load_osm.pps_category
    assert cat({"amenity": "school"}) == "school"
    assert cat({"amenity": "place_of_worship", "religion": "muslim", "name": "Masjid A"}) == "masjid"
    assert cat({"amenity": "place_of_worship", "religion": "muslim", "name": "Surau B"}) == "surau"
    assert cat({"amenity": "place_of_worship", "religion": "buddhist"}) is None
    assert cat({"amenity": "community_centre"}) == "community_hall"
    for name in ("BALAI RAYA Kg A", "Dewan Orang Ramai B", "dewan serbaguna C"):
        assert cat({"name": name}) == "community_hall"
    assert cat({"shop": "supermarket", "name": "Kedai"}) is None


def test_lines_cross():
    a = way(1, [(0, 0), (1, 1)])
    assert load_osm.crosses(a, way(2, [(0, 1), (1, 0)]))
    assert not load_osm.crosses(a, way(3, [(0, 0.5), (1, 1.5)]))          # parallel
    assert load_osm.crosses(a, way(4, [(1, 1), (2, 0)]))                    # touching end points
    assert not load_osm.crosses(way(5, [(0, 0)]), a)                        # one point = no segment


def test_km():
    assert load_osm.km(6, 102, 6, 102) == 0
    assert abs(load_osm.km(6, 102, 7, 102) - 111.2) < 1


def rows(*els, stations=STATIONS):
    return load_osm.features(PLACE, {"elements": [RIVER, *els]}, stations)


def test_named_possible_pps_within_the_radius():
    out = rows(node(10, 6.01, 102.0, amenity="school", name="SK Contoh"),
               node(11, 6.0, 102.0, amenity="school"),                                    # unnamed: skipped
               node(12, 6.2, 102.0, amenity="school", name="SK Jauh"),                    # ~22 km: skipped
               node(13, 6.005, 102.0, amenity="place_of_worship", religion="muslim", name="Masjid Contoh"),
               node(14, 6.006, 102.0, amenity="place_of_worship", religion="muslim", name="masjid contoh"))  # same name
    pps = [r for r in out if r["kind"] == "pps_candidate"]
    assert [(r["name"], r["km"], r["category"]) for r in pps] == [("SK Contoh", 1.1, "school"),     # schools first
                                                                  ("Masjid Contoh", 0.6, "masjid")]
    assert pps[1]["osm_ref"] == "node/13"


def test_at_most_top_pps():
    many = [node(100 + i, 6.0 + i / 1000, 102.0, amenity="school", name=f"SK {i}") for i in range(8)]
    pps = [r for r in rows(*many) if r["kind"] == "pps_candidate"]
    assert len(pps) == load_osm.TOP_PPS and pps[0]["name"] == "SK 0"


def test_bridge_over_a_named_river_gets_the_nearest_gauge_on_that_river():
    out = rows(way(20, [(6.0, 102.005), (6.0, 102.015)], highway="primary", bridge="yes", name="Jambatan Contoh"),
               way(21, [(6.0, 102.03), (6.0, 102.04)], highway="primary", bridge="yes", name="Jambatan Kering"),
               way(22, [(6.002, 102.005), (6.002, 102.015)], highway="track", bridge="yes"),       # no name / ref
               way(23, [(6.004, 102.005), (6.004, 102.015)], highway="trunk", bridge="yes", ref="FT 3"))
    b = [r for r in out if r["kind"] == "bridge"]
    assert [r["name"] for r in b] == ["Jambatan Contoh", "FT 3"]
    assert b[0]["river"] == "Sg. Contoh" and b[0]["station_key"] == "_NEAR" and b[0]["category"] == "primary"
    assert b[0]["gauge_km"] == 1.1


def test_no_gauge_when_the_river_has_none_close_enough():
    far = [{"station_key": "_FAR", "river": "Sg. Contoh", "lat": 6.5, "lon": 102.0}, STATIONS[1]]
    b = rows(way(20, [(6.0, 102.005), (6.0, 102.015)], highway="primary", bridge="yes", name="Jambatan Contoh"),
             stations=far)[0]
    assert b["station_key"] is None and b["gauge_km"] is None


def test_bridge_ending_short_of_the_river_line_still_spans_it():
    """An OSM bridge way often stops short of the river's centre line (e.g. split at the border): within 60 m counts."""
    short = way(30, [(6.0, 102.0098), (6.0, 102.0095)], highway="trunk", bridge="yes", name="Jambatan Sempadan")  # ~22 m
    far = way(31, [(6.0, 102.0090), (6.0, 102.0085)], highway="trunk", bridge="yes", name="Jambatan Jauh")      # ~110 m
    names = [r["name"] for r in rows(short, far) if r["kind"] == "bridge"]
    assert names == ["Jambatan Sempadan"]


def test_a_real_crossing_wins_over_a_nearby_river():
    stream = way(2, [(5.99, 102.0105), (6.01, 102.0105)], waterway="river", name="Sungai Anak")   # crossed by the bridge
    bridge = way(32, [(6.0, 102.0102), (6.0, 102.0108)], highway="primary", bridge="yes", name="Jambatan Anak")
    b = load_osm.features(PLACE, {"elements": [RIVER, stream, bridge]}, STATIONS)
    assert [(r["name"], r["river"]) for r in b if r["kind"] == "bridge"] == [("Jambatan Anak", "Sg. Anak")]


def test_prayer_rooms_are_not_possible_pps():
    for name in ("Musalla Contoh", "Surau Musolla A", "Mushola B", "Prayer Room C"):
        assert load_osm.pps_category({"amenity": "place_of_worship", "religion": "muslim", "name": name}) is None


def test_schools_and_halls_rank_before_masjid_and_surau():
    """Husaini 23 Oct: within the distance limit, schools and dewan / balai raya come before masjid / surau."""
    out = rows(node(40, 6.001, 102.0, amenity="place_of_worship", religion="muslim", name="Masjid Dekat"),
               node(41, 6.05, 102.0, amenity="school", name="SK Jauh Sikit"),
               node(42, 6.04, 102.0, name="Balai Raya Contoh"))
    assert [r["name"] for r in out if r["kind"] == "pps_candidate"] == ["Balai Raya Contoh", "SK Jauh Sikit",
                                                                       "Masjid Dekat"]
