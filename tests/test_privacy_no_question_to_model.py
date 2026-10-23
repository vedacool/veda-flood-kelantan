"""Privacy (Husaini 24 Oct): the user's question is never sent to any AI model. The real adapter builds every Nightshift
request (draft + Critic review); only the HTTP layer is replaced, so this checks the exact bodies that would leave."""
import json
from types import SimpleNamespace

import pytest

from app import gazetteer, loop, router
from app.adapters import nightshift
from app.agents import critic

QUESTION = "Mak saya Siti Zubaidah di Tumpat, nombor 0123456789, kena pindah malam ni? kodQZXWV"


@pytest.fixture
def live_models_offline_data(monkeypatch, tmp_path):
    """Recorded data (SAMPLE_MODE fixtures) but the real Nightshift adapter, with the network call replaced."""
    monkeypatch.setenv("SAMPLE_MODE", "true")
    monkeypatch.setattr(nightshift, "config", SimpleNamespace(sample_mode=lambda: False))
    monkeypatch.setenv("METERLESS_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("METERLESS_RUNTIME_TOKEN", "test-token")
    monkeypatch.setattr(router, "data_triggers", lambda *a, **k: ["test: forced full"])
    bodies = []

    def fake_call(lane, body, agent, prompt_summary, deadline=None, max_attempts=None):
        bodies.append(json.dumps(body, ensure_ascii=False))
        review = body["messages"][0]["content"] in (critic.SMALL_SYSTEM, critic.CRITIC_SYSTEM)
        content = '{"ok": true, "reason": "matches"}' if review else '{"explanation": "Paras sungai di Tumpat normal."}'
        return {"model": "nvidia/nemotron-3.5-super-vl-120b-a12b", "choices": [{"message": {"content": content}}],
                "meterless": {"decision_id": "req_test"}}, 1
    monkeypatch.setattr(nightshift, "_call", fake_call)
    gazetteer.clear_cache()
    yield SimpleNamespace(tmp=tmp_path, bodies=bodies)
    gazetteer.clear_cache()


def test_the_question_never_reaches_a_model(live_models_offline_data):
    env = live_models_offline_data
    r = loop.run(QUESTION, log_dir=env.tmp, quiet=True)                   # the real nightshift.chat, no stand-in
    assert r["plan"]["effort"] == "full" and len(env.bodies) >= 2          # draft + Critic review both sent
    for body in env.bodies:
        for piece in ("kodQZXWV", "Siti Zubaidah", "0123456789", "Mak saya", "kena pindah malam ni"):
            assert piece not in body, piece
    assert any('FACTS' in b for b in env.bodies)                           # what IS sent: the card's key facts
