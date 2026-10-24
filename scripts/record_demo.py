"""Record the demo clips: 1920x1080 webm (+ mp4 when ffmpeg is on PATH) of VEDA's web page, driven by Playwright
against an OFFLINE server (SAMPLE_MODE). Offline there is no AI explanation in any clip; the live versions are
re-recorded by hand (docs/media/video/README.md says which).

    SAMPLE_MODE=true VEDA_PORT=8001 python -m app.main          # first, in its own terminal
    python scripts/record_demo.py                                # every clip -> docs/media/video/
    python scripts/record_demo.py --only a,c --base http://127.0.0.1:8001

Dev only, not in requirements.txt: pip install playwright && python -m playwright install chromium.
Safety: refuses to start unless /health says sample_mode, and drops a clip unless every answer shows the expected
data label ("Past flood replay" / "Made-up test scene") - so no live JPS reading can end up in a video.
The page is zoomed 1.5x in a 1920x1080 window (laid out as on a 1280x720 screen): large text, a full frame.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "media" / "video"
PAUSE = 2.0                              # seconds on each screen
HOLD = 4.0                               # the waiting screen is held this long (offline answers take ~0.1 s)
REPLAY, MADEUP = "Past flood replay", "Made-up test scene"
# the page laid out as on a 1280x720 screen, drawn 1.5x larger: big readable text in a full 1920x1080 frame
ZOOM_JS = "document.addEventListener('DOMContentLoaded', () => { document.documentElement.style.zoom = '1.5'; });"
STREAM = lambda url: "/run/stream?" in url               # noqa: E731 - the page's one run request

# shown on every frame, bottom left: what data this clip runs on (recording only, never part of the page)
OVERLAY_JS = """(text) => {
  let el = document.getElementById("rec-label");
  if (!el) {
    el = document.createElement("div");
    el.id = "rec-label";
    el.style.cssText = "position:fixed;left:12px;bottom:16px;z-index:99;padding:8px 14px;max-width:290px;border-radius:14px;" +
      "background:#1c1c1a;color:#fff;font:600 15px/1.3 system-ui,sans-serif;opacity:.88";
    document.body.append(el);
  }
  el.textContent = text;
}"""
# a ring where the recorder taps, so viewers can follow (headless video has no mouse pointer)
RING_JS = """(t) => {
  const r = t.getBoundingClientRect(), d = document.createElement("div");
  d.style.cssText = `position:fixed;left:${r.left + r.width / 2 - 22}px;top:${r.top + r.height / 2 - 22}px;` +
    "width:44px;height:44px;border-radius:50%;border:4px solid #1f5f8b;z-index:98;pointer-events:none;" +
    "transition:transform .5s,opacity .5s";
  document.body.append(d);
  requestAnimationFrame(() => { d.style.transform = "scale(1.6)"; d.style.opacity = "0"; });
  setTimeout(() => d.remove(), 700);
}"""
# smooth scroll over `ms` milliseconds, window or a given element's top
SCROLL_JS = """([to, ms]) => new Promise((done) => {
  const y0 = window.scrollY;
  const y1 = typeof to === "number" ? to
    : Math.max(0, document.querySelector(to).getBoundingClientRect().top + window.scrollY - 90);
  const t0 = performance.now();
  const step = (now) => {
    const k = Math.min(1, (now - t0) / ms), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    window.scrollTo(0, y0 + (y1 - y0) * e);
    k < 1 ? requestAnimationFrame(step) : done();
  };
  requestAnimationFrame(step);
})"""


class WrongData(Exception):
    """The answer did not carry the expected data label: the clip is dropped."""


class Clip:
    def __init__(self, page, base):
        self.page, self.base = page, base

    def go(self, path, label, **query):
        self.page.goto(self.base + path + ("?" + urlencode(query) if query else ""))
        self.page.wait_for_load_state("networkidle")
        self.label(label)

    def label(self, text):
        self.page.evaluate(OVERLAY_JS, text)

    def pause(self, s=PAUSE):
        time.sleep(s)

    def tap(self, sel):
        el = self.page.locator(sel).first
        el.scroll_into_view_if_needed()
        el.evaluate(RING_JS)
        time.sleep(0.5)
        el.click()

    def scroll(self, to, ms=1600):
        self.page.evaluate(SCROLL_JS, [to, ms])
        time.sleep([JPS reading])

    def scroll_through(self, ms_per_screen=2200):
        """Top to bottom, one screen at a time with a pause on each - slow enough to read."""
        h = self.page.evaluate("() => document.documentElement.scrollHeight - innerHeight")
        y = self.page.evaluate("() => scrollY")
        while y < h - 4:
            y = min(h, y + 480)
            self.scroll(y, ms_per_screen // 2)
            self.pause(ms_per_screen / 1000)

    def ask_town(self, town, expect):
        """Tap a town on Home, hold the waiting screen, wait for the answer, check its data label."""
        held = []
        self.page.route(STREAM, lambda route: held.append((route, route.fetch())))
        self.tap(f"#towns button:has-text('{town}')")
        self.page.wait_for_selector("#s-wait:not([hidden])")
        self.pause(0.6)
        self.tap("#w-more")                              # "See what VEDA is doing"
        self.pause(HOLD)
        while not held:                                  # the request is in flight: let the handler run
            self.page.wait_for_timeout(100)
        route, resp = held[0]
        route.fulfill(response=resp)
        self.page.wait_for_selector("#s-answer:not([hidden])", timeout=60000)
        self.page.unroute(STREAM)
        got = self.page.locator("#a-label-text").inner_text() if self.page.locator("#a-label").is_visible() else ""
        if not got.startswith(expect):
            raise WrongData(f"answer labelled {got!r}, expected {expect!r}")
        self.page.evaluate("() => scrollTo(0, 0)")
        self.pause()
        return self.page.evaluate("() => result.run_id")

    def details(self):
        self.tap("#a-strip")
        self.pause(0.8)
        self.scroll("#a-details")
        self.pause()
        self.scroll_through()


def home(c, label, **scene):
    c.go("/", label, lang="en", **scene)
    c.pause()
    c.tap("#demo-link")                                  # show which data the demo runs on
    c.pause()
    c.scroll(0, 600)


# ---------- the clips ----------
def clip_a(c):
    """Home -> tap Rantau Panjang (Nov 2024 replay, 27 Nov 19:30) -> waiting -> answer -> Details -> How VEDA worked."""
    lab = f"{REPLAY} · 27 Nov 2024, 19:30 · offline (SAMPLE_MODE)"
    home(c, lab, replay="nov2024", at="2024-11-27 19:30")
    run_id = c.ask_town("Rantau Panjang", REPLAY)
    c.details()
    c.tap("#a-how")
    c.pause()
    c.scroll_through()
    c.pause()
    return run_id


def clip_b(c, run_id):
    """The live log replaying clip (a)'s run at 4x."""
    c.go("/live", f"{REPLAY} · 27 Nov 2024, 19:30 · the run from clip (a), replayed at 4×", run=run_id, speed="4")
    c.page.wait_for_selector("#status:has-text('finished')", timeout=60000)
    c.pause()
    c.scroll(0, 1200)
    c.pause()
    c.scroll_through(2600)
    c.pause()


