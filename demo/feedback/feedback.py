"""VEDA public demo - feedback form (its own tiny service; Python standard library only, nothing to install).

    python feedback.py serve                      # http://0.0.0.0:8090/feedback  (FEEDBACK_FILE, FEEDBACK_PORT)
    python feedback.py export > feedback.csv      # every answer as one CSV (UTF-8)
    python feedback.py export --out feedback.csv  # the same, with a BOM so Excel opens Malay text correctly

Privacy: no IP address, phone, email or address is stored. The server writes no request log; free text has email
addresses and phone / IC-like digit runs replaced by "[removed]"; the time is kept to the minute. A first name is
optional and quoted only if its box is ticked (unticked by default). Answers append as JSON lines to FEEDBACK_FILE.

Abuse: control characters are dropped, one answer is at most MAX_RECORD bytes, a form sent from another website is
refused, and the CSV export defuses cells a spreadsheet would run as a formula. One visitor can send at most
VISITOR_MAX answers in a rolling VISITOR_WINDOW (audit A-P3-30, so one visitor cannot fill the box for everyone): the
proxy passes its rate-limit key in the X-Veda-Visitor header; it is hashed at once with a random salt that lives in
memory only and is replaced every VISITOR_WINDOW, and only the hash and the answer times are kept, in memory - never
the address, never on disk.

Frame (B-96): the page wears VEDA's shared top bar, demo strip and footer - app/frame.py, the same file the app uses
(standard library only; the image copies it with app/config.py, see Dockerfile). /frame.css and /frame.js come from
VEDA through the proxy.
"""
import argparse
import csv
import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

for _root in Path(__file__).resolve().parents[:3]:          # /srv in the image, or the repo root (demo/feedback/..)
    if (_root / "app" / "frame.py").is_file():
        sys.path.insert(0, str(_root))
        break
from app import frame  # noqa: E402 - VEDA's shared frame

FILE = os.environ.get("FEEDBACK_FILE", "/data/answers.jsonl")
MAX_BODY = 8 * 1024                     # a filled-in form is well under 4 KB
MAX_TEXT = 500
MAX_NAME = 40
MAX_PLACE = 60                          # "Which place?" - the same as the form's maxlength
MAX_RECORD = 3 * 1024                   # one stored answer, in bytes (eight full answers fit)
MAX_FILE = 20 * 1024 * 1024             # stop accepting once the file is this big (about 10 000 answers)
PLACES = ("Rantau Panjang", "Pasir Mas", "Kota Bharu", "Tumpat", "other")
SHARE = ("yes", "maybe", "no")
AGES = ("under 30", "30-49", "50-64", "65+")
FIELDS = ("time", "lang", "place", "place_other", "would_do", "confusing", "share", "share_why", "ease",
          "should_add", "age", "first_name", "quote_ok")
TEXTS = ("would_do", "confusing", "share_why", "should_add")
VISITOR_HEADER = "X-Veda-Visitor"       # set by the proxy only (demo/nginx.conf, location /feedback)
VISITOR_MAX = 10                        # answers per visitor ...
VISITOR_WINDOW = 24 * 3600              # ... in a rolling 24 h; the salt is replaced as often, so no hash outlives it
_lock = threading.Lock()
_salt = {"key": secrets.token_bytes(32), "born": time.monotonic()}
_seen = {}                              # visitor hash -> times of their answers (memory only)

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE = re.compile(r"\+?\d[\d\s-]{5,}\d")          # 7+ digits with spaces / dashes: phone, IC
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
FORMULA = ("=", "+", "-", "@", "\t", "\r")           # a spreadsheet would run a cell starting with these

