"""B-106 `python -m veda doctor`: is this machine ready to run VEDA? Read-only, one line per check (✓ / ✗ + a one-line
fix), then the mode the server will start in and why (the same rule as the server's start-up check, B-104). Never
prints a key or any .env value. Always exits 0.

Also two small helpers the installers (install.ps1 / install.sh) call, so both platforms share one tested piece of logic:
    python -m veda init-env        # .env from .env.example, only when .env does not exist (never overwrites)
    python -m veda start [--port]  # the server on 127.0.0.1 in the background, then the link and the mode
"""
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JPS_STAMP = "doctor-jps-check.txt"      # under logs/: the doctor's own last JPS check (the 15-minute rule)
LIVE_SETUP = "README 'Live setup'"


def _python():
    v = sys.version_info
    ok = v >= (3, 11)                       # requirements-lock.txt (starlette) needs 3.11+
    return ok, f"Python {v.major}.{v.minor}.{v.micro}", None if ok else "install Python 3.11+ (3.13 recommended)"


def _packages(root):
    """Every package VEDA imports (requirements.txt) installed at its pinned version."""
    wrong = []
    lines = (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pins = [re.split(r"==", ln.split("#")[0].strip()) for ln in lines if "==" in ln.split("#")[0]]
    for name, want in pins:
        name = re.sub(r"\[.*\]", "", name).strip()
        try:
            have = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            have = None
        if have != want.strip():
            wrong.append(f"{name} {have or 'missing'}")
    if wrong:
        return False, f"Packages: {len(wrong)} of {len(pins)} not as pinned ({', '.join(wrong[:3])}" + \
            (", ..." if len(wrong) > 3 else "") + ")", "pip install -r requirements-lock.txt (or run the installer)"
    return True, f"Packages: {len(pins)} of {len(pins)} at the pinned versions", None


def _env_file(root):
    if (root / ".env").exists():
        return True, ".env present (values not shown)", None
    return False, ".env not found (fine for the offline demo)", \
        "copy .env.example to .env (the installer does this), then fill in the keys yourself for live mode"


def _docker():
    exe = shutil.which("docker")
    if not exe:
        return False, "Docker not found (needed only for live mode: Zetaris + Postgres)", \
            "install Docker Desktop - see " + LIVE_SETUP
    try:
        r = subprocess.run([exe, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            return True, f"Docker engine running ({r.stdout.strip()})", None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return False, "Docker installed but the engine is not answering (needed only for live mode)", \
        "start Docker Desktop yourself, then run the doctor again"


def zetaris_check(sql):
    """One read-only SQL statement on Zetaris -> 'ok' or a short reason (no key in it)."""
    from app.adapters import zetaris
    try:
        r = zetaris._post(sql, 1, timeout=10)
    except Exception as e:                  # noqa: BLE001 - audit 26 Oct: e.g. a smart-quoted key (UnicodeEncodeError)
        return f"unreachable ({type(e).__name__})"
    if r.ok:
        return "ok"
    return "API key refused (401)" if r.status_code == 401 else f"error (HTTP {r.status_code})"


VEDA_VIEWS = ("veda.place_risk_inputs", "veda.place_gauge_status")


def _zetaris():
    if not (os.getenv("ZETARIS_API_URL", "").strip() and os.getenv("ZETARIS_API_KEY", "").strip()):
        return False, "Zetaris: ZETARIS_API_URL / ZETARIS_API_KEY not set", \
            "put your Zetaris URL and API token into .env yourself - see " + LIVE_SETUP, "not set"
    state = zetaris_check("SELECT 1 AS x")
    if state != "ok":
        return False, f"Zetaris {state}", "start Zetaris in Docker and check ZETARIS_API_URL / the token - see " + \
            LIVE_SETUP, state
    missing = [v for v in VEDA_VIEWS if zetaris_check(f"SELECT * FROM {v} LIMIT 1") != "ok"]
    if missing:
        return False, f"Zetaris reachable, VEDA's tables missing ({', '.join(missing)})", \
            "python scripts/setup_all.py - see " + LIVE_SETUP, "ok"
    return True, "Zetaris reachable, VEDA's tables present", None, "ok"


def nightshift_models():
    """Nightshift's /healthz and the model names it serves -> (state, [names])."""
    import requests
    base = os.getenv("METERLESS_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("METERLESS_RUNTIME_TOKEN", "").strip()
    try:
        if not requests.get(base.rsplit("/v1", 1)[0] + "/healthz", timeout=5).ok:
            return "error", []
        r = requests.get(f"{base}/models", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    except Exception as e:                  # noqa: BLE001
        return f"unreachable ({type(e).__name__})", []
    if not r.ok:
        return ("token refused (401)" if r.status_code == 401 else f"error (HTTP {r.status_code})"), []
    try:
        return "ok", [m.get("id") for m in r.json().get("data", [])]
    except (ValueError, AttributeError):
        return "error (model list not readable)", []


def _nightshift():
    from app.adapters import nightshift
    if not (os.getenv("METERLESS_BASE_URL", "").strip() and os.getenv("METERLESS_RUNTIME_TOKEN", "").strip()):
        return False, "Nightshift: METERLESS_BASE_URL / METERLESS_RUNTIME_TOKEN not set", \
            "install Nightshift, then put its URL and runtime token into .env yourself - see " + LIVE_SETUP, "not set"
    state, models = nightshift_models()
    if state != "ok":
        return False, f"Nightshift {state}", "start Meterless Nightshift and check METERLESS_BASE_URL / the token - see " \
            + LIVE_SETUP, state
    want = nightshift.lane_model("deep")
    if want not in models:
        return False, f"Nightshift reachable, but {want} is not offered", \
            "add your NVIDIA key in Nightshift's Providers tab yourself - see " + LIVE_SETUP, "ok"
    return True, f"Nightshift reachable, {want} available", None, "ok"


def jps_head():
    import requests
    from app.ingest import jps
    try:
        r = requests.head(jps.URL, timeout=15, allow_redirects=True)
        return "ok" if r.ok else f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return f"unreachable ({type(e).__name__})"


def _jps(root):
    """Report only. One HEAD request, never within 15 minutes of the collector's last saved page or this check."""
    from app.ingest import jps
    now = time.time()
    recent = jps.newest_snapshot()
    stamp = root / "logs" / JPS_STAMP
    tried = jps.attempt_stamp()                       # the collector's last attempt, failed or not (A-P3-32)
    last = max([p.stat().st_mtime for p in (recent, stamp if stamp.exists() else None,
                                            tried if tried.exists() else None) if p] or [0])
    if 0 <= now - last < jps.MIN_INTERVAL_S:
        return True, f"JPS: not checked - VEDA fetched or checked it {int((now - last) // 60)} min ago " \
            "(at most once per 15 minutes)", None
    state = jps_head()
    try:
        stamp.parent.mkdir(exist_ok=True)
        stamp.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    except OSError:
        pass
    if state == "ok":
        return True, "JPS Public Infobanjir reachable", None
    return False, f"JPS Public Infobanjir {state} (report only)", \
        "nothing to fix here: VEDA keeps the last good readings and answers \"Can't confirm right now\""


def run(root=None, out=print):
    """All checks, then the mode. Returns the mode ('live' / 'offline')."""
    root = root or ROOT
    from dotenv import load_dotenv
    from app import config
    if not config.demo_mode():
        load_dotenv(root / ".env")
    ok_mark, bad_mark = ("✓", "✗") if _can_print("✓✗") else ("OK", "X ")
    zstate = nstate = None

    def line(res):
        ok, text, fix = res[:3]
        out(f"{ok_mark if ok else bad_mark} {text}" + ("" if ok else f"\n    fix: {fix}"))

    out("VEDA doctor (read-only; no key or .env value is ever shown)")
    line(_python())
    try:
        line(_packages(root))
    except OSError as e:
        line((False, f"Packages: cannot read requirements.txt ({type(e).__name__})", "run from the VEDA folder"))
    line(_env_file(root))
    line(_docker())
    for name, check in (("Zetaris", _zetaris), ("Nightshift", _nightshift), ("JPS", lambda: _jps(root))):
        try:
            res = check()
        except ImportError as e:
            res = (False, f"{name}: not checked (missing package {e.name})", "pip install -r requirements-lock.txt", None)
        line(res)
        if name == "Zetaris":
            zstate = res[3]
        elif name == "Nightshift":
            nstate = res[3]
    mode, why = start_mode(zstate, nstate)
    out(f"Mode: the server will start {'LIVE' if mode == 'live' else 'in the OFFLINE DEMO'} - {why}")
    return mode


def start_mode(zstate, nstate):
    """The server's own start-up rule (B-104, app.main.offline_reason), from the states found above."""
    from app import config
    if config.sample_mode():
        return "offline", config.sample_reason()
    from app import main
    reason = main.offline_reason(zetaris_state=zstate or "not checked")
    if reason:
        return "offline", reason
    note = main.nightshift_note(nightshift_state=nstate if nstate not in (None, "not set") else None)
    return "live", (f"Zetaris answering; {note} - answers are written by code until it answers" if note
                    else "keys set, Zetaris and Nightshift answering")


def _can_print(text):
    try:
        text.encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


# --- the installers' helpers -------------------------------------------------------------------------------------
def init_env(root=None, out=print):
    """.env from .env.example only when .env does not exist. Exclusive create: an existing .env is never touched."""
    root = root or ROOT
    try:
        with open(root / ".env", "x", encoding="utf-8", newline="") as f:
            f.write((root / ".env.example").read_text(encoding="utf-8"))
    except FileExistsError:
        out(".env already exists - left unchanged")
        return False
    out(".env created from .env.example (no keys in it: VEDA starts in the offline demo until you add them)")
    return True


def _health(port, timeout=3):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            h = json.loads(r.read().decode("utf-8"))
        return h if isinstance(h, dict) and "sample_mode" in h else None      # a VEDA /health, nothing else
    except (OSError, ValueError):
        return None


def _port_busy(port):
    import socket
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start(port=8000, root=None, out=print, wait_s=120):
    """The web server on 127.0.0.1:<port> in the background (log: logs/server-<port>.log), then the link + the mode.
    Already running on that port -> says so and starts nothing."""
    root = root or ROOT
    h = _health(port)
    if h is None and _port_busy(port):
        out(f"Port {port} is in use by another program - stop it, or use: python -m veda start --port 8001")
        return 1
    if h is None:
        (root / "logs").mkdir(exist_ok=True)
        log = open(root / "logs" / f"server-{port}.log", "ab")
        kw = ({"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
              if os.name == "nt" else {"start_new_session": True})
        proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                 "--port", str(port)], cwd=root, stdout=log, stderr=log, stdin=subprocess.DEVNULL, **kw)
        deadline = time.monotonic() + wait_s
        while h is None and time.monotonic() < deadline and proc.poll() is None:
            time.sleep(1)
            h = _health(port, timeout=5)
        if h is None:
            if proc.poll() is None:                 # audit 26 Oct: never leave a hung server behind
                proc.terminate()
            out(f"The server did not start - see logs/server-{port}.log, then run: python -m veda doctor")
            return 1
        stop = f"Stop-Process -Id {proc.pid}" if os.name == "nt" else f"kill {proc.pid}"
        note = f"(stop it with: {stop})"
    else:
        note = "(it was already running)"
    mode = f"offline demo - {h.get('reason')}" if h.get("sample_mode") else "live"
    out(f"VEDA is running ({mode}): http://127.0.0.1:{port}  {note}")
    return 0
