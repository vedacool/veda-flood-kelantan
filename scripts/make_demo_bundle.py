"""Build the public-demo bundle for the Wyse (docs/DEPLOY_DEMO.md): dist/veda-demo-<commit>.tar.gz.

    python scripts/make_demo_bundle.py                 # from origin/main (fetched first)
    python scripts/make_demo_bundle.py --ref <commit>  # any commit at or after a6a2280

The bundle is a `git archive` of the committed files the demo needs - never the working tree, so local changes,
`.env`, logs and caches cannot get in. Before it is written it must pass: the app's demo mode is in the commit
(VEDA_DEMO, a6a2280), no secret-looking or `.env` file names, none of this machine's `.env` values anywhere, and the
JPS guard (tests/test_no_jps_readings.py) run on the unpacked bundle. Prints the size and SHA256.
"""
import argparse
import hashlib
import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_MODE_COMMIT = "a6a2280"
# what the demo needs: the Docker build (see Dockerfile), the demo stack, the guide, licences
PATHS = ["Dockerfile", ".dockerignore", "requirements.txt", "requirements-lock.txt", "run.py", "app", "data",
         "scripts/run_evals.py", "tests/evals", "demo", "docs/DEPLOY_DEMO.md", "LICENSE", "NOTICE", "README.md"]
# extra files the JPS guard reads; used only to check the bundle, never put in it
GUARD = ["tests/test_no_jps_readings.py", "tests/fixtures/jps_synthetic_page.html", "scripts/make_synthetic_scenes.py",
         "scripts/publish_trace.py", "tests/conftest.py"]
BAD_NAMES = (".env", ".pem", ".key", "id_rsa", "credentials", "secrets")


def git(*args, binary=False):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode("utf-8").strip()


def env_values():
    """This machine's secret .env values - none may appear in the bundle. Same rule as the commit hook
    (tests/test_architecture.py): keys matching config.SECRET_ENV_KEY (TOKEN / KEY / PASSWORD / SECRET), 6+ characters.
    Settings such as the model name or Nightshift's local address are not secrets and are in the code on purpose."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app import config
    path = ROOT / ".env"
    if not path.exists():
        return []
    vals = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            v = value.split(" #")[0].strip().strip('"').strip("'")
            if config.SECRET_ENV_KEY.search(key.strip()) and len(v) >= 6:
                vals.append(v)
    return vals


def check_bundle(data, values):
    problems = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar.getmembers():
            name = m.name.lower().rsplit("/", 1)[-1]
            if any(name == b or name.startswith(".env") or name.endswith(b) for b in BAD_NAMES) \
                    and name != ".env.example":
                problems.append(f"secret-looking file: {m.name}")
            if m.isfile() and values:
                text = tar.extractfile(m).read().decode("utf-8", errors="ignore")
                problems += [f"a .env value inside {m.name}" for v in values if v in text]
    return problems


def jps_guard(data, ref):
    """Unpack the bundle + the guard's own files into a scratch git repo and run the guard there."""
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            tar.extractall(tmp, filter="data")
        root = Path(tmp) / "veda-demo"
        for p in GUARD:
            try:
                blob = git("show", f"{ref}:{p}", binary=True)
            except subprocess.CalledProcessError:
                continue                                  # optional file (conftest) not in this commit
            (root / p).parent.mkdir(parents=True, exist_ok=True)
            (root / p).write_bytes(blob)
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"]):
            subprocess.run(cmd, cwd=root, check=True, capture_output=True)
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                            "tests/test_no_jps_readings.py"], cwd=root, capture_output=True, text=True,
                           env={**__import__("os").environ, "SAMPLE_MODE": "true"})
        last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
        return r.returncode == 0, last, r.stdout + r.stderr


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="origin/main")
    a = ap.parse_args(argv)
    if a.ref.startswith("origin/"):
        git("fetch", "-q", "origin")
    commit = git("rev-parse", "--short=7", a.ref)
    if subprocess.run(["git", "merge-base", "--is-ancestor", DEMO_MODE_COMMIT, a.ref], cwd=ROOT).returncode != 0:
        sys.exit(f"refusing: {a.ref} ({commit}) is older than {DEMO_MODE_COMMIT} - the app has no VEDA_DEMO mode")
    if "def demo_mode" not in git("show", f"{a.ref}:app/config.py"):
        sys.exit(f"refusing: {a.ref} has no demo_mode() in app/config.py")
    data = git("archive", "--format=tar.gz", f"--prefix=veda-demo/", a.ref, *PATHS, binary=True)
    problems = check_bundle(data, env_values())
    if problems:
        sys.exit("refusing - " + "; ".join(problems[:5]))
    ok, last, log = jps_guard(data, a.ref)
    if not ok:
        sys.exit("refusing - the JPS guard failed on the bundle:\n" + log[-2000:])
    out = ROOT / "dist" / f"veda-demo-{commit}.tar.gz"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(data)
    print(f"bundle : {out.relative_to(ROOT)}")
    print(f"commit : {commit} ({a.ref}; has {DEMO_MODE_COMMIT} VEDA_DEMO)")
    print(f"checks : no secret files, no secret .env values ({len(env_values())} checked), JPS guard {last}")
    print(f"size   : {len(data) / 1e6:.1f} MB")
    print(f"sha256 : {hashlib.sha256(data).hexdigest()}")
    print(f"next   : tailscale file cp {out.relative_to(ROOT)} wyse5070:")
    return 0


if __name__ == "__main__":
    sys.exit(main())