def clip_c(c):
    """Made-up rain-upstream scene for Kota Bharu: answer + Details."""
    lab = f"{MADEUP} · rain upstream + here (made-up river levels, real archive rain 27 Nov 2024)"
    home(c, lab, replay="synthetic_upstream_rain", at="2024-11-27 12:00")
    c.ask_town("Kota Bharu", MADEUP)
    c.scroll("#a-rows")
    c.pause(3)
    c.details()
    c.pause()


def clip_d(c):
    """The Critic -> Data request in the live log (made-up silent upstream gauge, Pasir Mas)."""
    lab = f"{MADEUP} · silent upstream gauge (made-up river levels)"
    home(c, lab, replay="synthetic_silent_upstream", at="2024-06-15 10:00")
    run_id = c.ask_town("Pasir Mas", MADEUP)
    c.pause()
    c.go("/live", lab + " · live log", run=run_id, speed="1")
    c.page.wait_for_selector("#status:has-text('finished')", timeout=60000)
    c.scroll(0, 800)
    c.pause()
    c.scroll("#feed li.req", 2400)
    c.pause(4)
    c.scroll_through(2600)
    c.pause()


def clip_e(c):
    """The Normal and Can't-confirm states."""
    home(c, f"{MADEUP} · calm day (made-up river levels)", replay="synthetic_calm", at="2024-06-15 10:00")
    c.ask_town("Tumpat", MADEUP)
    c.pause()
    c.details()
    c.tap("#home-link")
    c.pause(1)
    home(c, f"{REPLAY} · 26 Nov 2024, 18:00 (no reported Tumpat reading)", replay="nov2024", at="2024-11-26 18:00")
    c.ask_town("Tumpat", REPLAY)
    c.pause(3)
    c.details()


