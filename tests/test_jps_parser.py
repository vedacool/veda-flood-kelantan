"""Edge-case tests for app/ingest/jps.py parse helpers (B-06). Offline only."""
from datetime import datetime, timezone

import pytest

from app.ingest import jps

COLS = (
    "No", "Station ID", "Station Name", "District", "Main Basin (mm)",
    "Sub River Basin (mm)", "Last Update", "wl", "Normal", "Alert", "Warning", "Danger",
)


def make_page(rows):
    """Minimal JPS-like HTML. Each row is a dict; optional station_key / no_link / href_extra."""
    parts = ["<table><tbody>"]
    for i, row in enumerate(rows, 1):
        d = {
            "No": str(i), "Station ID": "0730001WL", "Station Name": "Sg. Test (F1)",
            "District": "Kota Bharu", "Main Basin (mm)": "Sungai Kelantan",
            "Sub River Basin (mm)": "Sg. Kelantan", "Last Update": "22/10/2026 10:30",
            "wl": "7.47", "Normal": "5.0", "Alert": "6.0", "Warning": "7.0", "Danger": "8.0",
        }
        d.update(row)
        key = d.pop("station_key", f"_ST{i}")
        no_link = d.pop("no_link", False)
        href_extra = d.pop("href_extra", "")
        cells = []
        for col in COLS:
            val = d.get(col, "")
            if col == "wl" and not no_link:
                href = f"/index.php/wl-graph/?stationid={key}{href_extra}"
                cells.append(f"<td data-th='{col}'><a href='{href}'>{val}</a></td>")
            else:
                cells.append(f"<td data-th='{col}'>{val}</td>")
        parts.append("<tr class='item'>" + "".join(cells) + "</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def test_normalize_name_strips_tag_and_punctuation():
    assert jps.normalize_name("Sg. Kelantan di Tambatan D'Raja (F1)") == "sg kelantan di tambatan d raja"
    assert jps.normalize_name("  Sg.  Test  (F2)  ") == "sg test"
    assert all(c.isalnum() or c == " " for c in jps.normalize_name("Sg. A (F2)!"))


@pytest.mark.parametrize("raw, expected", [
    ("22/10/2026 00:15", datetime(2026, 10, 21, 16, 15, tzinfo=timezone.utc)),
    ("31/02/2026 10:00", None),
    ("22/10/2026 24:00", None),
    ("22/10/2026 10:30:00", None),
    ("-", None),
    ("", None),
])
def test_to_utc_edge_cases(raw, expected):
    assert jps.to_utc(raw) == expected


def test_parse_ignores_header_row_without_data_th():
    header = "<tr><td>No</td><td>Station ID</td><td>Station Name</td></tr>"
    html = "<table><tbody>" + header + make_page([{"station_key": "_OK1"}])[len("<table><tbody>"):]
    readings = jps.parse(html)
    assert len(readings) == 1 and readings[0].station_key == "_OK1"


def test_parse_row_without_graph_link_raises():
    with pytest.raises(jps.JpsParseError, match="graph link"):
        jps.parse(make_page([{"station_key": "_X", "no_link": True}]))


def test_parse_duplicate_station_id_raises():
    with pytest.raises(jps.JpsParseError, match="duplicate"):
        jps.parse(make_page([{"station_key": "_DUP"}, {"station_key": "_DUP"}]))


def test_parse_station_key_drops_query_after_ampersand():
    readings = jps.parse(make_page([{"station_key": "_ABC123", "href_extra": "&lang=en"}]))
    assert readings[0].station_key == "_ABC123"


def test_parse_blank_jps_id_dash_level_and_float_thresholds():
    readings = jps.parse(make_page([{
        "Station ID": "", "wl": "-", "Normal": "5.5", "Alert": "6.5",
        "Warning": "7.5", "Danger": "8.5", "station_key": "_BLANK1",
    }]))
    r = readings[0]
    assert r.jps_id is None and r.level_m is None
    assert r.normal_m == 5.5 and r.alert_m == 6.5 and r.warning_m == 7.5 and r.danger_m == 8.5


def test_parse_collapses_newlines_and_spaces_in_name():
    readings = jps.parse(make_page([{
        "Station Name": "Sg.  Galas\n  di   Dabong  (F1)", "station_key": "_SP1",
    }]))
    assert readings[0].name == "Sg. Galas di Dabong (F1)"
    assert readings[0].name_norm == "sg galas di dabong"


def test_parse_rejected_resets_after_clean_page():
    bad = make_page([
        {"station_key": "bad%20id"},
        {"station_key": "_GOOD1"},
    ])
    assert len(jps.parse(bad)) == 1 and jps.parse.rejected == 1
    clean = make_page([{"station_key": "_CLEAN1"}])
    assert len(jps.parse(clean)) == 1 and jps.parse.rejected == 0


def test_parse_all_malformed_station_ids_raises():
    with pytest.raises(jps.JpsParseError, match="no valid"):
        jps.parse(make_page([{"station_key": "bad%20id"}, {"station_key": "also bad"}]))