T = {
    "en": {"title": "Tell us what you think", "intro": "Eight short questions about VEDA's demo. Everything is optional. "
           "Please don't write your phone number, email or address.",
           "q1": "Which place did you check?", "other": "Other", "other_name": "Which place?",
           "q2": "After reading the answer, what would you do?", "q3": "Was anything confusing?",
           "q4": "Would you share this with your family group?", "yes": "Yes", "maybe": "Maybe", "no": "No",
           "why": "Why?", "q5": "How easy was it?", "hard": "1 = hard", "easy": "5 = easy",
           "q6": "One thing VEDA should add?", "q7": "Age range (optional)", "skip": "Prefer not to say",
           "q8": "First name (optional)", "quote": "OK to quote my first name and answer in VEDA's presentation",
           "send": "Send", "thanks": "Thank you!",
           "thanks_body": "Your answer is saved. It helps us make VEDA clearer for families in Kelantan.",
           "empty": "Please answer at least one question.",
           "full": "Sorry, the feedback box is full for now, so this answer was not saved. Please try again later.",
           "limit": "Thank you - you have already sent several answers today. Please send more tomorrow.",
           "too_long": "That was too long - please shorten it.",
           "cross_site": "Please send this form from VEDA's own feedback page.",
           "privacy": "We store only your answers and the time (to the minute) - no IP address, phone or email."},
    "ms": {"title": "Beritahu pendapat anda", "intro": "Lapan soalan ringkas tentang demo VEDA. Semuanya pilihan. "
           "Mohon jangan tulis nombor telefon, e-mel atau alamat anda.",
           "q1": "Tempat mana yang anda semak?", "other": "Lain-lain", "other_name": "Tempat mana?",
           "q2": "Selepas membaca jawapan, apa yang akan anda buat?", "q3": "Ada apa-apa yang mengelirukan?",
           "q4": "Adakah anda akan kongsi ini dalam <i>group</i> keluarga?", "yes": "Ya", "maybe": "Mungkin",
           "no": "Tidak", "why": "Kenapa?", "q5": "Adakah ia mudah digunakan?", "hard": "1 = susah",
           "easy": "5 = mudah", "q6": "Satu perkara yang VEDA patut tambah?", "q7": "Lingkungan umur (pilihan)",
           "skip": "Tidak mahu nyatakan", "q8": "Nama pertama (pilihan)",
           "quote": "Saya benarkan nama pertama dan jawapan saya dipetik dalam pembentangan VEDA",
           "send": "Hantar", "thanks": "Terima kasih!",
           "thanks_body": "Jawapan anda telah disimpan. Ia membantu kami menjadikan VEDA lebih jelas untuk keluarga "
           "di Kelantan.", "empty": "Sila jawab sekurang-kurangnya satu soalan.",
           "full": "Maaf, peti maklum balas penuh buat masa ini, jadi jawapan ini tidak disimpan. Sila cuba lagi nanti.",
           "limit": "Terima kasih - anda sudah menghantar beberapa jawapan hari ini. Sila hantar lagi esok.",
           "too_long": "Terlalu panjang - sila pendekkan.",
           "cross_site": "Sila hantar borang ini dari halaman maklum balas VEDA sendiri.",
           "privacy": "Kami simpan jawapan anda dan masa (hingga minit) sahaja - tiada alamat IP, telefon atau e-mel."},
}