def clip_f(c):
    """Emergency: from the Can't-confirm answer, and from Home (no engine call)."""
    home(c, f"{REPLAY} · 26 Nov 2024, 18:00 (no reported Tumpat reading)", replay="nov2024", at="2024-11-26 18:00")
    c.ask_town("Tumpat", REPLAY)
    c.pause()
    c.tap("#a-sos")
    c.label("Emergency screen · no data, no engine call")
    c.pause(3)
    c.scroll_through()
    c.tap("#e-back")
    c.pause()
    c.tap("#sos")
    c.pause(3)


CLIPS = {  # key: (file stem, what it shows, data source)
    "a": ("a-replay-rantau-panjang", "Home → tap Rantau Panjang → waiting → answer → Details → How VEDA worked this out",
          "Past flood replay, Nov 2024 (readings reported in the news, cited), 27 Nov 19:30"),
    "b": ("b-live-log-replay-4x", "Live log replaying clip (a)'s run at 4×",
          "Past flood replay, Nov 2024, 27 Nov 19:30 (the trace of clip a)"),
    "c": ("c-rain-upstream-kota-bharu", "Made-up rain-upstream scene for Kota Bharu: answer + Details",
          "Made-up test scene: SYNTHETIC river levels + real Open-Meteo archive rain, 27 Nov 2024 12:00"),
    "d": ("d-live-log-critic-data-request", "Live log: the Critic asks the Data & Reconciler for a missing upstream "
          "reading (Pasir Mas)", "Made-up test scene: SYNTHETIC silent upstream gauge, 15 Jun 2024 10:00"),
    "e": ("e-states-normal-cant-confirm", "Normal for now (Tumpat, calm day), then Can't confirm right now (Tumpat, "
          "26 Nov 18:00)", "Made-up test scene (calm day), then Past flood replay, Nov 2024"),
    "f": ("f-emergency", "Emergency: from the Can't-confirm answer, and from Home", "Past flood replay, Nov 2024, "
          "26 Nov 18:00; the Emergency screen itself uses no data"),
}


def health(base):
    with urllib.request.urlopen(base + "/health", timeout=10) as r:
        return json.load(r)


def seconds(path):
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    r = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return round(float(r.stdout.strip()))
    except ValueError:
        return None


def to_mp4(webm):
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    mp4 = webm.with_suffix(".mp4")
    subprocess.run([ff, "-y", "-v", "error", "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
                    "-preset", "slow", "-movflags", "+faststart", "-an", str(mp4)], check=True)
    return mp4


def record(key, base, tmp, shared):
    stem = CLIPS[key][0]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080},
                                  record_video_dir=str(tmp), record_video_size={"width": 1920, "height": 1080},
                                  color_scheme="light", locale="en-GB")
        ctx.add_init_script(ZOOM_JS)
        page = ctx.new_page()
        c = Clip(page, base)
        try:
            if key == "a":
                shared["run_a"] = clip_a(c)
            elif key == "b":
                if "run_a" not in shared:                # (b) replays (a)'s run: make one without filming it
                    raise WrongData("clip b needs clip a's run - record a first (--only a,b)")
                clip_b(c, shared["run_a"])
            else:
                globals()["clip_" + key](c)
            ok = True
        except WrongData as e:
            print(f"  {key}: DROPPED - {e}")
            ok = False
        video = page.video
        ctx.close()
        browser.close()
        src = Path(video.path())
        if not ok:
            src.unlink(missing_ok=True)
            return None
        dst = OUT / f"{stem}.webm"
        shutil.move(src, dst)
        return dst


