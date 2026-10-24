"""scripts/make_demo_bundle.py refuses a bundle with secrets in it, and the demo setup script stays safe."""
import importlib.util
import io
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("make_demo_bundle", ROOT / "scripts" / "make_demo_bundle.py")
mb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mb)


def tar_gz(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_secret_files_and_env_values_are_refused():
    fake = "-".join(("made", "up", "env", "value"))           # built at runtime: a made-up value, never a real one
    assert mb.check_bundle(tar_gz({"veda-demo/app/x.py": "print(1)", "veda-demo/.env.example": "KEY=placeholder"}),
                           [fake]) == []
    problems = mb.check_bundle(tar_gz({"veda-demo/.env": "A=b", "veda-demo/demo/id_rsa": "x",
                                       "veda-demo/app/c.py": f"X = {fake}"}), [fake])
    assert any(".env" in p for p in problems) and any("id_rsa" in p for p in problems)
    assert any("a .env value inside veda-demo/app/c.py" == p for p in problems)


def test_only_secret_env_keys_are_checked(tmp_path, monkeypatch):
    """Like the commit hook: a model name or a local URL is a setting, not a secret (it is in the code on purpose)."""
    fake = "-".join(("made", "up", "secret"))
    (tmp_path / ".env").write_text(f"METERLESS_MODEL_DEEP=nvidia/some-model\nMETERLESS_BASE_URL=http://127.0.0.1:8088/v1\n"
                                   f"METERLESS_RUNTIME_TOKEN={fake}\nVEDA_PG_PASSWORD={fake}2\n", encoding="utf-8")
    monkeypatch.setattr(mb, "ROOT", tmp_path)
    assert sorted(mb.env_values()) == [fake, fake + "2"]


def test_bundle_holds_what_the_demo_builds_from_and_never_local_state():
    for p in ("Dockerfile", "requirements-lock.txt", "app", "data", "demo", "docs/DEPLOY_DEMO.md"):
        assert p in mb.PATHS
    assert not any(p.startswith((".env", "logs", "dist", ".venv")) for p in mb.PATHS)
    assert mb.DEMO_MODE_COMMIT == "a6a2280"


def test_setup_script_never_resets_tailscale_and_never_installs():
    sh = (ROOT / "demo" / "setup_wyse.sh").read_text(encoding="utf-8")
    assert sh.startswith("#!/usr/bin/env bash") and "set -euo pipefail" in sh
    printed = sh.split("cat <<'EOF'", 1)[1].split("\nEOF", 1)[0]            # the install steps it only prints
    code = "\n".join(line for line in sh.replace(printed, "").splitlines() if not line.lstrip().startswith("#"))
    assert "get.docker.com" in printed and "get.docker.com" not in code       # never installs Docker itself
    assert "reset" not in code                                                 # never a Tailscale reset
    assert '--https="$fport" off' in code                                      # --stop: the demo's port only
    assert all(line.lstrip().startswith("say") for line in code.splitlines() if "down -v" in line)  # answers kept
    stop = code.split('"--stop" ]', 1)[1].split("exit 0", 1)[0]
    assert "read -r -p" in stop and "sudo tailscale funnel --https=443 off" in stop   # 443 too, but asks first
    assert stop.index("read -r -p") < stop.index("--https=443 off")
    export = code.split('"--export" ]', 1)[1].split("exit 0", 1)[0]
    assert 'rm -f "$out"' in export                                            # no half-written CSV left behind
