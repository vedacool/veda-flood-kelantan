"""Tests for app/adapters/zetaris.py (B-04). Offline: HTTP is faked with monkeypatch.

The live test runs only with VEDA_LIVE=1 (real Zetaris, real .env).
"""
import json
import os

import pytest

from app import trace
from app.adapters import zetaris

FAKE_KEY = "zk" + "-test-" + "0123456789abcdef"  # assembled so the file holds no secret-shaped literal


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload = status, payload
        self.ok = 200 <= status < 300
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def rows_payload(headers, data):
    return {"headers": headers, "data": data, "total": len(data), "timeUsed": 5}


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setenv("ZETARIS_API_URL", "http://localhost:8888/api/v1.0")
    monkeypatch.setenv("ZETARIS_API_KEY", FAKE_KEY)
    monkeypatch.setenv("ZETARIS_ORG_ID", "1")
    monkeypatch.setenv("SAMPLE_MODE", "false")
    monkeypatch.setenv("ZETARIS_RECORD", "false")
    monkeypatch.setattr(zetaris, "FIXTURES", tmp_path / "fixtures")
    monkeypatch.setattr(zetaris, "_sleep", lambda s: None)
    state = {"queue": [], "calls": []}

    def post(url, headers=None, json=None, timeout=None):
        state["calls"].append({"url": url, "headers": headers, "body": json})
        item = state["queue"].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(zetaris.requests, "post", post)
    state["run"] = trace.start_run("test", log_dir=tmp_path, quiet=True)
    yield state
    if trace.current_run() is not None:
        trace.end_run()


