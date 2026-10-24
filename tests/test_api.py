"""B-19 tests: the FastAPI entry points offline (SAMPLE_MODE, recorded fixtures) - /health, POST /run fields, the live
step stream, the web page, 400 on bad input, 429 while busy."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import config, gazetteer, main


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    real_run = main._run
    monkeypatch.setattr(main, "_run", lambda q, r, a, on_step=None, lang=None: _in_tmp(real_run, tmp_path, q, r, a, on_step,
                                                                                        lang))
    yield TestClient(main.app)
    gazetteer.clear_cache()


def _in_tmp(real_run, tmp_path, question, replay, at, on_step, lang=None):
    from app import loop
    return loop.run(question, quiet=True, replay=replay, at=at, on_step=on_step, log_dir=tmp_path, lang_hint=lang)


def test_health_in_sample_mode(client):
    assert client.get("/health").json() == {"status": "ok", "sample_mode": True, "zetaris": "replay (offline)",
                                            "nightshift": "not used"}


def test_run_returns_the_official_fields(client):
    r = client.post("/run", json={"question": "Tumpat ok?"})
    assert r.status_code == 200
    body = r.json()
    for field in ("run_id", "status", "output", "agents", "trace_id", "log_file", "execution_time"):
        assert field in body, field
    assert body["status"] == "success" and body["verdict"] in ("NORMAL", "WATCH", "PREPARE", "ACT")
    assert body["trace_id"] == body["run_id"]
    assert "Not an official warning" in body["output"] and set(body["card"]) == {"en", "ms"}
    assert {"Coordinator", "Data & Reconciler", "Forecast", "Critic"} <= set(body["agents"])


def test_run_in_malay(client):
    body = client.post("/run", json={"question": "Tumpat selamat ke?"}).json()
    assert body["language"] == "ms" and body["output"].startswith("APA PERLU DIBUAT SEKARANG")
    assert body["disclaimer"]["ms"].startswith("Bukan amaran rasmi")


def test_run_a_replay_scene(client):
    body = client.post("/run", json={"question": "Is Rantau Panjang safe now?", "replay": "nov2024",
                                     "at": "2024-11-27 19:30"}).json()
    assert body["verdict"] == "ACT" and body["output"].startswith("REPLAY · Nov 2024")


@pytest.mark.parametrize("payload, code", [
    ({"question": ""}, "empty_question"),
    ({"question": "x" * 501}, "question_too_long"),
    ({"question": "Tumpat?", "replay": "dec2099"}, "unknown_replay"),
    ({"question": "Tumpat?", "replay": "nov2024", "at": "27/11/2024"}, "bad_time"),
    ({"question": "Tumpat?", "replay": "nov2024", "at": "2024-12-25 08:00"}, "outside_replay"),
    ({"question": "Tumpat?", "at": "2024-11-27 08:00"}, "at_without_replay"),
    (["not", "an", "object"], "bad_json"),
])
def test_bad_input_is_a_400_with_structured_json(client, payload, code):
    r = client.post("/run", json=payload)
    assert r.status_code == 400 and r.json()["error"]["code"] == code and r.json()["error"]["message"]


def test_not_json_is_refused(client):
    r = client.post("/run", content=b"question=Tumpat", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415 and r.json()["error"]["code"] == "json_only"            # A-P3-3: no form posts
    r = client.post("/run", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_json"


def test_second_run_while_busy_is_a_429(client):
    assert main._busy.acquire(blocking=False)
    try:
        r = client.post("/run", json={"question": "Tumpat ok?"})
        assert r.status_code == 429 and r.json()["error"]["code"] == "busy"
        assert client.get("/run/stream", params={"question": "Tumpat ok?"}).status_code == 429
    finally:
        main._busy.release()


def test_stream_sends_steps_live_then_the_result(client):
    events = []
    with client.stream("GET", "/run/stream", params={"question": "Tumpat ok?"}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for block in r.iter_text():
            events.append(block)
    text = "".join(events)
    kinds = [line[7:] for line in text.splitlines() if line.startswith("event: ")]
    assert kinds[0] == "step" and kinds[-1] == "result" and kinds.count("result") == 1
    data = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
    assert [d for d in data if "line" not in d][-1]["status"] == "success", [d for d in data if "line" not in d]
    steps = [d["line"] for d in data if "line" in d]
    assert any(s.startswith("> Checking river gauges") for s in steps)
    assert not main._busy.locked()                        # released after the run


def test_stream_bad_input_is_a_400(client):
    r = client.get("/run/stream", params={"question": ""})
    assert r.status_code == 400 and r.json()["error"]["code"] == "empty_question"


def test_web_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "VEDA - Kelantan flood check" in r.text and "/run/stream" in r.text
    assert not re.search(r"<(script|link|img|iframe)[^>]+(src|href)=\"https?://", r.text)   # nothing loaded from outside
    # audit 23 Oct: data credits - B-96: on /sources, linked from every page's footer
    assert 'href="/sources"' in r.text
    src = client.get("/sources").text
    assert "CC BY 4.0" in src and "open-meteo.com" in src
    assert "Jabatan Pengairan dan Saliran (JPS) Malaysia" in src and "non-commercial" in src   # JPS credit
    assert "Mohon jangan taip nama, IC" in r.text and "Your question is not sent to any AI model" in r.text   # BM + EN
    assert "Soalan anda tidak dihantar kepada mana-mana model AI" in r.text


def test_access_log_drops_the_question():
    import logging
    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("127.0.0.1:1", "GET", "/run/stream?question=call+0123456789", "1.1", 200), None)
    main._NoQueryString().filter(rec)
    assert rec.getMessage() == '127.0.0.1:1 - "GET /run/stream HTTP/1.1" 200'


# -- B-75: offline answers run on labelled scenes, never on JPS readings -----------------------------------------
def test_sample_mode_question_runs_on_the_synthetic_calm_day(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    from app import gazetteer
    gazetteer.clear_cache()
    r = main._run("Tumpat ok?", None, None)
    assert r["answer"]["text"].startswith("SYNTHETIC · calm day")
    assert "River (made-up test data · SYNTHETIC)" in r["answer"]["text"] and "made-up test river levels (SYNTHETIC, not JPS)" in r["answer"]["text"]


def test_scene_picker_lists_replay_first_then_synthetic_scenes():
    page = (main.WEB_PAGE).read_text(encoding="utf-8")
    order = [page.index(x) for x in ("nov2024|2024-11-26 18:00", "synthetic_rising|", "synthetic_calm|")]
    assert order == sorted(order) and 'k: "live"' in page and "h.sample_mode" in page
    assert 'sampleMode && d.k === "live"' in page               # B-75: no Live choice offline


def test_web_runs_write_progress_to_stdout_without_the_question(monkeypatch, tmp_path, capsys):
    """FAQ: 'Writes logs to stdout and logs/' - the web path prints one short line per step (docker logs), never
    the question text; the full trace still goes to the trace file."""
    from app import loop
    monkeypatch.setenv("SAMPLE_MODE", "true")
    gazetteer.clear_cache()
    real = loop.run
    monkeypatch.setattr(loop, "run", lambda *a, **k: real(*a, **k, log_dir=tmp_path))
    r = main._run("Mak saya di Tumpat, 0123456789, selamat ke?", "", None)
    out = capsys.readouterr().out
    assert f"[{r['run_id']}] > Understanding the question" in out and "verdict" in out
    assert "0123456789" not in out and "Mak saya" not in out
    assert (tmp_path / f"trace-{r['run_id']}.jsonl").exists()
    gazetteer.clear_cache()


def test_offline_time_without_recorded_data_gets_a_notice_not_a_verdict(monkeypatch):
    """Session B, 24 Oct: offline, data exists only at a scene's recorded times."""
    monkeypatch.setenv("SAMPLE_MODE", "true")
    c = TestClient(main.app)
    r = c.post("/run", json={"question": "Rantau Panjang?", "replay": "nov2024", "at": "2024-11-27 10:00"})
    err = r.json()["error"]
    assert r.status_code == 400 and err["code"] == "no_recorded_data"
    assert "No recorded data for this time in this scene; available times: 2024-11-26 18:00, 2024-11-27 08:00, " \
           "2024-11-27 19:30." in err["message"] and "Tiada data yang direkodkan" in err["message"]
    assert main.parse_input("Rantau Panjang?", "nov2024", "2024-11-27 19:30")[2] is not None   # a recorded time works


