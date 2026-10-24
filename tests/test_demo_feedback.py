"""The public demo's feedback form (demo/feedback/feedback.py): what is stored, what is refused, the export."""
import csv
import importlib.util
import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("feedback", Path(__file__).resolve().parents[1] / "demo" / "feedback" /
                                              "feedback.py")
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)


def form(**kw):
    return {k: [v] for k, v in kw.items()}


def test_record_keeps_answers_and_removes_phone_and_email():
    r = fb.record(form(lang="ms", place="Tumpat", would_do="Telefon mak 012-345 6789 dulu",
                       share_why="emel saya ali@example.com", share="maybe", ease="4", age="65+",
                       first_name="Ali", quote_ok="yes"),
                  now=datetime(2026, 10, 26, 10, 15, 42, tzinfo=timezone.utc))
    assert r["time"] == "2026-10-26T10:15Z"                             # to the minute only
    assert r["place"] == "Tumpat" and r["share"] == "maybe" and r["ease"] == 4 and r["age"] == "65+"
    assert "[removed]" in r["would_do"] and "345" not in r["would_do"]
    assert "@" not in r["share_why"]
    assert r["quote_ok"] is True
    assert list(r) == list(fb.FIELDS)                                    # nothing else (no IP, no headers)


def test_quote_needs_a_name_and_is_off_by_default():
    assert fb.record(form(place="Pasir Mas", quote_ok="yes"))["quote_ok"] is False
    assert fb.record(form(place="Pasir Mas", first_name="Siti"))["quote_ok"] is False
    assert 'type="checkbox" name="quote_ok" value="yes">' in fb.form_page("en")     # unticked: no "checked"
    assert "checked" not in fb.form_page("en")


def test_unknown_choices_are_dropped_and_empty_or_long_answers_refused():
    r = fb.record(form(place="Mars", share="sure", ease="9", age="12", would_do="ok"))
    assert (r["place"], r["share"], r["ease"], r["age"]) == ("", "", None, "")
    with pytest.raises(ValueError, match="empty"):
        fb.record(form(lang="en", place="", would_do="   "))
    with pytest.raises(ValueError, match="too_long"):
        fb.record(form(would_do="x" * (fb.MAX_TEXT + 1)))


def test_language_from_query_then_phone():
    assert fb.lang_of({}, "ms-MY,ms;q=0.9,en;q=0.8") == "ms"
    assert fb.lang_of({}, "en-GB") == "en"
    assert fb.lang_of({"lang": ["en"]}, "ms-MY") == "en"
    ms = fb.form_page("ms")
    assert "Tempat mana yang anda semak?" in ms
    assert "dalam <i>group</i> keluarga" in ms and "Lingkungan umur (pilihan)" in ms       # Cowork BM review 24 Oct
    assert "Saya benarkan nama pertama dan jawapan saya dipetik dalam pembentangan VEDA" in ms
    assert "Mohon jangan tulis nombor telefon, e-mel atau alamat anda." in ms              # Cowork review 24 Oct
    assert "Please don't write your phone number, email or address." in fb.form_page("en")


def test_choices_are_easy_to_tap_and_the_scale_stays_on_one_row():
    """Every radio / checkbox sits inside its label (the whole label is the tap target, at least 44 x 44 px) and the
    1-5 scale is a five-column grid, so "5" never wraps onto its own line on a 320 px phone."""
    page = fb.form_page("en")
    boxes = page.count('type="radio"') + page.count('type="checkbox"')
    assert boxes == 5 + 3 + 5 + 5 + 1 and page.count('<label class="opt"><input type=') == boxes
    assert "label.opt{display:flex;align-items:center;gap:12px;min-height:44px;min-width:44px" in fb.CSS
    assert "input[type=radio],input[type=checkbox]{flex:none;width:28px;height:28px" in fb.CSS   # never shrinks
    assert ".scale{display:grid;grid-template-columns:repeat(5,minmax(44px,1fr))" in fb.CSS
    scale = page.split('<div class="scale">', 1)[1].split("</div>", 1)[0]
    assert [f'value="{i}"' in scale for i in range(1, 6)] == [True] * 5


def test_export_is_one_csv_with_every_answer(tmp_path):
    path = tmp_path / "answers.jsonl"
    fb.append(fb.record(form(place="Kota Bharu", should_add="peta, PPS")), path)
    fb.append(fb.record(form(place="other", place_other="Machang")), path)
    out = io.StringIO()
    assert fb.export(path, out) == 2
    rows = list(csv.DictReader(io.StringIO(out.getvalue())))
    assert [r["place"] for r in rows] == ["Kota Bharu", "other"] and rows[0]["should_add"] == "peta, PPS"