CSS = """:root{--bg:#f6f5f1;--fg:#1c1c1a;--muted:#55554f;--card:#fff;--line:#d6d5cf;--accent:#1f5f8b;--on-accent:#fff;
--danger:#b3261e}@media (prefers-color-scheme:dark){:root{--bg:#151514;--fg:#eeeeea;--muted:#b0b0a9;--card:#212120;
--line:#3b3b38;--accent:#82b8de;--on-accent:#151514;--danger:#f08a80}}*{box-sizing:border-box}html{font-size:18px}
body{margin:0;background:var(--bg);color:var(--fg);font:1rem/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:640px;margin:0 auto;padding:16px 16px 40px}
h1{font-size:1.45rem;margin:8px 0 12px}fieldset{border:1px solid var(--line);border-radius:14px;
background:var(--card);margin:12px 0;padding:12px 16px}legend{font-weight:700;padding:0 4px}
label.opt{display:flex;align-items:center;gap:12px;min-height:44px;min-width:44px;padding:4px 0;cursor:pointer}
input[type=radio],input[type=checkbox]{flex:none;width:28px;height:28px;margin:0;accent-color:var(--accent)}
.scale{display:grid;grid-template-columns:repeat(5,minmax(44px,1fr));gap:4px}.scale label.opt{flex-direction:column;gap:2px;
justify-content:center;font-weight:700}
textarea,input[type=text]{font:inherit;width:100%;min-height:48px;padding:10px 12px;border:1px solid var(--muted);
border-radius:12px;background:var(--card);color:var(--fg)}textarea{min-height:88px}.row{display:flex;flex-wrap:wrap;gap:4px 16px}
.note{color:var(--muted)}button,.btn{font:inherit;min-height:48px;width:100%;padding:10px 16px;border-radius:12px;
border:1px solid var(--accent);background:var(--accent);color:var(--on-accent);font-weight:700;display:inline-flex;
align-items:center;justify-content:center;text-decoration:none;margin-top:8px}.err{border-left:6px solid var(--danger);padding:8px 12px;background:var(--card)}
:focus-visible{outline:3px solid var(--accent);outline-offset:2px}"""


def lang_of(query, accept):
    q = (query.get("lang") or [""])[0]
    if q in T:
        return q
    return "ms" if (accept or "").lower().lstrip().startswith(("ms", "id")) else "en"


def page(lang, title, body):
    """One page in VEDA's shared frame (public demo: the strip and the Feedback link). The frame's EN | BM reloads
    the page with ?lang= (/frame.js)."""
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width, initial-scale=1"><title>{html.escape(title)} - VEDA</title>'
            f'<link rel="icon" href="data:,"><style>{CSS}</style></head><body>{frame.top("feedback", demo=True)}'
            f'<main>{body}</main>{frame.foot(public_demo=True)}</body></html>')


def form_page(lang, error=""):
    t = T[lang]
    radios = lambda name, items: "".join(                                            # noqa: E731
        f'<label class="opt"><input type="radio" name="{name}" value="{html.escape(v)}"> {html.escape(lbl)}</label>'
        for v, lbl in items)
    places = [(p, t["other"] if p == "other" else p) for p in PLACES]
    body = (f'<h1>{t["title"]}</h1><p class="note">{t["intro"]}</p>'
            + (f'<p class="err" role="alert">{html.escape(error)}</p>' if error else "")
            + f'<form method="post" action="/feedback?lang={lang}">'
            f'<input type="hidden" name="lang" value="{lang}">'
            f'<fieldset><legend>1. {t["q1"]}</legend>{radios("place", places)}'
            f'<label for="po" class="note">{t["other_name"]}</label>'
            f'<input type="text" id="po" name="place_other" maxlength="{MAX_PLACE}"></fieldset>'
            f'<fieldset><legend><label for="q2">2. {t["q2"]}</label></legend>'
            f'<textarea id="q2" name="would_do" maxlength="{MAX_TEXT}"></textarea></fieldset>'
            f'<fieldset><legend><label for="q3">3. {t["q3"]}</label></legend>'
            f'<textarea id="q3" name="confusing" maxlength="{MAX_TEXT}"></textarea></fieldset>'
            f'<fieldset><legend>4. {t["q4"]}</legend><div class="row">'
            f'{radios("share", [(s, t[s]) for s in SHARE])}</div>'
            f'<label for="q4w" class="note">{t["why"]}</label>'
            f'<input type="text" id="q4w" name="share_why" maxlength="{MAX_TEXT}"></fieldset>'
            f'<fieldset><legend>5. {t["q5"]}</legend><div class="scale">'
            f'{radios("ease", [(str(i), str(i)) for i in range(1, 6)])}</div>'
            f'<p class="note">{t["hard"]} · {t["easy"]}</p></fieldset>'
            f'<fieldset><legend><label for="q6">6. {t["q6"]}</label></legend>'
            f'<textarea id="q6" name="should_add" maxlength="{MAX_TEXT}"></textarea></fieldset>'
            f'<fieldset><legend>7. {t["q7"]}</legend>{radios("age", [(a, a) for a in AGES] + [("", t["skip"])])}'
            f'</fieldset>'
            f'<fieldset><legend><label for="q8">8. {t["q8"]}</label></legend>'
            f'<input type="text" id="q8" name="first_name" maxlength="{MAX_NAME}" autocomplete="off">'
            f'<label class="opt"><input type="checkbox" name="quote_ok" value="yes"> {t["quote"]}</label></fieldset>'
            f'<p class="note">{t["privacy"]}</p><button type="submit">{t["send"]}</button></form>')
    return page(lang, t["title"], body)


