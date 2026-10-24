"""Part 8 design polish: send / listen under WHAT TO DO, Details never wraps, one agent tag per step, the gauge post's
labels never overlap, and the demo-only intro line to the scenes."""
import re

from starlette.testclient import TestClient

from app import config

PAGE = (config.ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")


def test_send_and_listen_sit_right_under_what_to_do_and_check_again_at_the_bottom():
    todo, actions, rows = PAGE.index('class="card todo"'), PAGE.index('id="a-actions"'), PAGE.index('id="a-rows"')
    assert todo < actions < rows
    block = PAGE[actions:rows]
    assert 'id="a-wa"' in block and 'id="a-listen"' in block and 'id="a-check"' not in block
    assert PAGE.index('id="a-check"') < PAGE.index('id="a-again"')


def test_details_never_wraps_and_the_desktop_row_is_one_row():
    assert ".strip > span:last-child { white-space: nowrap;" in PAGE
    assert "#s-answer > .actions { grid-template-columns: 1fr auto;" in PAGE


def test_one_agent_tag_per_step():
    assert '$("w-status").textContent = t(keys[i]);' in PAGE          # the list item carries the tag
    assert '($("log").hidden ? agentTag(name) : "")' in PAGE


def test_gauge_post_labels_are_spaced_and_the_2014_line_starts_right_of_the_post():
    assert "Math.max(y(v) - 5, prev + 20)" in PAGE and 'x1="${dashed ? x1 : x0 - 4}"' in PAGE
    assert "const lo = r.level_m < low ? r.level_m - step * 0.6 : low;" in PAGE


def test_demo_intro_only_in_the_demo(monkeypatch):
    m = re.search(r'<p class="intro" id="demo-intro" hidden>.*?href="/scenes"', PAGE, re.S)
    assert m and PAGE.index('id="towns"') < m.start()                       # under the towns: they stay on screen 1
    assert 'demo_intro: "New here? Read a scene first, then test VEDA:", demo_scenes: "Scenes ›"' in PAGE
    assert 'demo_intro: "Baru di sini? Baca senario dahulu, kemudian uji VEDA:", demo_scenes: "Senario ›"' in PAGE
    from app import main
    monkeypatch.setenv("SAMPLE_MODE", "true")
    monkeypatch.delenv("VEDA_DEMO", raising=False)
    assert "demo" not in TestClient(main.app).get("/health").json()
    monkeypatch.setenv("VEDA_DEMO", "1")
    assert TestClient(main.app).get("/health").json()["demo"] is True
