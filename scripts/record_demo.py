"""Record the demo clips: webm (+ mp4 when ffmpeg is on PATH) of VEDA's web page at two sizes - a 375 px phone and a
1440 px desktop - driven by Playwright against an OFFLINE server (SAMPLE_MODE). Offline there is no AI explanation
in any clip; the live versions are re-recorded by hand (docs/media/video/README.md says which).

    SAMPLE_MODE=true VEDA_PORT=8001 python -m app.main          # first, in its own terminal
    python scripts/record_demo.py                                # every clip at both sizes -> docs/media/video/
    python scripts/record_demo.py --only a,c --sizes 1440 --base http://127.0.0.1:8001

Dev only, not in requirements.txt: pip install -r requirements-dev.txt && python -m playwright install chromium.
Safety: refuses to start unless /health says sample_mode, and drops a clip unless every answer shows the expected
data label ("Past flood replay" / "Made-up test scene") - so no live JPS reading can end up in a video.
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
PAUSE = 1.5                              # seconds held after every tap
LOOK = 3.0                               # seconds on the things that matter (map, verdict, WHAT TO DO, river, Details)
SCROLL_PX_S = 300                        # smooth, slow scrolling
TYPE_MS = 80                             # typing, per key
# Offline an answer takes ~0.1 s. While a question runs, the recorder slows the browser's download to this many
# bytes a second, so the real step lines (and their agent tags) arrive one by one in "See what VEDA is doing" and the
# whole answer in ~10 s - as a live run looks. The README says so.
SLOW_BYTES_S = 2000
REPLAY, MADEUP = "Past flood replay", "Made-up test scene"
# the two screens the page is designed for (B2): name -> (viewport, mp4 scale). Playwright films at the viewport's
# CSS size (a larger video size only pads the frame), so the phone clip is filmed at 375x812 and the mp4 is scaled 2x.
SIZES = {"375": ({"width": 375, "height": 812}, 2), "1440": ({"width": 1440, "height": 900}, 1)}

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
# a visible pointer (headless video has none): a ~22 px dot with a light ring, recording only - never part of the page.
# It glides to a point over `ms` (eased); the page is new after each navigation, so it starts where the last one was.
CURSOR_JS = """([x0, y0, x1, y1, ms]) => new Promise((done) => {
  let c = document.getElementById("rec-cursor");
  if (!c) {
    c = document.createElement("div");
    c.id = "rec-cursor";
    c.style.cssText = "position:fixed;left:0;top:0;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;" +
      "background:#1c1c1a;border:3px solid #fff;box-shadow:0 0 0 4px rgba(31,95,139,.45),0 2px 6px rgba(0,0,0,.35);" +
      "z-index:2147483647;pointer-events:none";
    document.body.append(c);
  }
  const t0 = performance.now();
  const step = (now) => {
    const k = ms ? Math.min(1, (now - t0) / ms) : 1, e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
    c.style.transform = `translate(${x0 + (x1 - x0) * e}px, ${y0 + (y1 - y0) * e}px)`;
    k < 1 ? requestAnimationFrame(step) : done();
  };
  requestAnimationFrame(step);
})"""
# a small ripple where the pointer clicks
RIPPLE_JS = """([x, y]) => {
  const d = document.createElement("div");
  d.style.cssText = `position:fixed;left:${x - 18}px;top:${y - 18}px;width:36px;height:36px;border-radius:50%;` +
    "border:3px solid #1f5f8b;z-index:2147483646;pointer-events:none;transition:transform .45s,opacity .45s";
  document.body.append(d);
  requestAnimationFrame(() => { d.style.transform = "scale(1.8)"; d.style.opacity = "0"; });
  setTimeout(() => d.remove(), 600);
}"""
# how far the open step log reaches below the screen (0 when it is closed or fits)
LOG_BELOW_JS = """() => { const l = document.getElementById("log");
  return l && !l.hidden ? l.getBoundingClientRect().bottom - innerHeight : 0; }"""
# smooth scroll at `speed` px/s to a y, or to put an element's top just under the header
SCROLL_JS = """([to, speed]) => new Promise((done) => {
  const y0 = window.scrollY, most = document.documentElement.scrollHeight - innerHeight;
  const y1 = Math.max(0, Math.min(most, typeof to === "number" ? to
    : document.querySelector(to).getBoundingClientRect().top + window.scrollY - 90));
  const ms = Math.max(300, Math.abs(y1 - y0) / speed * 1000);
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
        vp = page.viewport_size
        self.xy = (vp["width"] * 0.6, vp["height"] * 0.55)   # where the pointer rests
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.send("Network.enable")

    def go(self, path, label, **query):
        self.page.goto(self.base + path + ("?" + urlencode(query) if query else ""))
        self.page.wait_for_load_state("networkidle")
        self.label(label)
        self.page.evaluate(CURSOR_JS, [*self.xy, *self.xy, 0])

    def label(self, text):
        self.page.evaluate(OVERLAY_JS, text)

    def pause(self, s=PAUSE):
        time.sleep(s)

    def point(self, x, y, ms=400):
        self.page.evaluate(CURSOR_JS, [*self.xy, x, y, ms])
        self.xy = (x, y)

    def into_view(self, sel):
        """Scroll smoothly until the element is on screen (its top under the header), if it is not already."""
        r = self.page.locator(sel).first.bounding_box()
        h = self.page.viewport_size["height"]
        if r is None or (r["y"] >= 70 and r["y"] + min(r["height"], h * 0.5) <= h):
            return
        self.scroll(sel)

    def tap(self, sel, hold=PAUSE):
        """The pointer glides to the element, a ripple, the click, then a hold."""
        self.into_view(sel)
        r = self.page.locator(sel).first.bounding_box()
        x, y = r["x"] + r["width"] / 2, r["y"] + r["height"] / 2
        self.point(x, y)
        self.page.evaluate(RIPPLE_JS, [x, y])
        self.page.locator(sel).first.click()
        self.pause(hold)

    def look(self, sel, s=LOOK):
        """Bring something into view, rest the pointer on it and hold."""
        self.into_view(sel)
        r = self.page.locator(sel).first.bounding_box()
        h = self.page.viewport_size["height"]
        self.point(r["x"] + min(r["width"] - 16, 40), min(r["y"] + 24, h - 40))
        self.pause(s)

    def type(self, sel, text):
        """Tap the field, type letter by letter, pause before sending."""
        self.tap(sel, hold=0.4)
        r = self.page.locator(sel).first.bounding_box()
        self.point(r["x"] + r["width"] * 0.75, r["y"] + r["height"] + 28)        # out of the way of the text
        self.page.keyboard.type(text, delay=TYPE_MS)
        self.pause(2.0)

    def scroll(self, to, speed=SCROLL_PX_S):
        self.page.evaluate(SCROLL_JS, [to, speed])
        time.sleep(0.2)

    def scroll_through(self, pause_s=PAUSE):
        """Top to bottom, one screen at a time with a pause on each - slow enough to read."""
        h = self.page.evaluate("() => document.documentElement.scrollHeight - innerHeight")
        y = self.page.evaluate("() => scrollY")
        step = self.page.viewport_size["height"] * 0.6
        while y < h - 4:
            y = min(h, y + step)
            self.scroll(y)
            self.pause(pause_s)

    def slow(self, on):
        self.cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 0, "uploadThroughput": -1,
                                                            "downloadThroughput": SLOW_BYTES_S if on else -1})

    def ask(self, send_sel, expect):
        """Send the question (tap a town or Ask) with the download slowed, open "See what VEDA is doing" at once,
        follow the step lines as they arrive, then check the answer's data label."""
        self.slow(True)
        try:
            self.tap(send_sel, hold=0.3)
            self.page.wait_for_selector("#s-wait:not([hidden])")
            self.tap("#w-more", hold=0.2)                # the steps and their agent tags, live
            for _ in range(600):
                if self.page.locator("#s-answer:not([hidden])").count():
                    break
                below = self.page.evaluate(LOG_BELOW_JS)
                if below > 40:
                    self.scroll(self.page.evaluate("() => scrollY") + below + 40)
                self.page.wait_for_timeout(250)
            self.page.wait_for_selector("#s-answer:not([hidden])", timeout=60000)
        finally:
            self.slow(False)
        # the server's own data label (the chip on screen shows the short form, "Replay · 27 Nov 2024, 7:30 pm")
        got = self.page.evaluate("() => (result && result.view && result.view.label && result.view.label.en) || ''")
        if not got.startswith(expect) or not self.page.locator("#a-label").is_visible():
            raise WrongData(f"answer labelled {got!r}, expected {expect!r}")
        self.page.evaluate("() => scrollTo(0, 0)")
        self.pause(0.6)
        return self.page.evaluate("() => result.run_id")

    def ask_town(self, town, expect):
        return self.ask(f"#towns button:has-text('{town}')", expect)

    def answer_tour(self):
        """The verdict, WHAT TO DO, the gauge post and the upstream strip - ~3 s each."""
        self.look("#a-badge")
        self.look("#s-answer .todo")
        self.look("#a-river-box")
        self.look("#a-flow-box")

    def switch_language(self):
        """EN -> BM on the answer, hold, and back."""
        self.scroll(0)
        self.tap(".seg button[data-lang=ms]", hold=LOOK)
        self.tap(".seg button[data-lang=en]")

    def details(self):
        self.tap("#a-strip")
        self.look("#a-details")
        self.scroll_through()