def trace_lines(state):
    return [json.loads(x) for x in state["run"].path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("raw, expected", [
    ("72", 72), ("-3", -3), ("12.5", 12.5), ("0", 0), ("0.59", 0.59), ("1e3", 1000.0),
    ("0740121WL", "0740121WL"), ("0730671", "0730671"), ("2026-10-22 10:30", "2026-10-22 10:30"),
    ("", None), ("null", None), (None, None), ("Sg. Kelantan", "Sg. Kelantan"),
])
def test_coerce(raw, expected):
    assert zetaris.coerce(raw) == expected


def test_live_query_typed_rows_and_trace(fake):
    fake["queue"].append(FakeResponse(200, rows_payload(["station_id", "level_m", "updated"],
                                                        [["0740121WL", "7.47", "22/10/2026 10:30"]])))
    r = zetaris.run_sql("SELECT station_id, level_m, updated FROM veda_pg.river_levels;", agent="Data",
                        purpose="latest river levels")
    assert r.columns == ["station_id", "level_m", "updated"]
    assert r.rows == [["0740121WL", 7.47, "22/10/2026 10:30"]]
    assert r.records == [{"station_id": "0740121WL", "level_m": 7.47, "updated": "22/10/2026 10:30"}]
    assert r.source == "zetaris-live" and r.row_count == 1
    body, headers = fake["calls"][0]["body"], fake["calls"][0]["headers"]
    assert not body["sql"].endswith(";") and headers["X-Org-ID"] == "1"
    line = trace_lines(fake)[-1]
    assert line["action"] == "zetaris.run_sql" and line["input_summary"] == "latest river levels"
    assert line["details"]["query_hash"] == r.query_hash
    assert FAKE_KEY not in fake["run"].path.read_text(encoding="utf-8")


@pytest.mark.parametrize("sql", ["DROP TABLE x", "INSERT INTO t VALUES (1)", "SELECT 1; DROP TABLE x", "", "  ;  "])
def test_read_only_and_single_statement(fake, sql):
    with pytest.raises(zetaris.ZetarisError) as e:
        zetaris.run_sql(sql, agent="Data")
    assert e.value.kind == "not_allowed" and fake["calls"] == []


def test_semicolon_inside_string_is_fine(fake):
    fake["queue"].append(FakeResponse(200, rows_payload(["x"], [["a;b"]])))
    assert zetaris.run_sql("SELECT 'a;b' AS x", agent="Data").rows == [["a;b"]]


def test_record_then_replay_offline(fake, monkeypatch):
    sql = "SELECT station_id, level_m FROM veda_pg.river_levels"
    monkeypatch.setenv("ZETARIS_RECORD", "true")
    fake["queue"].append(FakeResponse(200, rows_payload(["station_id", "level_m"], [["0730671WL", "0.59"]])))
    live = zetaris.run_sql(sql, agent="Data")
    fixture = zetaris.FIXTURES / f"{live.query_hash}.json"
    assert fixture.exists() and json.loads(fixture.read_text(encoding="utf-8"))["rows"] == [["0730671WL", "0.59"]]

    monkeypatch.setenv("ZETARIS_RECORD", "false")
    monkeypatch.setenv("SAMPLE_MODE", "true")
    monkeypatch.delenv("ZETARIS_API_KEY")
    monkeypatch.delenv("ZETARIS_API_URL")
    replay = zetaris.run_sql("  SELECT station_id, level_m\n FROM veda_pg.river_levels ;", agent="Critic")
    assert replay.source == "zetaris-replay" and replay.rows == live.rows
    assert replay.fetched_at == live.fetched_at
    assert len(fake["calls"]) == 1  # replay never touched the network
    assert trace_lines(fake)[-1]["source"] == "zetaris-replay"


def test_replay_missing_fixture(fake, monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    with pytest.raises(zetaris.ZetarisError) as e:
        zetaris.run_sql("SELECT 42 AS answer", agent="Data")
    assert e.value.kind == "no_fixture" and fake["calls"] == []
    assert trace_lines(fake)[-1]["status"] == "failed"


def test_401_not_retried(fake):
    fake["queue"].append(FakeResponse(401, {"msg": "Unauthorized"}))
    with pytest.raises(zetaris.ZetarisError) as e:
        zetaris.run_sql("SELECT 1", agent="Data")
    assert e.value.kind == "auth" and "ZETARIS_API_KEY" in str(e.value) and len(fake["calls"]) == 1


def test_sql_error_not_retried(fake):
    fake["queue"].append(FakeResponse(400, {"msg": "[TABLE_OR_VIEW_NOT_FOUND] tpch.nation"}))
    with pytest.raises(zetaris.ZetarisError) as e:
        zetaris.run_sql("SELECT * FROM tpch.nation", agent="Data")
    assert e.value.kind == "sql" and "TABLE_OR_VIEW_NOT_FOUND" in str(e.value)


def test_rest_source_429_is_source_unavailable(fake):
    msg = "REST API call failed: Server returned HTTP response code: 429 for URL: https://api.data.gov.my/weather/warning/"
    fake["queue"].append(FakeResponse(400, {"msg": msg}))
    with pytest.raises(zetaris.ZetarisError) as e:
        zetaris.run_sql("SELECT * FROM veda_wx.mygov_warning", agent="Data")
    assert e.value.kind == "source_unavailable" and len(fake["calls"]) == 1


def test_network_errors_retried_then_fail(fake):
    fake["queue"] += [zetaris.requests.ConnectionError("down")] * 3
    with pytest.raises(zetaris.ZetarisError) as e:
        zetaris.run_sql("SELECT 1", agent="Data")
    assert e.value.kind == "network" and len(fake["calls"]) == 3
    assert [x["status"] for x in trace_lines(fake) if x["action"] == "zetaris.run_sql"] == \
        ["retrying", "retrying", "failed"]


def test_network_error_then_success(fake):
    fake["queue"] += [FakeResponse(503, {"msg": "busy"}), FakeResponse(200, rows_payload(["x"], [["1"]]))]
    assert zetaris.run_sql("SELECT 1 AS x", agent="Data").rows == [[1]]


def test_ddl_allow_list_and_already_exists(fake):
    with pytest.raises(zetaris.ZetarisError):
        zetaris.run_ddl("DROP DATASOURCE veda_pg", agent="Healer")
    fake["queue"] += [FakeResponse(200, rows_payload([], [])),
                      FakeResponse(400, {"msg": 'A table named "om_kb" already exists in database "VEDA_WX".'})]
    ddl = 'CREATE LIGHTNING REST TABLE om_kb FROM VEDA_WX REQUEST(endpoint "https://x")'
    assert zetaris.run_ddl(ddl, agent="Healer") is True
    assert zetaris.run_ddl(ddl, agent="Healer") is False
    assert [x["status"] for x in trace_lines(fake) if x["action"] == "zetaris.run_ddl"][-2:] == ["success", "success"]


def test_ddl_refused_in_sample_mode(fake, monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    with pytest.raises(zetaris.ZetarisError):
        zetaris.run_ddl("CACHE TABLE veda_wx.om_kb", agent="Healer")
    assert fake["calls"] == []


@pytest.mark.skipif(os.getenv("VEDA_LIVE") != "1", reason="live Zetaris test: set VEDA_LIVE=1")
def test_live_record_and_replay(tmp_path, monkeypatch):
    from dotenv import load_dotenv
    load_dotenv(trace.ROOT / ".env")
    monkeypatch.setattr(zetaris, "FIXTURES", tmp_path / "fixtures")
    monkeypatch.setenv("ZETARIS_RECORD", "true")
    monkeypatch.setenv("SAMPLE_MODE", "false")
    trace.start_run("live B-04 test", log_dir=tmp_path, quiet=True)
    try:
        sql = "SELECT 1 AS x, 'Pasir Mas' AS place, 2.50 AS level_m"
        live = zetaris.run_sql(sql, agent="Data")
        monkeypatch.setenv("SAMPLE_MODE", "true")
        monkeypatch.delenv("ZETARIS_API_KEY")
        replay = zetaris.run_sql(sql, agent="Data")
    finally:
        trace.end_run()
    assert live.rows == [[1, "Pasir Mas", 2.5]] and replay.rows == live.rows
    assert live.source == "zetaris-live" and replay.source == "zetaris-replay"
