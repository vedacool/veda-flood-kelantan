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
    for key in ("map_heading", "map_note", "map_credit", "map_thailand", "map_sea", "map_rain1", "map_rain2", "map_gauge", "map_alt"):
        assert PAGE.count(f"{key}: ") == 2, key                         # EN and BM
    assert "Sketch from © OpenStreetMap contributors (ODbL)" in PAGE
    assert PAGE.index('id="towns"') < PAGE.index('id="few-readings"') < PAGE.index('id="map-box"')
    assert SVG.count('class="m-gauge"') == 2 and "Kuala Krai" in SVG and "Kg. Jenob" in SVG
    assert "20 km" in SVG and 'class="m-north"' in SVG and 'class="m-cloud"' in SVG


def test_each_town_label_is_nearest_its_own_dot():
    """Cowork 24 Oct (5c): a label never reads as another town's - its centre is nearer its own dot than any other."""
    dots, labels = {}, {}
    for m in re.finditer(r'data-town="([^"]+)">.*?<circle cx="([\d.]+)" cy="([\d.]+)" r="8" class="m-dot"/>'
                         r'<text x="([\d.]+)" y="([\d.]+)"(?: text-anchor="(\w+)")?[^>]*>([^<]+)(?:<tspan[^>]*>([^<]+))?',
                         SVG):
        town, cx, cy, tx, ty, anchor, first, second = m.groups()
        w = max(len(first), len(second or "")) * 11.6
        x0 = float(tx) - (w if anchor == "end" else w / 2 if anchor == "middle" else 0)
        dots[town] = (float(cx), float(cy))
        labels[town] = (x0 + w / 2, float(ty) - 7 + (10 if second else 0))
    assert set(dots) == set(TOWNS)
    for town, (lx, ly) in labels.items():
        own = (lx - dots[town][0]) ** 2 + (ly - dots[town][1]) ** 2
        assert all(own < (lx - x) ** 2 + (ly - y) ** 2 for t, (x, y) in dots.items() if t != town), town


# -- Part 6 (Cowork 24 Oct): live mode shows all nine places --------------------------------------------------------
LIVE = PAGE[PAGE.index(mhm.LIVE_START):PAGE.index(mhm.LIVE_END)]
ADDED = ("Kuala Krai", "Tanah Merah", "Dabong", "Wakaf Bharu", "Pasir Pekan")


def test_two_maps_demo_four_towns_live_nine_places():
    assert 'id="map-demo"' in SVG and ' hidden' not in SVG.split(">", 1)[0]          # the demo map shows at once
    assert 'id="map-live"' in LIVE and LIVE.split("<svg", 1)[1].split(">", 1)[0].endswith(" hidden")
    assert SVG.count('class="m-town"') == 4 and 'class="m-place"' not in SVG             # offline: 4 places
    assert LIVE.count('class="m-town"') == 4 and LIVE.count('class="m-place"') == 5
    assert all(f'data-place="{p}"' in LIVE for p in ADDED) and "Dabong" in LIVE          # south to Dabong
    assert 'class="m-place"' in LIVE and 'role="button"' not in LIVE.split('class="m-place"', 1)[1][:200]
    assert mhm.page_with(mhm.build(), mhm.build(live=True)) == PAGE


def test_live_labels_are_nearest_their_own_dots_and_targets_do_not_overlap():
    dots = {}
    for m in re.finditer(r'data-town="([^"]+)">.*?<circle cx="([\d.]+)" cy="([\d.]+)"', LIVE):
        dots[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    for m in re.finditer(r'data-place="([^"]+)"><circle cx="([\d.]+)" cy="([\d.]+)"', LIVE):
        dots[m.group(1)] = (float(m.group(2)), float(m.group(3)))
    assert len(dots) == 9
    labels = {}
    for m in re.finditer(r'data-(?:town|place)="([^"]+)">.*?<text x="([\d.]+)" y="([\d.]+)"(?: text-anchor="(\w+)")?'
                         r'[^>]*>([^<]+)(?:<tspan[^>]*>([^<]+))?', LIVE, re.S):
        name, tx, ty, anchor, first, second = m.groups()
        w = max(len(first), len(second or "")) * (11.6 if first.strip() not in "12" else 1)
        x0 = float(tx) - (w if anchor == "end" else w / 2 if anchor == "middle" else 0)
        labels[name] = (x0 + w / 2, float(ty) - 7 + (10 if second else 0))
    assert set(labels) == set(dots)
    for name, (lx, ly) in labels.items():
        own = (lx - dots[name][0]) ** 2 + (ly - dots[name][1]) ** 2
        assert all(own < (lx - x) ** 2 + (ly - y) ** 2 for t, (x, y) in dots.items() if t != name), name
    boxes = [tuple(float(v) for v in m.groups()) for m in re.finditer(
        r'class="m-town"[^>]*><rect x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"', LIVE)]
    for i, (ax, ay, aw, ah) in enumerate(boxes):
        for bx, by, bw, bh in boxes[i + 1:]:
            assert not (ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah)
    for name in ("Wakaf Bharu", "Pasir Pekan"):                              # numbered dots: no target hides them
        x, y = dots[name]
        assert not any(bx <= x <= bx + bw and by <= y <= by + bh for bx, by, bw, bh in boxes), name


def test_live_also_covered_chips_hidden_offline():
    assert '<div id="also" hidden>' in PAGE and 'const ALSO = ["Kuala Krai", "Tanah Merah", "Dabong", "Wakaf Bharu", "Pasir Pekan"];' in PAGE
    assert "function showLive()" in PAGE and '$("also").hidden = !live;' in PAGE
    assert PAGE.count("also_covered: ") == 2 and PAGE.count("map_alt_live: ") == 2