def home(c, label, show_map=False, **scene):
    c.go("/", label, lang="en", **scene)
    c.pause()
    if show_map:                                         # "Where these towns are", then back up to the towns
        c.look("#map-box")
        c.scroll(0)
        c.pause(1)


# ---------- the clips ----------
def clip_a(c):
    """Home -> the map -> tap Rantau Panjang (Nov 2024 replay, 27 Nov 19:30) -> the steps -> answer (verdict, WHAT TO
    DO, river, upstream) -> EN/BM -> Details -> How VEDA worked."""
    lab = f"{REPLAY} · 27 Nov 2024, 19:30 · offline (SAMPLE_MODE)"
    home(c, lab, show_map=True, replay="nov2024", at="2024-11-27 19:30")
    run_id = c.ask_town("Rantau Panjang", REPLAY)
    c.answer_tour()
    c.switch_language()
    c.details()
    c.tap("#a-how")
    c.scroll_through()
    c.pause()
    return run_id


def clip_b(c, run_id):
    """The live log replaying clip (a)'s run at 4x."""
    c.go("/live", f"{REPLAY} · 27 Nov 2024, 19:30 · the run from clip (a), replayed at 4×", run=run_id, speed="4")
    c.page.wait_for_selector("#status:has-text('finished')", timeout=60000)
    c.pause()
    c.scroll(0)
    c.pause()
    c.scroll_through()
    c.pause()


