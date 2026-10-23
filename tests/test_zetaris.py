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
    ("", None), ("null", None), (None, None), ("Sg. Kelantan", "Sg. Kelantan"), ("1e400", "1e400"),
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


@pytest.mark.parametrize("sql", [
    "WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x",
    "SELECT reflect('java.lang.Runtime','getRuntime')",
    "SELECT java_method('java.lang.System','exit',0)",
    "SELECT * INTO newt FROM veda_pg.stations",
    "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d",
    "SELECT 1 /* hide */ ; DROP LIGHTNING DATABASE TABLE veda.x",
    "SELECT '\\'' AS a; DROP LIGHTNING DATABASE TABLE veda.x --'",
    "SET spark.sql.x = 1",
])
def test_writes_and_tricks_refused(fake, sql):
    with pytest.raises(zetaris.ZetarisError) as e:
        zetaris.run_sql(sql, agent="Data")
    assert e.value.kind == "not_allowed" and fake["calls"] == []


def test_comment_does_not_swallow_where(fake):
    sql = "SELECT * FROM veda_pg.river_levels -- latest only\nWHERE station_key = 'X'"
    assert zetaris.normalize_sql(sql) == "SELECT * FROM veda_pg.river_levels WHERE station_key = 'X'"
    assert zetaris.normalize_sql("SELECT /* note */ 1") == "SELECT 1"


def test_literals_keep_their_spaces_and_words(fake):
    assert zetaris.normalize_sql("SELECT  'Kg  Baru'   AS p") == "SELECT 'Kg  Baru' AS p"
    assert zetaris.query_hash("SELECT 'Kg  Baru'") != zetaris.query_hash("SELECT 'Kg Baru'")
    # write words inside quotes are just text
    assert zetaris.read_only_problem("SELECT 'please DROP this' AS note, \"set\" FROM t") is None


def test_non_object_json_is_handled_not_crashed(fake):
    class ListResp(FakeResponse):
        pass
    fake["queue"] += [FakeResponse(200, ["not", "a", "dict"])] * 3
    with pytest.raises(zetaris.ZetarisError) as e:
        zetaris.run_sql("SELECT 1", agent="Data")
    assert e.value.kind == "network"
    fake["queue"].append(FakeResponse(429, ["rate", "limited"]))
    with pytest.raises(zetaris.ZetarisError) as e:
        zetaris.run_sql("SELECT 2", agent="Data")
    assert e.value.kind == "sql"


def test_row_column_mismatch_is_refused(fake):
    fake["queue"].append(FakeResponse(200, rows_payload(["a"], [["1", "2", "3"]])))
    with pytest.raises(zetaris.ZetarisError) as e:
        zetaris.run_sql("SELECT a FROM t", agent="Data")
    assert e.value.kind == "bad_response"


def test_budget_stops_retries(fake):
    fake["queue"] += [zetaris.requests.ConnectionError("down")] * 3
    with pytest.raises(zetaris.ZetarisError):
        zetaris.run_sql("SELECT 1", agent="Data", budget_s=1.5)   # first wait (2 s) would pass the budget
    assert len(fake["calls"]) == 1


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
    ddl = 'CREATE LIGHTNING REST TABLE om_kb FROM VEDA_WX REQUEST(endpoint "https://api.open-meteo.com/v1/forecast?x=1")'
    assert zetaris.run_ddl(ddl, agent="Healer") is True
    assert zetaris.run_ddl(ddl, agent="Healer") is False
    assert [x["status"] for x in trace_lines(fake) if x["action"] == "zetaris.run_ddl"][-2:] == ["success", "success"]


@pytest.mark.parametrize("ddl, setup", [
    ('CREATE LIGHTNING REST TABLE x FROM db REQUEST(endpoint "http://169.254.169.254/latest/meta-data")', False),
    ('CREATE LIGHTNING REST TABLE x FROM db REQUEST(endpoint "https://evil.example.com/a")', False),
    ('CREATE LIGHTNING REST TABLE x FROM db REQUEST(endpoint "http://api.open-meteo.com/v1")', False),  # not https
    ("CREATE OR REPLACE SCHEMASTORE VIEW river_status_latest WITH CONTAINER veda AS SELECT 99 AS level_m", False),
    ("DROP LIGHTNING DATABASE TABLE VEDA_WX.om_kb", False),
    ("REGISTER DATASOURCE TABLES FROM veda_pg", False),
    ('CREATE DATASOURCE x OPTIONS (jdbcdriver "d")', False),
    ("DROP DATASOURCE veda_pg", True),
])
def test_agent_ddl_lockdown(fake, ddl, setup):
    with pytest.raises(zetaris.ZetarisError) as e:
        zetaris.run_ddl(ddl, agent="Healer", setup=setup)
    assert e.value.kind == "not_allowed" and fake["calls"] == []


def test_setup_ddl_allowed_with_flag(fake):
    fake["queue"].append(FakeResponse(200, rows_payload([], [])))
    assert zetaris.run_ddl("REGISTER DATASOURCE TABLES FROM veda_pg", agent="Setup", setup=True) is True
    assert zetaris.ddl_problem("CACHE TABLE veda_wx.om_kb") is None


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


def test_recording_never_overwrites_a_synthetic_fixture(tmp_path, monkeypatch):
    """B-75: a live recording run must not put real rows back over a SYNTHETIC fixture."""
    import json as _json
    monkeypatch.setattr(zetaris, "FIXTURES", tmp_path)
    (tmp_path / "abc.json").write_text(_json.dumps({"sql": "x", "columns": ["a"], "rows": [["1"]],
                                                    "recorded_at": "t", "synthetic": True}), encoding="utf-8")
    assert zetaris._save_fixture("abc", "x", ["a"], [["real"]], "t2") is False
    assert _json.loads((tmp_path / "abc.json").read_text(encoding="utf-8"))["rows"] == [["1"]]
