"""B-70 tests: the Nov 2024 replay end to end, offline from the recorded fixtures - REPLAY title first, labels,
no hindsight (data, rain and historic peaks cut at the replay time), no 2026 MetMalaysia data, medium confidence on
approximate times, the 2014 comparison, the 240 s replay budget."""
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app import config, gazetteer, loop
from app.agents import critic, forecast_agent
from app.engines.world_model import veda_ingest

SCENE_1 = datetime(2024, 11, 26, 18, 0, tzinfo=config.MYT)
SCENE_2 = datetime(2024, 11, 27, 19, 30, tzinfo=config.MYT)


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    yield tmp_path
    gazetteer.clear_cache()


def approve_llm():
    def llm(lane, messages, agent, **kw):
        if lane == "deep":
            return SimpleNamespace(data={"decision": "approve", "problems": [], "fix": ""}, text="")
        return SimpleNamespace(data={"explanation": "The Golok was high and rising at the time."}, text="")
    return llm


def lines(r):
    return [json.loads(x) for x in open(r["trace"], encoding="utf-8")]


def test_replay_sql_is_cut_at_the_replay_time():
    q = veda_ingest.replay_sqls("nov2024", SCENE_1)
    assert "observed_at <= TIMESTAMP '2024-11-26 10:00:00'" in q["levels"]          # 18:00 MYT = 10:00 UTC
    assert "t <= '2024-11-26T18:00'" in q["rain"] and "t > '2024-11-19T18:00'" in q["rain"]
    with pytest.raises(ValueError):
        veda_ingest.replay_sqls("nov2024'; DROP", SCENE_1)


def test_scene_1_prepare_with_labels_and_no_hindsight(offline):
    r = loop.run("Rantau Panjang selamat ke malam ni?", llm=approve_llm(), log_dir=offline, quiet=True,
                 replay="nov2024", at=SCENE_1)
    text = r["answer"]["text"]
    assert text.split("\n")[0] == "REPLAY · Nov 2024"
    assert r["forecast"]["verdict"] == "PREPARE" and r["forecast"]["confidence"]["label"] == "medium"
    assert "bacaan JPS yang dilaporkan (Bernama" in text and "masa anggaran" in text
    assert "11.43" not in text and "10.94" not in text and "29 Nov" not in text          # later readings never leak
    assert "Berbanding 2014" in text and "tiada ramalan hujan dalam ulang tayang" in text
    assert r["evidence"]["sources"]["mygov_forecast"]["note"].startswith("not available in replay")
    events = [h["event"] for h in r["forecast"]["history"]]
    assert not any("2024" in e for e in events)                                          # peaks after 26 Nov hidden


def test_scene_2_act_and_the_2014_comparison(offline):
    r = loop.run("Is Rantau Panjang safe now?", llm=approve_llm(), log_dir=offline, quiet=True,
                 replay="nov2024", at=SCENE_2)
    assert r["forecast"]["verdict"] == "ACT" and r["answer"]["text"].startswith("REPLAY · Nov 2024")
    assert "Compared with 2014: 0.1 m above the Dec 2014 peak here (10.84 m)." in r["answer"]["text"]
    assert "reported JPS reading (Kosmo" in r["answer"]["text"]


def test_replay_trace_says_replay_and_uses_the_replay_budget(offline):
    r = loop.run("Is Rantau Panjang safe now?", llm=approve_llm(), log_dir=offline, quiet=True,
                 replay="nov2024", at=SCENE_2)
    rec = next(x for x in lines(r) if x["action"] == "replay")
    assert rec["output_summary"].startswith("REPLAY · Nov 2024 at 27 Nov 2024 19:30")
    assert "replay budget 240 s" in rec["decision"]
    timing = next(x for x in lines(r) if x["action"] == "timing")
    assert timing["details"]["budget_s"] == loop.REPLAY_BUDGET_S == 240


def test_unknown_replay_is_refused(offline):
    with pytest.raises(ValueError):
        loop.run("x", log_dir=offline, quiet=True, replay="dec2099", at=SCENE_1)


def test_critic_requires_the_replay_title():
    found = critic.code_checks("Rantau Panjang: ACT", {}, {"replay": {"scenario": "nov2024"}})
    assert any("REPLAY" in f["detail"] for f in found)


@pytest.mark.parametrize("peak, when", [
    ({"observed_when": "27 Nov 2024 19:30"}, "2024-11-27 19:30"),
    ({"observed_when": "29 Nov 2024"}, "2024-11-29 00:00"),
    ({"observed_when": "printed '1/12/2014 2:00' - ambiguous", "event": "Dec 2014"}, "2014-12-01 00:00"),
    ({"observed_when": "2014", "event": "Dec 2014 (as reported by Kosmo)"}, "2014-12-01 00:00"),
])
def test_peak_times_are_read(peak, when):
    assert forecast_agent.peak_time(peak).strftime("%Y-%m-%d %H:%M") == when


@pytest.mark.parametrize("value, expected", [("true", True), ("false", False), (True, True), (False, False),
                                             ("FALSE", False), ("t", True), (None, False)])
def test_text_booleans_from_zetaris(value, expected):
    assert veda_ingest._true(value) is expected