def clip_c(c):
    """Made-up rain-upstream scene for Kota Bharu: the question typed, the steps, answer + Details."""
    lab = f"{MADEUP} · rain upstream + here (made-up river levels, real archive rain 27 Nov 2024)"
    home(c, lab, replay="synthetic_upstream_rain", at="2024-11-27 12:00")
    c.type("#q", "Is Kota Bharu safe tonight?")
    c.ask("#ask button[type=submit]", MADEUP)
    c.answer_tour()
    c.look("#a-rain-box2")
    c.details()
    c.pause()


def clip_d(c):
    """The Critic -> Data request in the live log (made-up silent upstream gauge, Pasir Mas)."""
    lab = f"{MADEUP} · silent upstream gauge (made-up river levels)"
    home(c, lab, replay="synthetic_silent_upstream", at="2024-06-15 10:00")
    run_id = c.ask_town("Pasir Mas", MADEUP)
    c.look("#a-badge")
    c.go("/live", lab + " · live log", run=run_id, speed="1")
    c.page.wait_for_selector("#status:has-text('finished')", timeout=60000)
    c.scroll(0)
    c.pause()
    c.look("#feed li.req", 4)
    c.scroll_through()
    c.pause()


def clip_e(c):
    """The Normal and Can't-confirm states."""
    home(c, f"{MADEUP} · calm day (made-up river levels)", replay="synthetic_calm", at="2024-06-15 10:00")
    c.ask_town("Tumpat", MADEUP)
    c.look("#a-badge")
    c.look("#s-answer .todo")
    c.details()
    c.tap("#home-link")
    home(c, f"{REPLAY} · 26 Nov 2024, 18:00 (no reported Tumpat reading)", replay="nov2024", at="2024-11-26 18:00")
    c.ask_town("Tumpat", REPLAY)
    c.look("#a-badge")
    c.look("#s-answer .todo")
    c.details()


