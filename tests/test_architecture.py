"""Architecture guard rules (B-65). Run by the pre-commit hook and CI; a failure blocks the commit.

Each test is one rule from BUILD_BRIEF / CLAUDE.md. Rules 1-2 skip spikes/ (throwaway, direct HTTP by design);
the secret scan and the control-character check cover every tracked file (spikes/, logs and fixtures included)
and read the STAGED content, i.e. exactly what is about to be committed.
"""
import ast
import re
import subprocess
from pathlib import Path

from app import config
from scripts.codemap import imports_of_file

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "app" / "agents"
# Agents get data only via run_sql() and models only via the Nightshift adapter. Anything that reaches the
# network, a database, the shell or dynamic imports directly would bypass that.
FORBIDDEN_FOR_AGENTS = {"requests", "httpx", "urllib", "urllib3", "aiohttp", "socket", "http",
                        "psycopg", "psycopg2", "sqlite3", "subprocess", "importlib", "ctypes",
                        "app.adapters.pg", "app.ingest"}
FORBIDDEN_CALLS = {"__import__", "exec", "eval"}
TRACE_MODULE = "app.trace"  # trace logger location, fixed in DECISIONS.md (built in B-02)


def py_files(*entries):
    out = []
    for entry in entries:
        p = ROOT / entry
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(f for f in p.rglob("*.py") if "__pycache__" not in f.parts)
    return sorted(out)


def staged_texts():
    """[(path, text)] for every tracked file as STAGED in the index (what a commit will contain).
    Binary files are skipped."""
    listing = subprocess.run(["git", "ls-files", "-s", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    entries = []
    for item in listing.decode("utf-8").split("\0"):
        if not item:
            continue
        meta, path = item.split("\t", 1)
        mode, sha, _stage = meta.split()
        if mode != "160000":           # skip submodules
            entries.append((path, sha))
    batch = subprocess.run(["git", "cat-file", "--batch"], cwd=ROOT, check=True, capture_output=True,
                           input="".join(f"{sha}\n" for _, sha in entries).encode()).stdout
    out, pos = [], 0
    for path, _sha in entries:
        header_end = batch.index(b"\n", pos)
        size = int(batch[pos:header_end].split()[2])
        body = batch[header_end + 1: header_end + 1 + size]
        pos = header_end + 1 + size + 1
        try:
            staged = body.decode("utf-8")
        except UnicodeDecodeError:
            continue                   # binary file
        out.append((path, staged))
        # also the working-tree copy when it differs, so a manual test run sees unstaged edits too
        work = ROOT / path
        if work.is_file():
            try:
                current = work.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if current.replace("\r\n", "\n") != staged.replace("\r\n", "\n"):
                out.append((f"{path} (working tree)", current))
    return out


def rel(p):
    return p.relative_to(ROOT).as_posix()


# --- Rule 1: agents get data only through run_sql() -- no direct network / DB / shell -------------------------
def test_agents_never_import_network_db_or_shell():
    bad = []
    for f in py_files("app/agents"):
        imported = imports_of_file(f)
        hits = {m for m in imported for banned in FORBIDDEN_FOR_AGENTS if m == banned or m.startswith(banned + ".")}
        hits |= {m for m in imported if m.split(".")[0] in FORBIDDEN_FOR_AGENTS}
        tree = ast.parse(f.read_text(encoding="utf-8"))
        hits |= {f"{n.func.id}()" for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FORBIDDEN_CALLS}
        if hits:
            bad.append(f"{rel(f)} uses {sorted(hits)}")
    assert not bad, ("Agents must get data only via run_sql() (Zetaris) and models via the Nightshift adapter - "
                     "no direct network, DB, shell or dynamic imports:\n" + "\n".join(bad))


# --- Rule 1b: agents never use setup-only DDL --------------------------------------------------------------
def test_agents_never_use_setup_ddl():
    bad = []
    for f in py_files("app/agents"):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and any(k.arg == "setup" for k in n.keywords):
                bad.append(f"{rel(f)}:{n.lineno}")
    assert not bad, "run_ddl(setup=...) is for scripts/ only, never agents:\n" + "\n".join(bad)


# --- Rule 2: never route through meterless/auto -------------------------------------------------------------
def test_no_meterless_auto():
    bad = [f"{rel(f)}:{i}" for f in py_files("app", "scripts", "veda", "run.py")      # + veda/ (audit 27 Oct A-P3-13)
           for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1) if "meterless/auto" in line]
    assert not bad, "Never call meterless/auto - use meterless/fast / meterless/deep:\n" + "\n".join(bad)


# --- Rule 3: no reading output_examples/ at runtime ---------------------------------------------------------
def test_runtime_never_reads_output_examples():
    bad = [f"{rel(f)}:{i}" for f in py_files("app", "veda", "run.py")                  # + veda/ (audit 27 Oct A-P3-13)
           for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1) if "output_examples" in line]
    assert not bad, "Runtime code must never read output_examples/ (no hard-coded outputs):\n" + "\n".join(bad)


# --- Rule 4: every agent writes trace -----------------------------------------------------------------------
def test_every_agent_uses_trace_logger():
    bad = [rel(f) for f in py_files("app/agents") if f.name != "__init__.py"
           and not any(m == TRACE_MODULE or m.startswith(TRACE_MODULE + ".") for m in imports_of_file(f))]
    assert not bad, f"Every agent must import the trace logger ({TRACE_MODULE}):\n" + "\n".join(bad)


# --- Rule 5: no secrets in anything staged (spikes/, logs, fixtures included) --------------------------------
def local_env_secrets():
    """Non-empty secret-looking values from the local .env (never printed)."""
    env = ROOT / ".env"
    if not env.exists():
        return []
    values = {}
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.split(" #")[0].strip().strip("'\"")
    return [(k, v) for k, v in values.items() if config.SECRET_ENV_KEY.search(k) and len(v) >= 6]


def test_no_secrets_in_staged_files():
    env_values = local_env_secrets()
    bad = []
    for path, text in staged_texts():
        for i, line in enumerate(text.splitlines(), 1):
            for label, pat in config.SECRET_PATTERNS.items():
                if pat.search(line):
                    bad.append(f"{path}:{i} looks like a {label}")
            for key, value in env_values:
                if value in line:
                    bad.append(f"{path}:{i} contains the value of {key} from .env")
    assert not bad, "Possible secrets in staged files (values not shown):\n" + "\n".join(bad)


# --- Rule 6: .env is never tracked --------------------------------------------------------------------------
def test_env_file_not_tracked():
    assert not [p for p, _ in staged_texts() if Path(p).name == ".env"], ".env must never be committed"


# --- Rule 7: no invisible control characters in text files ---------------------------------------------------
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def test_no_control_characters():
    # A backslash in an edit script (e.g. "\a", "\v", "\b") silently becomes a control character - 3 times on
    # 22 Oct. Tabs, newlines and carriage returns are fine.
    bad = [f"{path}:{text[:m.start()].count(chr(10)) + 1} (char {ord(m.group())})"
           for path, text in staged_texts() for m in [CONTROL.search(text)] if m]
    assert not bad, "Invisible control characters in text files:\n" + "\n".join(bad)