def write_readme(made, base_commit):
    rows = []
    for key, (stem, what, data) in CLIPS.items():
        files = [f for f in (OUT / f"{stem}.webm", OUT / f"{stem}.mp4") if f.exists()]
        if not files:
            continue
        secs = seconds(files[0])
        mb = sum(f.stat().st_size for f in files) / 1e6
        names = " / ".join(f"`{f.name}`" for f in files)
        rows.append(f"| {key} | {names} | {secs if secs is not None else '?'} s | {what} | {data} | {mb:.1f} MB |")
    text = f"""# Demo video clips

Made by `scripts/record_demo.py` (Playwright, Chromium headless) from VEDA's own web page, at {made} from commit
`{base_commit}`. 1920x1080 (the page zoomed 1.5x, laid out as on a 1280x720 screen), webm and mp4 (H.264). Slow pacing: about 2 s on each
screen, smooth scrolling, a ring where the recorder taps. The pill at the bottom left of every frame names the data
the clip runs on; it is added by the recorder, not part of VEDA's page.

**Offline recordings (SAMPLE_MODE):** no network, no Zetaris, no Nightshift. So **no clip shows an AI explanation**
(the card is written and checked by code; offline the models are replaced by the agents' code fallbacks), and the
step timings are offline timings (a run takes about 0.1 s). The waiting screen is **held for {HOLD:.0f} s by the
recorder** so it can be seen; a live run waits for real (up to 150 s). No JPS reading appears in any clip: every answer
is checked to carry the "Past flood replay" or "Made-up test scene" label, or the clip is dropped.

| Clip | Files | Length | What it shows | Data | Size |
|---|---|---|---|---|---|
""" + "\n".join(rows) + """

## To re-record live (with the AI explanation) - Session A / Husaini
Live = Zetaris + Nightshift running, Nemotron 3.5 Super VL by name, still on the **Nov 2024 replay** (never live JPS
data; delete Nightshift's VEDA memory records first, as for the 24 Oct screenshots):
- **a** - the answer's "In plain words" (AI explanation) and "How VEDA worked this out" with the served model,
  Nightshift receipt and real seconds; the waiting screen with a real wait.
- **b** - the live log with real "Waiting for Nemotron" bubbles and the two Nightshift calls (draft + Critic review).
- **c**, **d** - optional: the same scenes with the AI explanation (both are made-up scenes, labelled).
- **e**, **f** - no need: Normal (quick path) and Can't confirm use no AI, and Emergency makes no engine call.
"""
    (OUT / "README.md").write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    ap.add_argument("--only", default=",".join(CLIPS), help="comma-separated clip keys, e.g. a,b")
    a = ap.parse_args()
    h = health(a.base)
    if not h.get("sample_mode"):
        sys.exit("refusing: the server is not in SAMPLE_MODE (a live run could show live JPS readings)")
    OUT.mkdir(parents=True, exist_ok=True)
    keys = [k.strip() for k in a.only.split(",") if k.strip() in CLIPS]
    shared = {}
    with tempfile.TemporaryDirectory() as tmp:
        for key in keys:
            print(f"recording {key} ({CLIPS[key][0]}) ...")
            webm = record(key, a.base, Path(tmp), shared)
            if webm:
                mp4 = to_mp4(webm)
                print(f"  {key}: {webm.name}" + (f" + {mp4.name}" if mp4 else "") + f", {seconds(webm)} s")
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip()
    write_readme(time.strftime("%d %b %Y %H:%M MYT"), commit)


if __name__ == "__main__":
    main()
