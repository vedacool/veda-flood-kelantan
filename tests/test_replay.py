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
    assert "bacaan JPS dilaporkan (Bernama" in text and "masa anggaran" in text
    assert "26 Nov 18:00; masa anggaran" in text or "(Bernama, 26 Nov" in text       # the reading time stays
    assert "11.43" not in text and "10.94" not in text and "29 Nov" not in text          # later readings never leak
    assert "Berbanding 2014" in text                       # the 2014 line is never trimmed (rain may be, ~750 cap)
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


# -- audit 23 Oct: no hindsight from reconstructed rows ------------------------------------------------------
def _row(hour, kind, level):
    return {"kind": kind, "level_m": level, "t": datetime(2024, 11, 27, hour)}


def test_reconstructed_rows_toward_a_later_reading_are_dropped():
    rows = [_row(1, "reported", 8.0), _row(2, "reconstructed", 8.1), _row(3, "reported", 8.2),
            _row(4, "reconstructed", 8.5), _row(5, "reconstructed", 8.8)]       # 4 and 5 lean on a later anchor
    assert [r["t"].hour for r in veda_ingest.known_by_then(rows)] == [1, 2, 3]


def test_the_newest_replay_reading_is_always_a_reported_one():
    assert veda_ingest.known_by_then([_row(4, "reconstructed", 8.5)]) == []


def test_the_scene_inside_the_gap_cannot_see_the_peak(offline):
    res = loop.run("Rantau Panjang selamat ke?", llm=approve_llm(), log_dir=offline, quiet=True, replay="nov2024",
                   at=datetime(2024, 11, 27, 8, 0, tzinfo=config.MYT))
    text = res["answer"]["text"]
    assert res["forecast"]["verdict"] == "INSUFFICIENT_DATA" and "8.41 m" in text
    assert "10.94" not in text and "19:30" not in text and "dibina semula" not in text


def test_critic_rechecks_the_replay_table_in_a_replay():
    sql = critic._raw_sql("_DPMS0003", {"scenario": "nov2024", "at": "2024-11-27T19:30:00+08:00"})
    assert "veda_pg.replay_levels" in sql and "kind = 'reported'" in sql
    assert "TIMESTAMP '2024-11-27 11:30:00'" in sql                              # MYT 19:30 = UTC 11:30
    assert "river_levels" in critic._raw_sql("_DPMS0003", None)


def test_above_danger_shows_direction_not_numbers(offline):
    """Husaini 23 Oct: 27 Nov 19:30 (10.94 m, Danger 9 m) - no 13.75-14.54 m range, 'masih naik' + 2014."""
    r = loop.run("Rantau Panjang selamat ke?", llm=approve_llm(), log_dir=offline, quiet=True, replay="nov2024",
                 at=SCENE_2)
    text, c = r["answer"]["text"], r["card"]
    assert c["above_danger"] and c["range_24h"] is None
    assert "24 jam akan datang: masih naik, melebihi paras 2014." in text
    assert "13.75" not in text and "14.54" not in text
    facts = __import__("app.card", fromlist=["key_facts"]).key_facts(c, r["forecast"], "ms")
    assert "next_24h" not in facts and facts["trend"] == "naik"
