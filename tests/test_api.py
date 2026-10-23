"""B-19 tests: the FastAPI entry points offline (SAMPLE_MODE, recorded fixtures) - /health, POST /run fields, the live
step stream, the web page, 400 on bad input, 429 while busy."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import gazetteer, main


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    real_run = main._run
    monkeypatch.setattr(main, "_run", lambda q, r, a, on_step=None: _in_tmp(real_run, tmp_path, q, r, a, on_step))
    yield TestClient(main.app)
    gazetteer.clear_cache()


def _in_tmp(real_run, tmp_path, question, replay, at, on_step):
    from app import loop
    return loop.run(question, quiet=True, replay=replay, at=at, on_step=on_step, log_dir=tmp_path)


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


def test_not_json_is_a_400(client):
    r = client.post("/run", content=b"question=Tumpat", headers={"Content-Type": "text/plain"})
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
    assert "CC BY 4.0" in r.text and "open-meteo.com" in r.text           # audit 23 Oct: data credits
    assert "Jabatan Pengairan dan Saliran (JPS) Malaysia" in r.text and "non-commercial" in r.text   # JPS credit
    assert "Jangan taip nama, IC" in r.text and "NVIDIA Nemotron" in r.text  # privacy notice, BM + EN


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
    assert "River (SYNTHETIC)" in r["answer"]["text"] and "SYNTHETIC river levels (not JPS)" in r["answer"]["text"]


def test_scene_picker_lists_replay_first_then_synthetic_scenes():
    page = (main.WEB_PAGE).read_text(encoding="utf-8")
    order = [page.index(x) for x in ("nov2024|2024-11-26 18:00", "synthetic_rising|", "synthetic_calm|")]
    assert order == sorted(order) and 'id="live-option"' in page and "h.sample_mode" in page
