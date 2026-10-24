"""B-96 part 1 (Cowork wireframes v3): judge-first home offline / in the demo, one filled button per screen, the
answer's "Why this answer?" with the technical log folded under it."""
import re

from app import config

PAGE = (config.ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")


def test_home_30_seconds_block_with_one_start_button_and_two_links():
    block = re.search(r'<div id="intro30" hidden>(.*?)</div>', PAGE, re.S).group(1)
    assert block.count('class="primary') == 1 and 'id="i30-start"' in block
    assert re.findall(r'href="([^"]+)"', block) == ["/scenes", "/how-it-works"]
    assert 'i30_start: "Start: Rantau Panjang at the Nov 2024 flood peak"' in PAGE
    assert 'i30_start: "Mula: Rantau Panjang semasa kemuncak banjir Nov 2024"' in PAGE
    assert 'i30_line: "VEDA menjawab soalan ini untuk Kelantan. Beberapa ejen AI menyemak kerja satu sama lain, dan setiap langkah direkodkan."' in PAGE
    assert '$("intro30").hidden = !sampleMode;' in PAGE and '$("ask-go").classList.toggle("primary", !sampleMode);' in PAGE
    assert 'pick(PEAK); ask(UI[lang].q_default.replace("{town}", "Rantau Panjang"), "Rantau Panjang")' in PAGE


def test_old_scene_link_intro_line_and_check_buttons_are_gone():
    for gone in ('id="scenes-link"', 'id="demo-intro"', '<p class="intro" id="intro">', 'id="aa"'):
        assert gone not in PAGE, gone
    assert '<span class="go" aria-hidden="true">›</span>' in PAGE                      # the whole row is the target


def test_answer_one_filled_button_listen_link_and_why():
    actions = re.search(r'<div class="actions" id="a-actions">(.*?)</div>', PAGE, re.S).group(1)
    assert 'id="a-wa"' in actions and 'id="a-listen"' not in actions
    links = re.search(r'<p class="links-row" id="a-links">(.*?)</p>', PAGE, re.S).group(1)
    assert 'id="a-share"' in links and 'id="a-listen"' in links and links.count('class="linkish"') == 2
    assert 'id="a-why-open"' in PAGE and '<summary id="a-tech-sum" data-t="tech_log">' in PAGE
    assert 'tech_log: "Show technical log ▾", tech_hide: "Hide technical log ▴"' in PAGE


def test_fix_round_plain_replay_line_end_links_and_one_disclaimer():
    assert '<p id="a-label" class="moment-line" hidden>' in PAGE and 'class="chip"' not in PAGE
    assert 'replay_of: "Replay of"' in PAGE
    end = re.search(r'<p class="links-row" id="a-end">(.*?)</p>', PAGE, re.S).group(1)
    assert 'id="a-check"' in end and 'id="a-again"' in end and end.count('class="linkish"') == 2
    assert 'data-t="disclaimer"' in PAGE.split('id="s-sos"')[1]                      # only the emergency screen keeps it
    assert PAGE.split('id="s-sos"')[0].count('data-t="disclaimer"') == 0 and 'data-t="footer"' not in PAGE
    assert 'i30_how: "Cara VEDA berfungsi: ejen, rakaman sebenar, API ›"' in PAGE
    assert 'useful: "Was this useful? Tell us"' in PAGE and '$("a-useful").hidden = !publicDemo;' in PAGE


LIVE = (config.ROOT / "app" / "web" / "live.html").read_text(encoding="utf-8")


def test_live_has_no_filled_button_and_opens_on_the_featured_run_in_the_demo():
    assert 'button[aria-pressed="true"] { border: 3px solid var(--accent); font-weight: 800; }' in LIVE
    filled = [ln for ln in LIVE.splitlines() if "background: var(--accent)" in ln]
    assert len(filled) == 1 and filled[0].lstrip().startswith("#b-play")               # Play: the one filled button
    assert 'redacted: "River readings are hidden, as the organisers asked. Details ▾"' in LIVE
    assert 'redacted: "Bacaan sungai disembunyikan, seperti yang diminta penganjur. Butiran ▾"' in LIVE
    assert '<details class="note rnote" id="rnote" hidden>' in LIVE and '" UTC"' not in LIVE
    assert 'id="b-replay"' in LIVE and 'const FEATURED = "20261024-201011";' in LIVE
    assert 'if (h.sample_mode) listed.then(() => loadChosen(true)); else goLive();' in LIVE   # live mode unchanged
    assert 'hint: "Press play to watch each agent step, recorded live."' in LIVE
    assert LIVE.index('id="b-play"') < LIVE.index('<div class="wrap">')               # Play before the panel


def test_bm_change_link_never_breaks_and_sources_lines_keep_their_height():
    assert '<span class="nowrap"><span id="a-change-dot"' in PAGE
    src = (config.ROOT / "app" / "web" / "sources.html").read_text(encoding="utf-8")
    assert "li a { display: inline-block; padding: 10px 0; margin: -10px 0; }" in src