def test_full_file_refuses_more(tmp_path, monkeypatch):
    path = tmp_path / "answers.jsonl"
    path.write_text("x" * 100, encoding="utf-8")
    monkeypatch.setattr(fb, "MAX_FILE", 50)
    with pytest.raises(ValueError, match="full"):
        fb.append(fb.record(form(place="Tumpat")), path)


def test_control_characters_are_dropped_and_one_answer_is_at_most_3_kb():
    """Audit 24 Oct: control characters were stored as 6-byte \\uXXXX, ~15 KB per answer."""
    r = fb.record(form(would_do="a" + "\x00\x01\x1b\x7f" * 100 + "b", place_other="Machang\x07"))
    assert r["would_do"] == "a b" and r["place_other"] == "Machang"
    full = {k: "x" * fb.MAX_TEXT for k in fb.TEXTS}
    assert len(json.dumps(fb.record(form(**full))).encode()) <= fb.MAX_RECORD     # eight full answers still fit
    with pytest.raises(ValueError, match="too_long"):
        fb.record(form(**{k: "é" * fb.MAX_TEXT for k in fb.TEXTS}))                 # 2 bytes a character: too big
    with pytest.raises(ValueError, match="too_long"):
        fb.record(form(place_other="x" * (fb.MAX_PLACE + 1)))                        # 60, the same as the form
    assert f'name="place_other" maxlength="{fb.MAX_PLACE}"' in fb.form_page("en") and fb.MAX_PLACE == 60


def test_csv_export_defuses_spreadsheet_formulas(tmp_path):
    path = tmp_path / "answers.jsonl"
    for text in ('=HYPERLINK("http://example.invalid","x")', "+1", "-2", "@SUM(A1)", "peta"):
        fb.append(fb.record(form(would_do=text)), path)
    out = io.StringIO()
    fb.export(path, out)
    cells = [r["would_do"] for r in csv.DictReader(io.StringIO(out.getvalue()))]
    assert cells == ["'=HYPERLINK(\"http://example.invalid\",\"x\")", "'+1", "'-2", "'@SUM(A1)", "peta"]
    assert fb.safe_cell("\tx") == "'\tx" and fb.safe_cell("\rx") == "'\rx" and fb.safe_cell(4) == 4


def test_cross_site_detection():
    same = {"Host": "wyse5070.example.ts.net"}
    assert not fb.cross_site(same)                                                  # curl: neither header
    assert not fb.cross_site({**same, "Sec-Fetch-Site": "same-origin", "Origin": "https://wyse5070.example.ts.net:8443"})
    assert not fb.cross_site({**same, "Origin": "null"})                            # no-referrer same-site form
    assert fb.cross_site({**same, "Sec-Fetch-Site": "cross-site"})
    assert fb.cross_site({**same, "Sec-Fetch-Site": "same-site"})
    assert fb.cross_site({**same, "Origin": "https://evil.example"})


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(fb, "FILE", str(tmp_path / "answers.jsonl"))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), fb.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", tmp_path / "answers.jsonl"
    srv.shutdown()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def test_post_saves_and_redirects_to_thanks(server, capsys):
    base, path = server
    data = urllib.parse.urlencode({"lang": "en", "place": "Rantau Panjang", "share": "yes", "ease": "5"}).encode()
    req = urllib.request.Request(base + "/feedback", data=data, headers={"X-Forwarded-For": "203.0.113.9"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.build_opener(NoRedirect).open(req)
    assert e.value.code == 303 and e.value.headers["Location"] == "/feedback/thanks?lang=en"
    stored = path.read_text(encoding="utf-8")
    assert json.loads(stored)["place"] == "Rantau Panjang"
    assert "203.0.113.9" not in stored and "127.0.0.1" not in stored          # no address stored
    assert "127.0.0.1" not in capsys.readouterr().err                          # and no request log
    with urllib.request.urlopen(base + "/feedback/thanks?lang=ms") as r:
        assert "Terima kasih!" in r.read().decode()


def test_post_too_big_or_empty_is_refused(server):
    base, path = server
    for body, code in ((b"would_do=" + b"a" * (fb.MAX_BODY + 10), 413), (b"lang=en", 400)):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(base + "/feedback", data=body))
        assert e.value.code == code
    assert not path.exists()


def test_post_from_another_website_is_refused(server):
    base, path = server
    data = urllib.parse.urlencode({"lang": "ms", "place": "Tumpat"}).encode()
    for headers in ({"Sec-Fetch-Site": "cross-site"}, {"Origin": "https://evil.example"}):
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(base + "/feedback?lang=ms", data=data, headers=headers))
        assert e.value.code == 403 and "halaman maklum balas VEDA sendiri" in e.value.read().decode()
    assert not path.exists()
