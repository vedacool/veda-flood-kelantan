"""/admin (Cowork weekend plan B8, 24 Oct): this computer only, never the question, counts from the World Model and the
run's own trace, approve guarded; the exact prompt sent to the AI is kept whole in the local trace."""
import json
import shutil
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from app import admin, config, main
from app.adapters import nightshift
from tests.test_nightshift import FakeResponse, fake, ok_payload  # noqa: F401 - fixture

RECORDED = next((config.ROOT / "data" / "sample" / "live_traces").glob("*2341MYT*.jsonl"))
RID = "20261023-234156-dd79"


@pytest.fixture
def logs(tmp_path, monkeypatch):
    monkeypatch.setattr(admin, "LOGS", tmp_path)
    shutil.copy(RECORDED, tmp_path / f"trace-{RID}.jsonl")
    return tmp_path


def test_every_admin_route_is_this_computer_only():
    far = TestClient(main.app, client=("192.168.1.20", 5000))
    assert far.get("/admin").status_code == 403
    assert far.get("/admin/api/overview").status_code == 403
    assert far.get(f"/admin/api/run/{RID}").status_code == 403
    assert far.post("/admin/api/approve", json={}).status_code == 403


def test_overview_in_sample_mode_lists_runs_without_the_question(logs, monkeypatch):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    o = TestClient(main.app).get("/admin/api/overview").json()
    assert o["sample_mode"] and o["growth"] is None and o["discovered"] == []
    row = next(r for r in o["recent"] if r["run_id"] == RID)
    assert row["place"] == "Rantau Panjang" and row["verdict"] == "WATCH" and row["ai_calls"] == 2
    question = json.loads(RECORDED.read_text(encoding="utf-8").splitlines()[1])["input_summary"]
    assert question not in json.dumps(o, ensure_ascii=False)


def test_run_detail_from_a_recorded_live_run(logs):
    d = TestClient(main.app).get(f"/admin/api/run/{RID}").json()
    assert [a["served"] for a in d["ai"]] == ["nvidia/nemotron-3.5-super-vl-120b-a12b"] * 2
    assert all(a["receipt"] for a in d["ai"])
    assert d["world_counts"]["events_written"] == 67 and d["world_counts"]["reads"] == 3
    assert len(d["sql"]) == 16 and all(q["sql"].startswith("SELECT") for q in d["sql"])
    question = json.loads(RECORDED.read_text(encoding="utf-8").splitlines()[1])["input_summary"]
    assert question not in json.dumps(d, ensure_ascii=False)
    assert TestClient(main.app).get("/admin/api/run/..%2F.env").status_code == 404


def test_approve_is_guarded(monkeypatch):
    c = TestClient(main.app)
    assert c.post("/admin/api/approve", json={"station_key": "x"}).status_code == 400          # no admin header
    monkeypatch.setenv("SAMPLE_MODE", "true")
    r = c.post("/admin/api/approve", json={"station_key": "x", "place_id": "tumpat", "by": "A"},
               headers={"X-VEDA-Admin": "1"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "sample_mode"


def test_growth_counts_come_from_the_world_model():
    ents = {"a": {"type": "station"}, "b": {"type": "station"}, "c": {"type": "place"}}
    world = SimpleNamespace(store=SimpleNamespace(state={"entities": ents}))
    found = [{"status": "discovered", "place_id": "tumpat"}, {"status": "discovered", "place_id": None},
             {"status": "approved", "place_id": "pasir_mas"}]
    srcs = [{"id": "mygov_flood", "name": "flood feed", "excluded": True, "status": "stale"},
            {"id": "open_meteo", "name": "rain", "excluded": False, "status": "ok"}]
    g = admin.growth(world, found, srcs)
    assert (g["mapped"], g["found"], g["waiting_near_towns"], g["approved"], g["left_out"]) == (2, 3, 1, 1, ["flood feed"])
    assert admin.growth(None, [], []) is None


def test_the_exact_prompt_is_kept_whole_in_the_local_trace(fake):
    system = "Line one of the instructions.\n" + "x" * 900 + "\nLast line."
    fake["queue"].append(FakeResponse(200, ok_payload('{"explanation": "ok"}')))
    nightshift.chat(nightshift.AI_LANE, [{"role": "system", "content": system}, {"role": "user", "content": '{"FACTS": {}}'}],
                    agent="Coordinator", json_mode=True)
    from app import trace
    rec = [json.loads(x) for x in trace.current_run().path.read_text(encoding="utf-8").splitlines()][-1]
    assert rec["action"] == "nightshift.chat"
    assert rec["details"]["prompt"] == [{"role": "system", "content": system}, {"role": "user", "content": '{"FACTS": {}}'}]


def test_admin_page_is_self_contained():
    import re
    page = TestClient(main.app).get("/admin").text
    assert "Found by VEDA · waiting for a person" in page and "only facts written by code" in page
    assert "Sources · the network grows, with approval" in page and '"X-VEDA-Admin": "1"' in page
    assert not re.search(r'<(script|link)[^>]+(src|href)="https?:', page)


def test_recent_answers_show_the_final_verdict_after_a_recompute(tmp_path, monkeypatch):
    """Session B bug (24 Oct): the silent-upstream Pasir Mas run was listed NORMAL while the answer said WATCH."""
    from datetime import datetime
    from app import gazetteer, loop
    monkeypatch.setenv("SAMPLE_MODE", "true")
    monkeypatch.setattr(admin, "LOGS", tmp_path)
    gazetteer.clear_cache()
    r = loop.run("Pasir Mas banjir tak esok?", quiet=True, replay="synthetic_silent_upstream",
                 at=datetime(2024, 6, 15, 10, 0, tzinfo=config.MYT), log_dir=tmp_path)
    gazetteer.clear_cache()
    assert r["forecast"]["verdict"] == "WATCH"
    end = [json.loads(x) for x in open(r["trace"], encoding="utf-8")][-1]
    assert end["action"] == "run_end" and end["details"]["verdict"] == "WATCH"
    assert end["details"]["first_verdict"] == "NORMAL" and end["details"]["recomputed_from"] == "NORMAL"
    row = admin.summary(tmp_path / f"trace-{r['run_id']}.jsonl")
    assert row["verdict"] == "WATCH" and row["recomputed_from"] == "NORMAL"


def test_old_traces_without_run_end_verdict_use_the_last_verdict_line(tmp_path):
    lines = [{"action": "run_start", "run_id": "r", "timestamp": "2026-10-24T01:00:00Z"},
             {"action": "forecast.verdict", "input_summary": "Pasir Mas", "output_summary": "NORMAL (confidence high, 0.85)"},
             {"action": "forecast.verdict", "input_summary": "Pasir Mas", "output_summary": "WATCH (confidence high, 0.8)"},
             {"action": "run_end", "status": "success", "details": {"ai_fallbacks": []}}]
    p = tmp_path / "trace-old.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    row = admin.summary(p)
    assert row["verdict"] == "WATCH" and row["recomputed_from"] == "NORMAL"
