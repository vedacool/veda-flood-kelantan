"""VEDA_DEMO=1 - the public demo (Session B, docs/DEPLOY_DEMO.md): SAMPLE_MODE forced on whatever else is set, no
.env read, no live Zetaris / Nightshift call even if something asks, and the operator routes answer 404."""
import importlib

import pytest
from starlette.testclient import TestClient

from app import config
from app.adapters import nightshift, zetaris


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv("VEDA_DEMO", "1")
    monkeypatch.setenv("SAMPLE_MODE", "false")          # Session B's case: the demo wins
    yield


def test_demo_forces_sample_mode(demo):
    assert config.demo_mode() and config.sample_mode()


def test_demo_off_by_default(monkeypatch):
    monkeypatch.delenv("VEDA_DEMO", raising=False)
    monkeypatch.setenv("SAMPLE_MODE", "false")
    assert not config.demo_mode() and not config.sample_mode()


def test_no_live_call_is_possible_in_the_demo(demo):
    with pytest.raises(zetaris.ZetarisError, match="public demo"):
        zetaris._post("SELECT 1", 1)
    with pytest.raises(nightshift.NightshiftError, match="public demo"):
        nightshift._post("http://127.0.0.1:9/v1", "t", {"model": "m"}, "veda-deep")


def test_operator_routes_answer_404_in_the_demo(demo):
    from app import main
    c = TestClient(main.app)
    for method, path in (("get", "/admin"), ("get", "/admin/api/overview"), ("get", "/admin/api/run/20261024-120000-abcd"),
                         ("post", "/admin/api/approve"), ("get", "/trace/run/20261024-120000-abcd")):
        r = getattr(c, method)(path)
        assert r.status_code == 404 and r.json()["error"]["message"] == "not in the public demo", path
    h = c.get("/health").json()
    assert h["sample_mode"] is True and h["nightshift"] == "not used"
    assert c.get("/").status_code == 200 and c.get("/live").status_code == 200       # the public screens stay
    assert c.get("/trace/recorded").status_code == 200


def test_main_reads_no_env_file_in_the_demo(demo, monkeypatch):
    import dotenv
    from app import main
    calls = []
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: calls.append(a))
    importlib.reload(main)
    try:
        assert calls == []
    finally:
        monkeypatch.delenv("VEDA_DEMO")
        importlib.reload(main)                         # back to the normal module for the other tests