def test_live_mode_accepts_any_time_in_the_window(monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "false")
    assert main.parse_input("Rantau Panjang?", "nov2024", "2024-11-27 10:00")[1] == "nov2024"


def test_cli_offline_prints_the_notice(monkeypatch, capsys):
    import run
    monkeypatch.setenv("SAMPLE_MODE", "true")
    assert run.main(["run.py", "--replay", "nov2024", "--at", "2024-11-27 10:00", "Rantau Panjang?"]) == 2
    out = capsys.readouterr().out
    assert "available times: 2024-11-26 18:00" in out and "masa yang ada:" in out


def test_web_picker_offers_only_recorded_times():
    import re
    page = main.WEB_PAGE.read_text(encoding="utf-8")
    offered = re.findall(r'v: "(\w+)\|([0-9-]+ [0-9:]+)"', page)
    assert offered and all(at in config.REPLAYS[s]["scenes"] for s, at in offered), offered


def test_cli_at_outside_the_replay_window_gets_the_api_notice(monkeypatch, capsys):
    import run
    monkeypatch.setenv("SAMPLE_MODE", "false")
    assert run.main(["run.py", "--replay", "nov2024", "--at", "2024-12-25 08:00", "Rantau Panjang?"]) == 2
    assert "This replay covers 2024-11-26 08:00 to 2024-11-27 19:30 (MYT)." in capsys.readouterr().out
    assert run.main(["run.py", "--replay", "nov2024", "--at", "27/11/2024", "Rantau Panjang?"]) == 2
    assert "'at' must look like" in capsys.readouterr().out


