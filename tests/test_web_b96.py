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
    assert 'id="a-why-open"' in PAGE and '<details class="tech"><summary data-t="tech_log">' in PAGE
    assert 'useful: "Was this useful? Tell us"' in PAGE and '$("a-useful").hidden = !publicDemo;' in PAGE
