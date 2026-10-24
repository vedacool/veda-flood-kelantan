"""Home's "Where these towns are" sketch map (Cowork / Husaini 24 Oct): a static inline SVG built once by
scripts/make_home_map.py from committed data - no tiles, no network, the four towns tappable like their rows."""
import importlib.util
import re

from app import trace

ROOT = trace.ROOT
PAGE = (ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
spec = importlib.util.spec_from_file_location("make_home_map", ROOT / "scripts" / "make_home_map.py")
mhm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mhm)
SVG = PAGE[PAGE.index(mhm.START):PAGE.index(mhm.END)]
TOWNS = ("Rantau Panjang", "Pasir Mas", "Kota Bharu", "Tumpat")


def targets():
    out = {}
    for m in re.finditer(r'<g class="m-town" role="button" tabindex="0" data-town="([^"]+)">'
                         r'<rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', SVG):
        out[m.group(1)] = tuple(float(v) for v in m.group(2, 3, 4, 5))
    return out


def test_map_is_inline_and_rebuilds_to_the_same_page():
    assert '<svg viewBox="0 0 340 ' in SVG and "m-river" in SVG and "m-border" in SVG and "m-sea" in SVG
    assert mhm.page_with(mhm.build()) == PAGE                        # regenerating gives the same file
    assert mhm.main(["--check"]) == 0


def test_no_external_requests_from_the_map():
    assert not re.search(r"(href|src)\s*=|https?://|url\(", SVG)      # no tiles, no images, no links
    assert "<script" not in SVG


def test_four_town_targets_big_enough_and_never_overlapping():
    t = targets()
    assert set(t) == set(TOWNS)
    scale = (375 - 32 - 20) / 340                                     # page gutters + the card's padding at 375 px
    for town, (x, y, w, h) in t.items():
        assert min(w, h) * scale >= 44, town
        assert x >= 0 and x + w <= 340, town                          # inside the map, never cut off
    names = list(t)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            (ax, ay, aw, ah), (bx, by, bw, bh) = t[a], t[b]
            assert not (ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah), f"{a} / {b}"


def test_map_towns_do_what_the_rows_do():
    assert "function townFromMap(g)" in PAGE and "b.dataset.town = town;" in PAGE and "row.click()" in PAGE
    assert 'g.addEventListener("keydown"' in PAGE and 'e.key === "Enter" || e.key === " "' in PAGE
    assert ".m-town:focus-visible .m-hit" in PAGE                       # a visible focus ring
    assert 'map_check: "Check {town}"' in PAGE and 'map_check: "Semak {town}"' in PAGE


def test_map_wording_and_placement():
    for key in ("map_heading", "map_note", "map_credit", "map_thailand", "map_sea", "map_rain", "map_gauge", "map_alt"):
        assert PAGE.count(f"{key}: ") == 2, key                         # EN and BM
    assert "Sketch from © OpenStreetMap contributors (ODbL)" in PAGE
    assert PAGE.index('id="towns"') < PAGE.index('id="few-readings"') < PAGE.index('id="map-box"')
    assert SVG.count('class="m-gauge"') == 2 and "Kuala Krai" in SVG and "Kg. Jenob" in SVG
    assert "20 km" in SVG and 'class="m-north"' in SVG and 'class="m-cloud"' in SVG
