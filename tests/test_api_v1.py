"""B-92: the public API (/api/v1) and the CLI (python -m veda) - the same agent loop as the web page, offline."""
import importlib
import json
import subprocess
import sys

import pytest
from starlette.testclient import TestClient

from app import api, config, gazetteer, main, trace

QUESTION = "Is Kota Bharu at risk in the next two days?"


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    monkeypatch.delenv("VEDA_DEMO", raising=False)
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    if trace.current_run():
        trace.end_run()
    yield
    gazetteer.clear_cache()


def test_ask_works_with_no_keys_and_equals_the_web_flow(offline):
    c = TestClient(main.app)
    r = c.post("/api/v1/ask", json={"question": QUESTION, "lang": "bm", "scene": "synthetic_rising"})
    assert r.status_code == 200
    a = r.json()
    assert a["mode"] == "offline sample" and a["ai_judgement"] == "live mode only" and a["language"] == "en"
    assert a["level"] == "WATCH" and a["level_label"] == {"en": "Keep watching", "bm": "Terus berjaga-jaga"}
    web = c.post("/run", json={"question": QUESTION, "replay": "synthetic_rising"}).json()   # the web page's call
    assert a["level"] == web["verdict"] and a["text"] == web["output"]
    assert a["what_to_do"][0] == web["view"]["action"]["ms"][0]                                  # lang=bm -> BM words
    assert {s["source"] for s in a["facts_used"]} | {s["source"] for s in a["facts_left_out"]} == \
        {s["name"] for s in web["view"]["sources"]["ms"]}
    assert a["critic_checks"]["checks"] and [s["agent"] for s in a["steps"]][:3] == \
        ["Coordinator", "Data & Reconciler", "Forecast"]


def test_scenes_and_health(offline):
    c = TestClient(main.app)
    sc = c.get("/api/v1/scenes").json()["scenes"]
    assert {s["id"] for s in sc} == set(config.REPLAYS) and all(s["title"] and s["source"] for s in sc)
    assert c.get("/api/v1/health").json()["sample_mode"] is True


def test_trapped_question_gets_the_emergency_words_first(offline):
    a = TestClient(main.app).post("/api/v1/ask", json={"question": "I am trapped by water in Tumpat"}).json()
    assert "999" in a["text"].split("\n")[0] or "999" in a["text"][:300]
    assert a["emergency"] is True


def test_emergency_flag_on_a_path_with_no_card(offline):
    """Audit 26 Oct A-P2-11: place not covered (no card) - the stranded advice comes first AND the flag is true."""
    a = TestClient(main.app).post("/api/v1/ask", json={"question": "I am trapped by water in Gua Musang"}).json()
    assert a["level"] is None and a["text"].startswith("If you are stranded") and a["emergency"] is True
    calm = TestClient(main.app).post("/api/v1/ask", json={"question": "Is Gua Musang at risk?"}).json()
    assert calm["emergency"] is False


@pytest.mark.parametrize("kw, status, code", [
    ({"json": {"question": ""}}, 400, "empty_question"),
    ({"json": {"question": "x" * 301}}, 400, "question_too_long"),
    ({"json": {"question": "Tumpat?", "lang": "fr"}}, 400, "bad_lang"),
    ({"json": {"question": "Tumpat?", "scene": "atlantis"}}, 400, "unknown_scene"),
    ({"json": ["Tumpat?"]}, 400, "bad_json"),
    ({"content": "{not json", "headers": {"content-type": "application/json"}}, 400, "bad_json"),
    ({"content": "question=Tumpat", "headers": {"content-type": "text/plain"}}, 415, "json_only"),
    ({"content": json.dumps({"question": "Tumpat?", "pad": "x" * 5000}), "headers": {"content-type": "application/json"}},
     413, "body_too_large"),
])
def test_bad_input_is_a_json_4xx(offline, kw, status, code):
    r = TestClient(main.app).post("/api/v1/ask", **kw)
    assert r.status_code == status and r.json()["error"]["code"] == code


def test_busy_is_429(offline):
    assert main._busy.acquire(blocking=False)
    try:
        r = TestClient(main.app).post("/api/v1/ask", json={"question": "Tumpat?"})
        assert r.status_code == 429 and r.json()["error"]["code"] == "busy"
    finally:
        main._busy.release()