def thanks_page(lang):
    t = T[lang]
    return page(lang, t["thanks"], f'<h1>{t["thanks"]}</h1><p>{t["thanks_body"]}</p>')   # back: VEDA in the top bar


def clean_text(s, limit):
    s = " ".join(CONTROL.sub(" ", s or "").split())[:limit]
    return PHONE.sub("[removed]", EMAIL.sub("[removed]", s))


def record(form, now=None):
    """Form fields -> one stored answer, or raise ValueError(key of the message to show)."""
    one = lambda k: (form.get(k) or [""])[0]                                         # noqa: E731
    if any(len(one(k)) > MAX_TEXT for k in TEXTS) or len(one("first_name")) > MAX_NAME \
            or len(one("place_other")) > MAX_PLACE:
        raise ValueError("too_long")
    rec = {
        "time": (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%MZ"),
        "lang": one("lang") if one("lang") in T else "en",
        "place": one("place") if one("place") in PLACES else "",
        "share": one("share") if one("share") in SHARE else "",
        "ease": int(one("ease")) if one("ease") in ("1", "2", "3", "4", "5") else None,
        "age": one("age") if one("age") in AGES else "",
        "first_name": clean_text(one("first_name"), MAX_NAME),
        "place_other": clean_text(one("place_other"), MAX_PLACE),
    }
    for k in TEXTS:
        rec[k] = clean_text(one(k), MAX_TEXT)
    rec["quote_ok"] = one("quote_ok") == "yes" and bool(rec["first_name"])
    answered = [k for k in ("place", "share", "age", "first_name", "place_other", *TEXTS) if rec[k]] \
        + (["ease"] if rec["ease"] else [])
    if not answered:
        raise ValueError("empty")
    rec = {k: rec[k] for k in FIELDS}
    if len(json.dumps(rec, ensure_ascii=False).encode("utf-8")) > MAX_RECORD:
        raise ValueError("too_long")
    return rec


def cross_site(headers):
    """True when a browser says the form was sent from another website (same rule as VEDA's /run/stream).
    curl and scripts send neither header; the proxy's rate limit covers them."""
    site = headers.get("Sec-Fetch-Site")
    if site and site not in ("same-origin", "none"):
        return True
    origin = headers.get("Origin")
    if not origin or origin == "null":                  # "null": a same-site form under Referrer-Policy no-referrer
        return False
    host = (headers.get("Host") or "").rsplit(":", 1)[0].lower()
    return (urlsplit(origin).hostname or "") != host


def safe_cell(v):
    return "'" + v if isinstance(v, str) and v.startswith(FORMULA) else v


def _recent(visitor, now):
    """-> (hash, this visitor's answer times in the window). Call with _lock held. `visitor` (the proxy's key) is
    hashed at once and dropped; every VISITOR_WINDOW the salt is replaced and every count forgotten."""
    if now - _salt["born"] >= VISITOR_WINDOW:
        _salt.update(key=secrets.token_bytes(32), born=now)
        _seen.clear()
    key = hmac.new(_salt["key"], visitor.encode("utf-8", "replace"), hashlib.sha256).hexdigest()[:16]
    return key, [t for t in _seen.get(key, ()) if now - t < VISITOR_WINDOW]


def over_cap(visitor, now=None):
    """True when this visitor already sent VISITOR_MAX answers in the last VISITOR_WINDOW. Only looks: an answer is
    counted by count_answer() after it is saved (audit A-P3-39: a 'box full' failure must not spend a slot). No key
    (a direct request, not through the proxy) is never capped."""
    if not visitor:
        return False
    now = time.monotonic() if now is None else now
    with _lock:
        key, times = _recent(visitor, now)
        _seen[key] = times
        return len(times) >= VISITOR_MAX


def count_answer(visitor, now=None):
    """Count one SAVED answer against this visitor's cap."""
    if not visitor:
        return
    now = time.monotonic() if now is None else now
    with _lock:
        key, times = _recent(visitor, now)
        _seen[key] = times + [now]


def append(rec, path=None):
    path = path or FILE
    with _lock:
        if os.path.exists(path) and os.path.getsize(path) > MAX_FILE:
            raise ValueError("full")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def export(path, out):
    w = csv.DictWriter(out, fieldnames=FIELDS, extrasaction="ignore")
    w.writeheader()
    n = 0
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    w.writerow({k: safe_cell(v) for k, v in json.loads(line).items()})
                    n += 1
    return n


class Handler(BaseHTTPRequestHandler):
    server_version = "veda-feedback"
    sys_version = ""

    def log_message(self, *args):          # no request log: it would hold IP addresses
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _lang(self):
        return lang_of(parse_qs(urlsplit(self.path).query), self.headers.get("Accept-Language"))

    def do_GET(self):
        path = urlsplit(self.path).path.rstrip("/")
        if path == "/feedback":
            return self._send(200, form_page(self._lang()))
        if path == "/feedback/thanks":
            return self._send(200, thanks_page(self._lang()))
        if path == "/feedback/health":
            return self._send(200, "ok", "text/plain; charset=utf-8")
        return self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        lang = self._lang()
        if urlsplit(self.path).path.rstrip("/") != "/feedback":
            return self._send(404, "not found", "text/plain; charset=utf-8")
        try:
            size = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            size = MAX_BODY + 1
        if size > MAX_BODY:
            return self._send(413, form_page(lang, T[lang]["too_long"]))
        if cross_site(self.headers):
            return self._send(403, form_page(lang, T[lang]["cross_site"]))
        form = parse_qs(self.rfile.read(size).decode("utf-8", "replace"), keep_blank_values=True)
        lang = (form.get("lang") or [lang])[0] if (form.get("lang") or [""])[0] in T else lang
        try:
            rec = record(form)                         # a form with no answer is refused before it counts
            visitor = self.headers.get(VISITOR_HEADER)
            if over_cap(visitor):
                return self._send(429, form_page(lang, T[lang]["limit"]))
            append(rec)
            count_answer(visitor)                      # only a saved answer spends a slot (A-P3-39)
        except ValueError as e:
            key = str(e) if str(e) in T[lang] else "empty"
            return self._send(400 if key != "full" else 503, form_page(lang, T[lang][key]))
        self._send(303, "", headers={"Location": f"/feedback/thanks?lang={lang}"})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("serve")
    ex = sub.add_parser("export")
    ex.add_argument("--file", default=FILE)
    ex.add_argument("--out", help="write a CSV file (with a BOM, for Excel) instead of stdout")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        port = int(os.environ.get("FEEDBACK_PORT", "8090"))
        ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
    elif a.out:
        with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
            print(f"{export(a.file, f)} answers -> {a.out}", file=sys.stderr)
    else:
        buf = io.StringIO()
        n = export(a.file, buf)
        sys.stdout.write(buf.getvalue())
        print(f"{n} answers", file=sys.stderr)


if __name__ == "__main__":
    main()
