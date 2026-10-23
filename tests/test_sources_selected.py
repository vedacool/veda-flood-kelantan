"""B-71(a): the Data & Reconciler says which sources it chose for this place and which it skipped and why - one
`data.sources` trace line (details: chosen / skipped) and a short line in the live view."""
import json

import pytest

from app import gazetteer, loop, progress, router
from app.agents import data_agent


def _sources_line(r):
    return next(json.loads(x) for x in open(r["trace"], encoding="utf-8") if '"data.sources"' in x)


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    gazetteer.clear_cache()
    yield tmp_path
    gazetteer.clear_cache()


def test_full_path_lists_chosen_and_skipped_sources(offline, monkeypatch):
    monkeypatch.setattr(router, "data_triggers", lambda *a, **k: ["test: forced full"])
    r = loop.run("Is Tumpat safe tomorrow?", log_dir=offline, quiet=True)
    line = _sources_line(r)
    chosen, skipped = line["details"]["chosen"], line["details"]["skipped"]
    assert any("(controlling" in c for c in chosen) and line["agent_name"] == "Data & Reconciler"
    assert any(s.startswith("data.gov.my flood-warning") for s in skipped)       # the frozen feed: excluded, says why
    assert line["target_agent"] == "Forecast" and line["decision"].endswith("skipped")
    shown = progress.describe(line)
    assert shown.startswith("  sources: ") and "used" in shown and "skipped" in shown


def test_quick_path_says_the_cross_check_was_skipped(offline, monkeypatch):
    monkeypatch.setattr(router, "data_triggers", lambda *a, **k: [])
    r = loop.run("Tumpat ok?", log_dir=offline, quiet=True)
    assert r["plan"]["effort"] == "quick"
    assert "data.gov.my flood-warning cross-check: quick path" in _sources_line(r)["details"]["skipped"]


def test_replay_says_why_metmalaysia_is_skipped(offline):
    from datetime import datetime
    from app import config
    r = loop.run("Rantau Panjang bahaya ke esok?", log_dir=offline, quiet=True, replay="synthetic_rising",
                 at=datetime(2024, 11, 25, 18, 0, tzinfo=config.MYT))
    skipped = _sources_line(r)["details"]["skipped"]
    assert any(s.startswith("MetMalaysia warnings: not available in replay") for s in skipped)


def test_a_stale_or_broken_gauge_is_skipped_with_its_reason():
    g = {"name": "G", "role": "sentinel", "level_m": 3.0, "health": {"ok": True}, "freshness": "stale",
         "age_minutes": 400}
    bad = dict(g, name="H", freshness="fresh", health={"ok": False})
    none = dict(g, name="N", level_m=None)
    backup = dict(g, name="B", role="controlling", freshness="fresh", backup_for="A")
    out = data_agent.sources_selected({"effort": "full", "intent": "risk_check"},
                                      {"gauges": [backup], "sentinels": [g, bad, none]}, {}, None, None)
    assert out["chosen"] == ["B (controlling, backup for A)"]
    assert out["skipped"][:3] == ["G (upstream): reading too old (400 min)",
                                  "H (upstream): failed the plausibility check", "N (upstream): no reading"]
