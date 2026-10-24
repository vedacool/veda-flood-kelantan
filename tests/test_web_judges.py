"""B-90: the "For judges" page (/judges) shows only the published, redacted recorded live runs - never a live or
unredacted JPS level - and works offline, live and in the public demo."""
import csv
import importlib.util
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import config, trace
from app.main import app

PAGE = (trace.ROOT / "app" / "web" / "judges.html").read_text(encoding="utf-8")
TRACES = trace.ROOT / "data" / "sample" / "live_traces"
METRES = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s?m(?![m\w])")


def cited_levels():
    """The only metre values allowed anywhere: the JPS thresholds and the historic peaks VEDA cites."""
    keep = set()
    for r in csv.DictReader((trace.ROOT / "data" / "stations_mapping.csv").open(encoding="utf-8")):
        keep |= {round(float(v), 2) for k, v in r.items() if k.startswith("jps") and k.endswith("_m") and v}
    for r in csv.DictReader((trace.ROOT / "data" / "historic_peaks.csv").open(encoding="utf-8")):
        keep.add(round(float(r["peak_m"]), 2))
    return keep


def numeric_levels(obj, path=()):
    """(key path, value) for every number under a level-like key (*_m, *level*), at any depth."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from numeric_levels(v, path + (str(k),))
    elif isinstance(obj, list):
        for v in obj:
            yield from numeric_levels(v, path)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool) and path:
        key = path[-1].lower()
        if key.endswith("_m") or "level" in key:
            yield ".".join(path), obj


@pytest.fixture()
def client():
    return TestClient(app)


def test_page_is_served_offline_and_in_the_public_demo(client, monkeypatch):
    r = client.get("/judges")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"] and 'id="judges"' in r.text
    monkeypatch.setattr(config, "demo_mode", lambda: True)          # VEDA_DEMO=1: /admin and run logs are closed
    assert client.get("/judges").status_code == 200 and client.get("/trace/recorded").status_code == 200
    assert client.get("/admin").status_code == 404


def test_the_page_itself_holds_no_level_and_reads_only_the_recorded_runs():
    assert METRES.findall(re.sub(r"<svg.*?</svg>", "", PAGE, flags=re.S)) == []          # no metre value at all
    fetched = re.findall(r'fetch\("([^"]+)"', PAGE)
    assert fetched and all(f.startswith("/trace/recorded") for f in fetched), fetched
    for closed in ("/trace/run/", "/live/stream", "/run/stream", "/admin", "/run\"", "logs/"):
        assert closed not in PAGE, closed


def test_every_served_recorded_run_is_redacted(client):
    """What /judges shows comes only from /trace/recorded: no metre value and no numeric level that is not a cited
    threshold or peak, in any field (the raw view shows every field)."""
    keep, runs = cited_levels(), client.get("/trace/recorded").json()
    assert len(runs) == len(list(TRACES.glob("*.jsonl"))) >= 18
    for run in runs:
        body = client.get(f"/trace/recorded/{run['name']}").json()
        assert "not redistributed" in body["note"]
        text = json.dumps(body["records"], ensure_ascii=False)
        assert "[JPS reading — not redistributed]" in text, run["name"]
        left = [m.group(0) for m in METRES.finditer(text) if round(float(m.group(1)), 2) not in keep]
        assert left == [], (run["name"], left[:5])
        bad = [(p, v) for rec in body["records"] for p, v in numeric_levels(rec) if round(float(v), 2) not in keep]
        assert bad == [], (run["name"], bad[:5])


def test_featured_runs_exist_and_are_labelled_as_recorded():
    for key in re.findall(r'"(\d{6}-[0-9a-f]{4})": "why_', PAGE):
        assert any(key in f.name for f in TRACES.glob("*.jsonl")), key
    assert 'label: "Recorded live run · {when} MYT"' in PAGE and 'label: "Larian langsung dirakam · {when} MYT"' in PAGE


def test_english_and_malay_have_the_same_words():
    ui = PAGE.split("const UI = {", 1)[1].split("\n};", 1)[0]
    en, ms = ui.split("\n  ms: {", 1)
    keys = lambda block: set(re.findall(r"(?:^|[{,]|\n)\s*([a-z_0-9]+): (?=[\"\[{])", block))   # noqa: E731
    assert keys(en) - {"en"} == keys(ms) and len(keys(ms)) > 30


def test_repo_link_is_the_one_the_publishing_sweep_rewrites():
    spec = importlib.util.spec_from_file_location("public_links", trace.ROOT / "scripts" / "public_links.py")
    pl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pl)
    assert f'const REPO = "{pl.PRIVATE}";' in PAGE and pl.LINK.search(PAGE)
    assert "README.md#how-it-works" in PAGE and "docs/EVIDENCE.md" in PAGE
