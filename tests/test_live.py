"""The live log (Cowork weekend plan B6, 24 Oct): every trace record reaches /live as it happens, word for word but
without the question; a Nemotron call shows 'waiting' before its line; recorded runs replay; logs/ stay local."""
import asyncio
import json

import pytest
from starlette.testclient import TestClient

from app import gazetteer, main, trace
from app.adapters import nightshift
from tests.test_nightshift import FakeResponse, fake, ok_payload, trace_lines  # noqa: F401 - fixture


def test_notify_reaches_the_listener_without_a_trace_line(tmp_path):
    seen = []
    run = trace.start_run("q", log_dir=tmp_path, quiet=True, listener=seen.append)
    try:
        trace.notify("Coordinator", "ai.waiting", model="m")
    finally:
        trace.end_run()
    assert seen[-2]["action"] == "ai.waiting" and seen[-2]["transient"] and seen[-2]["details"] == {"model": "m"}
    lines = [json.loads(x)["action"] for x in run.path.read_text(encoding="utf-8").splitlines()]
    assert "ai.waiting" not in lines


def test_notify_outside_a_run_is_harmless():
    trace.notify("Coordinator", "ai.waiting")


def test_nemotron_call_says_waiting_before_its_line(fake):
    seen = []
    trace.current_run().listener = seen.append
    fake["queue"].append(FakeResponse(200, ok_payload('{"explanation": "x"}')))
    nightshift.chat(nightshift.AI_LANE, [{"role": "user", "content": "x"}], agent="Coordinator", json_mode=True)
    actions = [r["action"] for r in seen]
    assert actions.index("ai.waiting") < actions.index("nightshift.chat")
    wait = seen[actions.index("ai.waiting")]["details"]
    assert wait["expected"] == nightshift.expected_model(nightshift.AI_LANE) and wait["attempt"] == 1


def test_public_record_hides_the_question_and_redacts():
    rec = {"action": "run_start", "input_summary": "Mak saya 0123456789 di Tumpat", "trace_id": "x", "run_id": "r"}
    out = main.public_record(rec)
    assert out["input_summary"] == main.QUESTION_HIDDEN and "trace_id" not in out
    other = main.public_record({"action": "x", "output_summary": "call 012-3456789 now"})
    assert "3456789" not in other["output_summary"]


def test_a_run_is_published_to_live_watchers(monkeypatch, tmp_path):
    from app import loop
    monkeypatch.setenv("SAMPLE_MODE", "true")
    gazetteer.clear_cache()
    real = loop.run
    monkeypatch.setattr(loop, "run", lambda *a, **k: real(*a, **k, log_dir=tmp_path))
    class Direct:                                   # stands in for the event loop: hands the record over at once
        def call_soon_threadsafe(self, fn, *a):
            fn(*a)
    q = asyncio.Queue()
    entry = (Direct(), q)
    main._watchers.append(entry)
    try:
        main._run("Mak saya di Tumpat kodQZXWV, selamat ke?", "", None)
    finally:
        main._watchers.remove(entry)
        gazetteer.clear_cache()
    got = []
    while not q.empty():
        got.append(q.get_nowait())
    assert got[0]["action"] == "run_start" and got[-1]["action"] == "run_end"
    assert "kodQZXWV" not in json.dumps(got) and any(r["agent_name"] == "Forecast" for r in got)


def test_recorded_runs_list_and_load():
    c = TestClient(main.app)
    runs = c.get("/trace/recorded").json()
    assert len(runs) >= 10 and all(r["name"].endswith(".jsonl") and r["run_id"] for r in runs)
    one = c.get("/trace/recorded/" + runs[-1]["name"]).json()
    assert one["note"].startswith("JPS readings not redistributed") and one["records"][0]["action"] == "run_start"
    assert c.get("/trace/recorded/..%2F..%2F.env").status_code == 404
    assert c.get("/trace/recorded/nothing.jsonl").status_code == 404


def test_run_logs_are_local_only_and_hide_the_question(tmp_path, monkeypatch):
    monkeypatch.setattr(trace, "ROOT", tmp_path)
    (tmp_path / "logs").mkdir()
    rid = "20261024-101500-abcd"
    (tmp_path / "logs" / f"trace-{rid}.jsonl").write_text("\n".join(json.dumps(r) for r in (
        {"action": "run_start", "input_summary": "is Tumpat safe kodQZXWV", "run_id": rid},
        {"action": "gazetteer.resolve", "input_summary": "is Tumpat safe kodQZXWV", "run_id": rid,
         "details": {"normalized": "is tumpat safe kodqzxwv", "place_id": "tumpat"}})) + "\n", encoding="utf-8")
    local = TestClient(main.app).get(f"/trace/run/{rid}")
    assert local.status_code == 200 and "kodqzxwv" not in local.text.lower()
    assert local.json()["records"][1]["details"]["place_id"] == "tumpat"            # the rest stays word for word
    far = TestClient(main.app, client=("10.1.2.3", 5000)).get(f"/trace/run/{rid}")
    assert far.status_code == 403
    assert TestClient(main.app).get("/trace/run/..%2Fsecret").status_code == 404


def test_live_page_is_self_contained():
    import re
    page = TestClient(main.app).get("/live").text
    assert "VEDA · live log" in page and "/live/stream" in page and "Waiting for" in page
    assert not re.search(r'<(script|link)[^>]+(src|href)="https?:', page)
    assert 'data-speed="1"' in page and 'data-speed="4"' in page


def test_45_open_live_logs_never_slow_health(monkeypatch):
    """Audit 24 Oct P1-1: 45 held /live/stream connections froze /health (10 s). Now the streams are async, at most
    MAX_WATCHERS are accepted (503 above) and /health answers at once - on a real uvicorn server."""
    import socket
    import threading
    import time
    import uvicorn
    monkeypatch.setenv("SAMPLE_MODE", "true")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    socks, codes = [], []
    try:
        for _ in range(45):
            c = socket.create_connection(("127.0.0.1", port), timeout=5)
            c.sendall(b"GET /live/stream HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
            codes.append(c.recv(64).split(b" ")[1])
            socks.append(c)
        t0 = time.perf_counter()
        h = socket.create_connection(("127.0.0.1", port), timeout=5)
        h.sendall(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        reply = h.recv(4096)
        took = time.perf_counter() - t0
        h.close()
    finally:
        for c in socks:
            c.close()
        server.should_exit = True
    assert codes.count(b"200") == main.MAX_WATCHERS and codes.count(b"503") == 45 - main.MAX_WATCHERS
    assert b" 200 " in reply.split(b"\r\n")[0] + b" " and took < 2