# -- audit A-P2/A-P3 (24 Oct): security headers, JSON-only POST, no run from another site ------------------------
def test_security_headers_on_every_response(client):
    for path in ("/", "/live", "/health", "/ui/words", "/trace/recorded"):
        h = client.get(path).headers
        assert "frame-ancestors 'none'" in h["content-security-policy"] and "script-src 'self' 'unsafe-inline'" in             h["content-security-policy"], path
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer"


def test_a_link_on_another_site_cannot_start_a_run(client):
    q = "/run/stream?question=Tumpat%3F&replay=synthetic_calm&at=2024-06-15%2010:00"
    r = client.get(q, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "cross_site"
    assert client.get(q, headers={"Origin": "https://evil.example"}).status_code == 403
    ok = client.get(q, headers={"Sec-Fetch-Site": "same-origin"})
    assert ok.status_code == 200 and "event: result" in ok.text                        # the page's own request


def test_live_health_reports_postgres_newest_reading_and_open_breakers(monkeypatch):
    """A-P2-5: live /health also checks veda-pg, the newest reading's age and the open circuit breakers."""
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from app.adapters import pg, zetaris
    from app.agents import data_agent
    import app.engines.world_model as wm
    monkeypatch.setenv("SAMPLE_MODE", "false")
    monkeypatch.setattr(zetaris, "_post", lambda *a, **k: SimpleNamespace(ok=True))
    monkeypatch.setattr(main.requests, "get", lambda *a, **k: SimpleNamespace(ok=True))
    newest = datetime.now(timezone.utc) - timedelta(minutes=400)

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql):
            return SimpleNamespace(fetchone=lambda: (newest,))
    monkeypatch.setattr(pg, "connect", lambda *a, **k: Conn())
    monkeypatch.setattr(wm, "WorldModel", lambda **k: SimpleNamespace(store=SimpleNamespace(close=lambda: None)))
    until = datetime.now(timezone.utc) + timedelta(minutes=10)
    monkeypatch.setattr(data_agent, "_breaker_state", lambda w, k: (3, until) if k == "open_meteo" else (0, None))
    h = TestClient(main.app).get("/health").json()
    assert h["postgres"] == "ok" and h["newest_reading_age_min"] == 400 and h["newest_reading"] == "stale"
    assert h["open_breakers"] == ["open_meteo"] and h["status"] == "degraded"

    def down(*a, **k):
        raise pg.PgError("cannot reach veda-pg")
    monkeypatch.setattr(pg, "connect", down)
    assert TestClient(main.app).get("/health").json()["postgres"].startswith("unreachable")


def test_postgres_host_can_be_overridden_for_docker(monkeypatch):
    import importlib
    from app import config
    monkeypatch.setenv("VEDA_PG_HOST", "host.docker.internal")
    monkeypatch.setenv("VEDA_PG_PORT", "5544")
    importlib.reload(config)
    try:
        assert (config.PG_HOST, config.PG_PORT) == ("host.docker.internal", 5544)
    finally:
        monkeypatch.delenv("VEDA_PG_HOST")
        monkeypatch.delenv("VEDA_PG_PORT")
        importlib.reload(config)
    assert (config.PG_HOST, config.PG_PORT) == ("127.0.0.1", 5433)


def test_share_link_base_is_veda_public_url_when_set(monkeypatch):
    """Cowork 24 Oct: the share text's "Check it yourself" link never carries 127.0.0.1 / localhost when
    VEDA_PUBLIC_URL is set; without it, the request's own base URL."""
    c = TestClient(main.app, base_url="http://127.0.0.1:8002")
    monkeypatch.delenv("VEDA_PUBLIC_URL", raising=False)
    assert c.get("/ui/words").json()["public_url"] == "http://127.0.0.1:8002"
    monkeypatch.setenv("VEDA_PUBLIC_URL", "https://veda-demo.example.net/")
    url = c.get("/ui/words").json()["public_url"]
    assert url == "https://veda-demo.example.net" and "127.0.0.1" not in url and "localhost" not in url
    page = c.get("/").text
    assert "(words && words.public_url) || location.origin" in page and "await wordsReady" in page