def test_demo_mode_docs_show_only_the_public_api(monkeypatch):
    monkeypatch.setenv("VEDA_DEMO", "1")
    importlib.reload(main)
    try:
        c = TestClient(main.app)
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert c.get(path).status_code == 404, path
        schema = c.get("/api/openapi.json").json()
        assert set(schema["paths"]) == {"/v1/ask", "/v1/scenes", "/v1/health"}
        assert not any(k in json.dumps(schema) for k in ("/admin", "/trace/run", "admin/api/approve"))
        assert schema["paths"]["/v1/ask"]["post"]["requestBody"]["content"]["application/json"]["example"]
        docs = c.get("/api/docs")
        assert docs.status_code == 200 and "/api/openapi.json" in docs.text
    finally:
        monkeypatch.delenv("VEDA_DEMO")
        importlib.reload(main)


def test_operator_routes_are_in_no_schema(monkeypatch):
    monkeypatch.delenv("VEDA_DEMO", raising=False)
    paths = TestClient(main.app).get("/openapi.json").json()["paths"]
    assert not [p for p in paths if p.startswith(("/admin", "/trace/run"))]


def test_cli_exits_0_with_no_keys_and_says_offline(offline, monkeypatch, capsys):
    import veda.__main__ as cli
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)        # as on a fresh clone: no .env
    monkeypatch.delenv("SAMPLE_MODE")
    assert cli.main(["ask", "Is Tumpat safe tonight?", "--json"]) == 0
    out = capsys.readouterr()
    assert out.err.startswith("Offline sample mode (") and "ZETARIS_API_URL" in out.err.splitlines()[0]   # B-104 rule
    assert json.loads(out.out)["mode"] == "offline sample"
    assert cli.main(["ask", ""]) == 2


def test_python_m_veda_runs(offline):
    env = {k: v for k, v in __import__("os").environ.items() if not k.startswith(("ZETARIS_", "METERLESS_"))}
    env.update(SAMPLE_MODE="true", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-m", "veda", "scenes"], cwd=config.ROOT, env=env, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0 and "synthetic_rising" in r.stdout and r.stderr.startswith("Offline sample mode")


def test_ask_takes_an_optional_time_inside_the_scene(offline):
    """Audit 27 Oct A-P3-33: 'at' with a scene, checked like the CLI's --at; the Nov 2024 peak can be asked."""
    c = TestClient(main.app)
    peak = c.post("/api/v1/ask", json={"question": "Is Rantau Panjang at risk?", "scene": "nov2024",
                                       "at": "2024-11-27 19:30"}).json()
    assert peak["level"] == "ACT"
    for body, code in (({"scene": "nov2024", "at": "27/11/2024"}, "bad_time"),
                       ({"scene": "nov2024", "at": "2030-01-01 00:00"}, "outside_replay"),
                       ({"at": "2024-11-27 19:30"}, "at_without_replay")):
        r = c.post("/api/v1/ask", json={"question": "Is Rantau Panjang at risk?", **body})
        assert r.status_code == 400 and r.json()["error"]["code"] == code, body


@pytest.mark.parametrize("ctype", ["text/plain;application/json", "text/plain; x=application/json",
                                   "application/jsonx", "application/json-patch+json"])
def test_only_exactly_application_json_is_accepted(offline, ctype):
    """Audit 27 Oct A-P3-29 (closes A-P3-8): a browser's no-preflight 'simple' form never passes."""
    c = TestClient(main.app)
    for path in ("/api/v1/ask", "/run"):
        r = c.post(path, content=json.dumps({"question": "Tumpat?"}), headers={"content-type": ctype})
        assert r.status_code == 415, (path, ctype)
    ok = c.post("/api/v1/ask", content=json.dumps({"question": "Is Tumpat at risk?"}),
                headers={"content-type": "application/json; charset=utf-8"})
    assert ok.status_code == 200


@pytest.mark.parametrize("field, value", [("question", ["Tumpat?"]), ("lang", ["en"]), ("lang", {"x": 1}),
                                          ("scene", ["nov2024"]), ("scene", {"a": 1}), ("at", 1930)])
def test_wrong_type_json_is_a_422_never_a_500(offline, field, value):
    """Audit 27 Oct A-P3-7: a list / object / number in a text field."""
    c = TestClient(main.app)
    body = {"question": "Is Tumpat at risk?", field: value}
    r = c.post("/api/v1/ask", json=body)
    assert r.status_code == 422 and r.json()["error"]["code"] == "wrong_type" and field in r.json()["error"]["message"]
    run_field = {"scene": "replay"}.get(field, field)
    r2 = c.post("/run", json={"question": "Is Tumpat at risk?", run_field: value})
    assert r2.status_code == 422 and r2.json()["error"]["code"] == "wrong_type"