def clip_f(c):
    """Emergency: from the Can't-confirm answer, and from Home (no engine call)."""
    home(c, f"{REPLAY} · 26 Nov 2024, 18:00 (no reported Tumpat reading)", replay="nov2024", at="2024-11-26 18:00")
    c.ask_town("Tumpat", REPLAY)
    c.look("#a-badge")
    c.tap("#a-sos")
    c.label("Emergency screen · no data, no engine call")
    c.pause(LOOK)
    c.scroll_through()
    c.tap("#e-back")
    c.tap("#sos", hold=LOOK)


CLIPS = {  # key: (file stem, what it shows, data source)
    "a": ("a-replay-rantau-panjang",
          "Home → the map → tap Rantau Panjang → waiting → answer → Details → How VEDA worked this out",
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


def to_mp4(webm, scale=1):
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    mp4 = webm.with_suffix(".mp4")
    vf = ["-vf", f"scale=iw*{scale}:ih*{scale}:flags=lanczos"] if scale != 1 else []
    subprocess.run([ff, "-y", "-v", "error", "-i", str(webm), *vf, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "23", "-preset", "slow", "-movflags", "+faststart", "-an", str(mp4)], check=True)
    return mp4


def record(key, base, tmp, shared, size):
    stem = f"{CLIPS[key][0]}-{size}"
    viewport = SIZES[size][0]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=viewport, record_video_dir=str(tmp), record_video_size=viewport,
                                  color_scheme="light", locale="en-GB")
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
        for size in SIZES:
            files = [f for f in (OUT / f"{stem}-{size}.webm", OUT / f"{stem}-{size}.mp4") if f.exists()]
            if not files:
                continue
            secs = seconds(files[0])
            mb = sum(f.stat().st_size for f in files) / 1e6
            names = " / ".join(f"`{f.name}`" for f in files)
            rows.append(f"| {key} | {size} px | {names} | {secs if secs is not None else '?'} s | {what} | {data} | "
                        f"{mb:.1f} MB |")
    text = f"""# Demo video clips

Made by `scripts/record_demo.py` (Playwright, Chromium headless) from VEDA's own web page, at {made} from commit
`{base_commit}`. Two sizes: **375 px** (a phone, 375x812; the mp4 scaled 2x, about 750x1624) and **1440 px** (a desktop,
1440x900: the two-column layout), webm and mp4 (H.264).

**Recording style (the same as the live clips):** a visible pointer (a dark dot with a light ring) glides to each
target and shows a ripple on the click; a typed question appears letter by letter ({TYPE_MS} ms a key) with a 2 s pause
before Ask; {PAUSE:g} s after every tap; slow smooth scrolling (~{SCROLL_PX_S} px/s); about {LOOK:g} s on the map, the
verdict, WHAT TO DO, the gauge post, the upstream strip and Details; clip (a) switches the answer to BM for {LOOK:g} s
and back. The pointer and the pill at the bottom left (naming the data the clip runs on) are added by the recorder; they
are not part of VEDA's page.

**Offline recordings (SAMPLE_MODE):** no network, no Zetaris, no Nightshift. So **no clip shows an AI explanation**
(the card is written and checked by code; offline the models are replaced by the agents' code fallbacks), and the
step timings are offline timings (a run takes about 0.1 s). **While each question runs, the recorder slows the
browser's download to {SLOW_BYTES_S} bytes a second**, so the real step lines arrive one by one in "See what VEDA is
doing" (opened right after Ask) and the answer comes in about 10 s; a live run waits for real (up to 150 s). No JPS
reading appears in any clip: every answer is checked to carry the "Past flood replay" or "Made-up test scene" label,
or the clip is dropped.

| Clip | Screen | Files | Length | What it shows | Data | Size |
|---|---|---|---|---|---|---|
""" + "\n".join(rows) + """

## To re-record live (with the AI explanation) - Session A / Husaini
Live = Zetaris + Nightshift running, Nemotron 3.5 Super VL by name, still on the **Nov 2024 replay** (never live JPS
data; delete Nightshift's VEDA memory records first, as for the 24 Oct screenshots):
- **a** - the answer's "In plain words" (AI explanation) and "How VEDA worked this out" with the served model,
  Nightshift receipt and real seconds; the waiting screen with a real wait.
- **b** - the live log with real "Waiting for Nemotron" bubbles and the two Nightshift calls (draft + Critic review).
- **c**, **d** - optional: the same scenes with the AI explanation (both are made-up scenes, labelled).
- **e**, **f** - no need: Normal (quick path) and Can't confirm use no AI, and Emergency makes no engine call.

## Making the clips again
Dev only (judges do not need this):
```
pip install -r requirements-dev.txt                 # VEDA's requirements + Playwright
python -m playwright install chromium               # the headless browser, once (~120 MB download)
SAMPLE_MODE=true VEDA_PORT=8001 python -m app.main  # in its own terminal (PowerShell: $env:SAMPLE_MODE="true" ...)
python scripts/record_demo.py                        # all clips; --only a,b for some
```
ffmpeg on PATH adds the mp4 copies and the lengths in this table.

**The video files are not in git** (`.gitignore`: too heavy for the public repo; the README table gives each size).
They stay in this folder on the recording machine and are uploaded with the submission.
"""
    (OUT / "README.md").write_text(text, encoding="utf-8", newline="\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    ap.add_argument("--only", default=",".join(CLIPS), help="comma-separated clip keys, e.g. a,b")
    ap.add_argument("--sizes", default=",".join(SIZES), help="comma-separated screen widths: 375,1440")
    a = ap.parse_args()
    h = health(a.base)
    if not h.get("sample_mode"):
        sys.exit("refusing: the server is not in SAMPLE_MODE (a live run could show live JPS readings)")
    OUT.mkdir(parents=True, exist_ok=True)
    keys = [k.strip() for k in a.only.split(",") if k.strip() in CLIPS]
    sizes = [s.strip() for s in a.sizes.split(",") if s.strip() in SIZES]
    with tempfile.TemporaryDirectory() as tmp:
        for size in sizes:
            shared = {}                                  # (b) replays the (a) run made at the same size
            for key in keys:
                print(f"recording {key} ({CLIPS[key][0]}) at {size} px ...")
                webm = record(key, a.base, Path(tmp), shared, size)
                if webm:
                    mp4 = to_mp4(webm, SIZES[size][1])
                    print(f"  {key}: {webm.name}" + (f" + {mp4.name}" if mp4 else "") + f", {seconds(webm)} s")
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip()
    write_readme(time.strftime("%d %b %Y %H:%M MYT"), commit)


if __name__ == "__main__":
    main()
