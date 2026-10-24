"""B-96 shared frame for every VEDA page: top bar (VEDA · Test scenes · How it works · EN|BM), the demo strip and the
footer (Feedback · API docs · not an official warning).

    html = frame.framed(page_html, "home")      # page = home | scenes | how | feedback

A page marks where they go with <!--VEDA:TOP--> (first thing in <body>) and <!--VEDA:FOOT--> (last). The frame's
words carry both languages (data-vf-en / data-vf-ms); /frame.js picks one. The demo strip shows in offline sample mode
(the public demo and a judge's own clone); the Feedback link only in the public demo, where /feedback exists.
"""
from html import escape

from app import config

TOP, FOOT = "<!--VEDA:TOP-->", "<!--VEDA:FOOT-->"
PAGES = {"scenes": ("/scenes", "Test scenes", "Senario ujian"),
         "how": ("/how-it-works", "How it works", "Cara VEDA berfungsi")}
STRIP = ("Demo · past flood replay · not an official warning", "Demo · ulang tayang banjir lalu · bukan amaran rasmi")
FEEDBACK = ("Feedback", "Maklum balas")
API_DOCS = ("API docs", "Dokumen API")
NOTICE = ("Not an official warning · 999 / APM 991", "Bukan amaran rasmi · 999 / APM 991")


def _words(pair):
    en, ms = pair
    return f'data-vf-en="{escape(en)}" data-vf-ms="{escape(ms)}">{escape(en)}'


def top(page, demo=None):
    """The top bar (+ the demo strip in offline sample mode). page: which link is the current page (bold)."""
    demo = config.sample_mode() if demo is None else demo
    cur = lambda p: ' aria-current="page"' if p == page else ""                       # noqa: E731
    links = "".join(f'<a href="{href}"{cur(key)} {_words((en, ms))}</a>' for key, (href, en, ms) in PAGES.items())
    # phone: VEDA + EN|BM on the first row, the two page links on the second; desktop: one row (frame.css)
    bar = ('<link rel="stylesheet" href="/frame.css">'
           '<header class="vf-top">'
           f'<a class="vf-home" id="home-link" href="/"{cur("home")}>VEDA</a>'
           f'<nav class="vf-links" aria-label="VEDA">{links}</nav>'
           '<span class="vf-lang seg" role="group" aria-label="Language / Bahasa">'
           '<button type="button" data-lang="en" aria-pressed="true">EN</button>'
           '<button type="button" data-lang="ms" aria-pressed="false">BM</button></span></header>')
    return bar + (f'<p class="vf-strip" role="note" {_words(STRIP)}</p>' if demo else "")


def foot(public_demo=None):
    """The footer: Feedback (public demo only) · API docs · the one-line notice."""
    public_demo = config.demo_mode() if public_demo is None else public_demo
    items = ([f'<a href="/feedback" {_words(FEEDBACK)}</a>'] if public_demo else []) + [
        f'<a href="/api/docs" {_words(API_DOCS)}</a>', f'<span {_words(NOTICE)}</span>']
    return f'<footer class="vf-foot">{" · ".join(items)}</footer><script src="/frame.js" defer></script>'


def framed(html, page):
    """A page with the frame in place of its two markers (unchanged when it has none)."""
    return html.replace(TOP, top(page), 1).replace(FOOT, foot(), 1)
