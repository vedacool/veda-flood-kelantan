"""B-104 (Cowork 26 Oct): one app, two modes. At server start VEDA runs live when the keys are set and Zetaris +
Nightshift answer; otherwise it falls back to offline sample mode with the reason (log line + /health). A data outage
while running (JPS) never switches it. Offline: no network - the two service checks are stubbed."""
import logging

import pytest
from fastapi.testclient import TestClient

from app import config, frame, main

KEYS = {"ZETARIS_API_URL": "http://zetaris.test", "ZETARIS_API_KEY": "placeholder-key-1",
        "METERLESS_BASE_URL": "http://nightshift.test/v1", "METERLESS_RUNTIME_TOKEN": "placeholder-token-2"}


@pytest.fixture
def fresh(monkeypatch):
    """Not in sample mode, no fallback yet; SAMPLE_MODE and the fallback are restored after the test."""
    monkeypatch.setenv("SAMPLE_MODE", "false")
    monkeypatch.delenv("VEDA_DEMO", raising=False)
    monkeypatch.setitem(config._FALLBACK, "reason", None)
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def services(mp, zetaris="ok", nightshift="ok"):
    mp.setattr(main, "_zetaris_status", lambda: zetaris)
    mp.setattr(main, "_nightshift_status", lambda: nightshift)


def test_no_env_file_and_no_keys_starts_offline(fresh, tmp_path, caplog):
    fresh.setattr(config, "ROOT", tmp_path)                      # a fresh clone: no .env
    services(fresh, zetaris="never called", nightshift="never called")
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        main.start_mode()
    assert config.sample_mode() and config.sample_reason().startswith("no .env file: ZETARIS_API_URL")
    assert [r.getMessage() for r in caplog.records] == [f"VEDA: starting in offline sample mode - {config.sample_reason()}"]


def test_unreachable_services_start_offline_with_the_reason(fresh):
    for k, v in KEYS.items():
        fresh.setenv(k, v)
    services(fresh, zetaris="unreachable (ConnectionError)")
    with TestClient(main.app) as c:                              # the real start-up (lifespan) runs the check
        h = c.get("/health").json()
    assert h["sample_mode"] is True and h["reason"] == "Zetaris unreachable (ConnectionError) at start-up"
    assert "Demo · past flood replay · not an official warning" in TestClient(main.app).get("/").text
    fresh.setitem(config._FALLBACK, "reason", None)
    services(fresh, nightshift="error")
    assert main.offline_reason() == "Nightshift error at start-up"


def test_reason_names_keys_never_values(fresh):
    fresh.setenv("ZETARIS_API_KEY", "placeholder-key-1")
    reason = main.offline_reason()
    assert "ZETARIS_API_URL" in reason and "ZETARIS_API_KEY" not in reason and "placeholder-key-1" not in reason


def test_a_jps_outage_while_running_stays_live(fresh):
    for k, v in KEYS.items():
        fresh.setenv(k, v)
    services(fresh)
    main.start_mode()
    assert not config.sample_mode() and config.sample_reason() is None
    # the collector has failed for hours and the JPS breaker is open: degraded, still live, never switched
    fresh.setattr(main, "_store_health", lambda: {"postgres": "ok", "newest_reading_age_min": 900,
                                                  "newest_reading": "stale", "open_breakers": ["jps_levels"]})
    h = TestClient(main.app).get("/health").json()
    assert h["sample_mode"] is False and h["status"] == "degraded" and "reason" not in h
    assert not config.sample_mode()


def test_sample_mode_set_skips_the_check(fresh):
    fresh.setenv("SAMPLE_MODE", "true")
    fresh.setattr(main, "offline_reason", lambda: pytest.fail("no service check when SAMPLE_MODE=true"))
    main.start_mode()
    h = TestClient(main.app).get("/health").json()
    assert h["sample_mode"] is True and h["reason"] == "SAMPLE_MODE=true"


def test_live_strip_on_the_live_home_only():
    live = "Live · river readings from JPS now · not an official warning"
    assert live in frame.top("home", demo=False)
    assert 'data-vf-ms="Langsung · bacaan sungai JPS terkini · bukan amaran rasmi"' in frame.top("home", demo=False)
    assert live not in frame.top("home", demo=True)
    for page in ("scenes", "how", "live", "sources"):           # past runs / replays: no "now" strip
        assert 'class="vf-strip' not in frame.top(page, demo=False)
