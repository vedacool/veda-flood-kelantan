"""B-70 tests: the replay anchors file and the reconstruction (straight line between verified readings only)."""
import importlib.util

import pytest

from app import trace

spec = importlib.util.spec_from_file_location("build_replay", trace.ROOT / "scripts" / "build_replay.py")
build_replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_replay)

KEYS = {"_DPMS0003", "_DTMH0008", "_DPMS0008", "5521044_DKKI0014", "_DKBR0007"}


def anchor(**kw):
    row = {"scenario": "nov2024", "station_key": "_DPMS0003", "observed_at_myt": "2024-11-26 18:00",
           "time_exact": "false", "level_m": "8.41", "source_name": "Bernama", "source_url": "https://bernama.com/x",
           "quote": "has risen to 8.41 metres", "note": ""}
    return {**row, **kw}


def test_committed_anchors_are_valid_and_cited():
    rows = build_replay.load_rows()
    assert build_replay.validate(rows, KEYS) == []
    assert all(r["source_url"].startswith("https://") and r["quote"] for r in rows)
    assert {r["level_m"] for r in rows if r["station_key"] == "_DPMS0003"} == {"8.27", "8.41", "10.94"}


def test_every_level_is_in_its_own_quote_and_its_gauge_is_mapped():
    """No invented or rounded numbers: the level in each row is written in the quoted sentence."""
    import csv
    mapped = {r["station_key"] for r in csv.DictReader((trace.ROOT / "data" / "stations_mapping.csv")
                                                       .open(encoding="utf-8")) if r["record_type"] == "gauge"}
    for r in build_replay.load_rows():
        assert r["level_m"] in r["quote"], r
        assert r["station_key"] in mapped, r


def test_sungai_kelantan_readings_cited_24_oct():
    """Task (c), 24 Oct: news readings citing JPS for the Sg. Kelantan side, quotes of at most 15 words."""
    added = {(r["station_key"], r["observed_at_myt"]): r for r in build_replay.load_rows()
             if r["station_key"] in ("_DPMS0008", "5521044_DKKI0014", "_DKBR0007")}
    assert {k: (r["level_m"], r["time_exact"]) for k, r in added.items()} == {
        ("_DPMS0008", "2024-11-26 08:00"): ("2.03", "false"),                # Harian Metro: no time stated
        ("5521044_DKKI0014", "2024-11-29 08:00"): ("25.17", "true"),         # Bernama: "as of 8 am"
        ("_DKBR0007", "2024-11-29 08:00"): ("5.58", "true"),
        ("_DKBR0007", "2024-11-29 21:00"): ("5.53", "true")}                 # Bernama: "as of 9 pm today"
    for r in added.values():
        assert len(r["quote"].replace("...", " ").split()) <= 15, r["quote"]
        assert "JPS" in r["source_name"] or "DID" in r["source_name"]


@pytest.mark.parametrize("bad, problem", [
    ({"station_key": "_NOPE"}, "unknown station_key"),
    ({"observed_at_myt": "26/11/2024 18:00"}, "observed_at_myt"),
    ({"time_exact": "maybe"}, "time_exact"),
    ({"level_m": "8,41"}, "not a number"),
    ({"source_url": "http://bernama.com/x"}, "https"),
    ({"quote": ""}, "quoted sentence"),
])
def test_bad_anchor_is_refused(bad, problem):
    assert any(problem in p for p in build_replay.validate([anchor(**bad)], KEYS))


def test_out_of_order_readings_are_refused():
    rows = [anchor(observed_at_myt="2024-11-27 19:30"), anchor(observed_at_myt="2024-11-26 18:00")]
    assert any("time order" in p for p in build_replay.validate(rows, KEYS))


def test_reconstruction_is_a_straight_line_between_readings_only():
    rows = build_replay.reconstruct(build_replay.load_rows())
    rp = [r for r in rows if r["station_key"] == "_DPMS0003"]
    assert rp[0]["observed_at"].strftime("%d %H:%M") == "26 08:00" and rp[0]["kind"] == "reported"
    assert rp[-1]["observed_at"].strftime("%d %H:%M") == "27 19:30" and rp[-1]["level_m"] == 10.94
    rec = [r for r in rp if r["kind"] == "reconstructed"]
    assert len(rec) == 9 + 25                         # 09:00-17:00 on 26 Nov, then 19:00 26 Nov - 19:00 27 Nov
    assert all(8.27 < r["level_m"] < 10.94 for r in rec)
    noon = next(r for r in rec if r["observed_at"].strftime("%d %H:%M") == "26 13:00")
    assert noon["level_m"] == round(8.27 + (8.41 - 8.27) * 5 / 10, 2)
    jenob = [r for r in rows if r["station_key"] == "_DTMH0008"]
    assert [r["kind"] for r in jenob] == ["reported"]                    # one reading -> nothing reconstructed
    for single in ("_DPMS0008", "5521044_DKKI0014"):
        assert [r["kind"] for r in rows if r["station_key"] == single] == ["reported"]
    kb = [r for r in rows if r["station_key"] == "_DKBR0007"]
    assert [r["observed_at"].strftime("%d %H:%M") for r in kb if r["kind"] == "reported"] == ["29 08:00", "29 21:00"]
    assert len(kb) == 2 + 12 and all(5.53 <= r["level_m"] <= 5.58 for r in kb)    # 09:00-20:00 between them only


def test_labels_use_the_approved_wording():
    rows = build_replay.reconstruct(build_replay.load_rows())
    late = next(r for r in rows if r["kind"] == "reconstructed" and r["observed_at"].strftime("%d %H") == "27 08")
    assert late["label"] == ("reconstructed between the verified JPS readings 8.41 m (26 Nov ~18:00) and "
                             "10.94 m (27 Nov 2024 19:30)")
    assert late["time_exact"] is False                 # one end is approximate -> the trend is approximate
    reported = next(r for r in rows if r["kind"] == "reported" and r["level_m"] == 10.94)
    assert reported["label"].startswith("reported JPS reading (Kosmo") and reported["time_exact"] is True
