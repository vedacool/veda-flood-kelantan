"""B2: the desktop layout (>= 1024 px) is CSS placement only - the phone layout and the document order are unchanged."""
import re

from app import trace

PAGE = (trace.ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
CSS = PAGE.split("<style>", 1)[1].split("</style>", 1)[0]
DESKTOP = CSS.split("@media (min-width: 1024px) {", 1)[1]


def test_every_desktop_rule_is_inside_the_1024px_block():
    outside = CSS.split("@media (min-width: 1024px) {", 1)[0]
    for sel in ("#s-home {", "#s-answer {", "#s-wait {", ".wait-side", ".wait-steps", "max-width: 1200px"):
        assert sel not in outside, sel                      # nothing changes on a phone
        assert sel in DESKTOP, sel


def test_home_answer_and_checking_columns():
    assert "#s-home > #map-box { grid-column: 2;" in DESKTOP                         # map right
    assert "#s-home > * { grid-column: 1; }" in DESKTOP                               # town list left
    assert "#s-answer > #a-rows { grid-column: 2;" in DESKTOP                         # gauge post, upstream, rain right
    for left in ("#a-badge", ".todo", ".actions"):                                    # verdict, WHAT TO DO, actions left
        assert re.search(rf"#s-answer > {re.escape(left)}[^{{]*{{ grid-column: 1; }}", DESKTOP) or \
            f"#s-answer > {left}," in DESKTOP, left
    assert "#s-answer > * { grid-column: 1 / -1; }" in DESKTOP                        # Details full width below
    assert "#s-wait > .wait-steps { grid-column: 1;" in DESKTOP and "#s-wait > .wait-side { grid-column: 2;" in DESKTOP
    assert "main { max-width: 1200px;" in DESKTOP


def test_document_order_is_the_phone_order():
    """Phones and screen readers follow the document: towns before the map before the question box; the river cards
    after WHAT TO DO and its send / listen buttons (Part 8); progress before the steps."""
    order = lambda *ids: [PAGE.index(i) for i in ids]                                 # noqa: E731
    assert order('id="towns"', 'id="map-box"', 'id="ask"') == sorted(order('id="towns"', 'id="map-box"', 'id="ask"'))
    a = order('class="card todo"', 'class="actions"', 'id="a-rows"', 'id="a-details"')
    assert a == sorted(a)
    w = order('class="wait-side"', 'id="w-status"', 'id="w-tip"', 'class="wait-steps"', 'id="w-check"', 'id="log"')
    assert w == sorted(w)
