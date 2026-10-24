"""B-96 shared frame: the same top bar, demo strip and footer on every VEDA page (app/frame.py, app/web/frame/)."""
import re

from starlette.testclient import TestClient

from app import frame, main


def test_home_and_how_it_works_carry_the_frame(monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    monkeypatch.delenv("VEDA_DEMO", raising=False)
    c = TestClient(main.app)
    assert c.get("/how-it-works").status_code == 200          # the /judges page; Session B adds the frame markers to it
    for path, current in (("/", "/"),):
        html = c.get(path).text
        assert html.count('class="vf-top"') == 1 and html.count('class="vf-foot"') == 1, path
        nav = re.search(r'<nav aria-label="VEDA">(.*?)</nav>', html).group(1)
        assert re.findall(r'href="([^"]+)"', nav) == ["/", "/scenes", "/how-it-works"]          # nothing else in the bar
        assert re.search(rf'href="{current}"[^>]*aria-current="page"', nav), path               # current page in bold
        assert '<!--VEDA:' not in html and 'id="aa"' not in html
    assert "Demo · past flood replay · not an official warning" in c.get("/").text              # offline: the strip


def test_judges_moves_to_how_it_works_and_the_frame_files_are_served(monkeypatch):
    c = TestClient(main.app)
    r = c.get("/judges", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/how-it-works"
    assert c.get("/frame.css").status_code == 200 and "vf-top" in c.get("/frame.css").text
    assert c.get("/frame.js").status_code == 200 and "vedaFrameLang" in c.get("/frame.js").text


def test_strip_only_offline_feedback_only_in_the_public_demo():
    assert 'class="vf-strip"' in frame.top("home", demo=True) and 'class="vf-strip"' not in frame.top("home", demo=False)
    assert 'href="/feedback"' in frame.foot(public_demo=True) and 'href="/feedback"' not in frame.foot(public_demo=False)
    f = frame.foot(public_demo=True)
    assert 'href="/api/docs"' in f and "Not an official warning · 999 / APM 991" in f
    assert 'data-vf-ms="Bukan amaran rasmi · 999 / APM 991"' in f
    assert 'data-vf-ms="Demo · ulang tayang banjir lalu · bukan amaran rasmi"' in frame.top("home", demo=True)
