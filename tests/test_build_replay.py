"""B-70 tests: the replay anchors file and the reconstruction (straight line between verified readings only)."""
import importlib.util

import pytest

from app import trace

spec = importlib.util.spec_from_file_location("build_replay", trace.ROOT / "scripts" / "build_replay.py")
build_replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_replay)

KEYS = {"_DPMS0003", "_DTMH0008"}


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


def test_labels_use_the_approved_wording():
    rows = build_replay.reconstruct(build_replay.load_rows())
    late = next(r for r in rows if r["kind"] == "reconstructed" and r["observed_at"].strftime("%d %H") == "27 08")
    assert late["label"] == ("reconstructed between the verified JPS readings 8.41 m (26 Nov ~18:00) and "
                             "10.94 m (27 Nov 2024 19:30)")
    assert late["time_exact"] is False                 # one end is approximate -> the trend is approximate
    reported = next(r for r in rows if r["kind"] == "reported" and r["level_m"] == 10.94)
    assert reported["label"].startswith("reported JPS reading (Kosmo") and reported["time_exact"] is True
