"""Bug (Cowork 24 Oct): the Nov 2024 replay's Data & Reconciler line said "newest 2024-02-23 14:45 MYT ... 277 days old"
- today's data.gov.my /flood-warning feed treated as if it were what existed at the replay moment. data.gov.my keeps
no archive, so in a replay the feed is "not available in replay" (as the MetMalaysia feeds are) and nothing from it
is shown, compared or re-queried."""
import json
from datetime import datetime

from app import config, gazetteer, loop, view


def test_a_replay_never_shows_todays_flood_warning_feed(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    at = datetime.strptime("2024-11-26 18:00", "%Y-%m-%d %H:%M").replace(tzinfo=config.MYT)
    r = loop.run("Is Rantau Panjang at risk in the next two days?", replay="nov2024", at=at, log_dir=tmp_path,
                 quiet=True)
    text = open(r["trace"], encoding="utf-8").read()
    assert "2024-02-23" not in text and "277 days" not in text
    cross = [json.loads(x) for x in text.splitlines() if '"data.cross_check"' in x]
    assert cross and cross[0]["output_summary"] == "not available in replay"
    assert r["evidence"]["cross_check"]["status"] == "not_in_replay"
    assert r["reviews"][0]["recheck"]["flood_warning"]["status"] == "skipped"          # the Critic does not re-query it
    flood = next(s for s in view.sources(r["evidence"], r["plan"], "en") if s["kind"] == "flood_warnings")
    assert not flood["used"] and "not available for this date" in flood["note"]
    assert not r["card"].get("excluded") and not r["card"].get("not_checked")
