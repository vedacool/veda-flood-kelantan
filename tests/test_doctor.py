"""B-106 `python -m veda doctor` + the installers' .env step. Offline: Docker, Zetaris, Nightshift and JPS are stubbed.
The doctor never prints a key, always exits 0, and states the mode with the server's own start-up rule (B-104)."""
import shutil
import time

import pytest

from app import config
from veda import __main__ as cli
from veda import doctor

KEYS = {"ZETARIS_API_URL": "http://zetaris.test", "ZETARIS_API_KEY": "placeholder-key-1",
        "METERLESS_BASE_URL": "http://nightshift.test/v1", "METERLESS_RUNTIME_TOKEN": "placeholder-token-2"}
NEMOTRON = "nvidia/nemotron-3.5-super-vl-120b-a12b"


@pytest.fixture
def home(monkeypatch, tmp_path):
    """A VEDA folder with no .env and no keys, nothing reachable unless a test says so."""
    shutil.copy(config.ROOT / "requirements.txt", tmp_path / "requirements.txt")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(doctor, "ROOT", tmp_path)                 # never the real .env
    monkeypatch.setenv("SAMPLE_MODE", "false")
    monkeypatch.delenv("VEDA_DEMO", raising=False)
    monkeypatch.delenv("METERLESS_MODEL_DEEP", raising=False)
    monkeypatch.setitem(config._FALLBACK, "reason", None)
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(doctor, "_docker", lambda: (True, "Docker engine running (test)", None))
    monkeypatch.setattr(doctor, "_jps", lambda root: (True, "JPS Public Infobanjir reachable", None))
    monkeypatch.setattr(doctor, "zetaris_check", lambda sql: pytest.fail("no Zetaris call without keys"))
    monkeypatch.setattr(doctor, "nightshift_models", lambda: pytest.fail("no Nightshift call without keys"))
    return monkeypatch, tmp_path


def run(tmp_path):
    out = []
    mode = doctor.run(root=tmp_path, out=out.append)
    return mode, "\n".join(out)


def keys_and_services(mp, tmp_path, zetaris="ok", models=(NEMOTRON,)):
    (tmp_path / ".env").write_text("# test .env: the keys come from the environment\n", encoding="utf-8")
    for k, v in KEYS.items():
        mp.setenv(k, v)
    mp.setattr(doctor, "zetaris_check", lambda sql: zetaris)
    mp.setattr(doctor, "nightshift_models", lambda: ("ok", list(models)))


def test_missing_env_file_starts_the_offline_demo(home):
    _, tmp = home
    mode, text = run(tmp)
    assert ".env not found (fine for the offline demo)" in text and "fix: copy .env.example to .env" in text
    assert "Zetaris: ZETARIS_API_URL / ZETARIS_API_KEY not set" in text
    assert mode == "offline" and text.splitlines()[-1].startswith(
        "Mode: the server will start in the OFFLINE DEMO - no .env file: ZETARIS_API_URL")


def test_unreachable_zetaris_is_a_cross_with_a_fix_and_the_offline_reason(home):
    mp, tmp = home
    keys_and_services(mp, tmp, zetaris="unreachable (ConnectionError)")
    mode, text = run(tmp)
    assert "Zetaris unreachable (ConnectionError)\n    fix: start Zetaris in Docker" in text
    assert mode == "offline" and text.endswith("OFFLINE DEMO - Zetaris unreachable (ConnectionError) at start-up")


def test_all_ok_starts_live_and_never_prints_a_key(home):
    mp, tmp = home
    keys_and_services(mp, tmp)
    mode, text = run(tmp)
    assert mode == "live" and text.endswith("Mode: the server will start LIVE - keys set, Zetaris and Nightshift answering")
    assert "fix:" not in text and f"Nightshift reachable, {NEMOTRON} available" in text
    assert "Zetaris reachable, VEDA's tables present" in text
    assert not any(v in text for v in KEYS.values())


def test_model_missing_or_tables_missing(home):
    mp, tmp = home
    keys_and_services(mp, tmp, models=("meterless/fast",))
    _, text = run(tmp)
    assert f"but {NEMOTRON} is not offered\n    fix: add your NVIDIA key in Nightshift's Providers tab yourself" in text
    mp.setattr(doctor, "zetaris_check", lambda sql: "ok" if sql == "SELECT 1 AS x" else "error (HTTP 500)")
    _, text = run(tmp)
    assert "VEDA's tables missing (veda.place_risk_inputs, veda.place_gauge_status)" in text


def test_the_cli_always_exits_0(home, capsys):
    assert cli.main(["doctor"]) == 0
    assert "Mode: the server will start" in capsys.readouterr().out


def test_jps_is_checked_at_most_once_per_15_minutes(monkeypatch, tmp_path):
    from app.ingest import jps
    (tmp_path / "logs").mkdir()
    monkeypatch.setattr(jps, "newest_snapshot", lambda: None)
    calls = []
    monkeypatch.setattr(doctor, "jps_head", lambda: calls.append(1) or "HTTP 404")
    first = doctor._jps(tmp_path)
    assert calls == [1] and first[0] is False and "(report only)" in first[1]
    second = doctor._jps(tmp_path)                                    # the stamp is < 15 min old: no second request
    assert calls == [1] and second[0] is True and "at most once per 15 minutes" in second[1]
    old = time.time() - jps.MIN_INTERVAL_S - 60
    import os
    os.utime(tmp_path / "logs" / doctor.JPS_STAMP, (old, old))
    doctor._jps(tmp_path)
    assert calls == [1, 1]


def test_init_env_never_overwrites(tmp_path):
    (tmp_path / ".env.example").write_text("SAMPLE_MODE=false\nZETARIS_API_KEY=\n", encoding="utf-8")
    out = []
    assert doctor.init_env(tmp_path, out.append) is True
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "SAMPLE_MODE=false\nZETARIS_API_KEY=\n"
    (tmp_path / ".env").write_text("MY_OWN=1\n", encoding="utf-8")
    assert doctor.init_env(tmp_path, out.append) is False                  # second run: left unchanged
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "MY_OWN=1\n"
    assert out[-1] == ".env already exists - left unchanged"


def test_both_installers_use_the_same_env_step_and_bind_localhost():
    for name in ("install.ps1", "install.sh"):
        text = (config.ROOT / name).read_text(encoding="utf-8")
        assert "-m veda init-env" in text and "-m veda doctor" in text and "-m veda start" in text
        assert "requirements-lock.txt" in text
        for never in ("sudo ", "Remove-Item", "rm -", "curl ", "wget ", "docker ", "0.0.0.0", "Copy-Item", "cp "):
            assert never not in text, (name, never)
    assert '"--host", "127.0.0.1"' in (config.ROOT / "veda" / "doctor.py").read_text(encoding="utf-8")


def test_nightshift_down_still_starts_live(home):
    mp, tmp = home
    keys_and_services(mp, tmp)
    mp.setattr(doctor, "nightshift_models", lambda: ("unreachable (ConnectionError)", []))
    mode, text = run(tmp)
    assert mode == "live" and text.endswith("Mode: the server will start LIVE - Zetaris answering; Nightshift "
                                            "unreachable (ConnectionError) - answers are written by code until it answers")


def test_start_says_when_the_port_is_busy(monkeypatch, tmp_path):
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        port = s.getsockname()[1]
        out = []
        assert doctor.start(port, root=tmp_path, out=out.append) == 1
    assert out == [f"Port {port} is in use by another program - stop it, or use: python -m veda start --port 8001"]
