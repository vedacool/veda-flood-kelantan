"""Architecture guard rules (B-65). Run by the pre-commit hook; a failure blocks the commit.

Each test is one rule from BUILD_BRIEF / CLAUDE.md. Rules 1-2 skip spikes/ (throwaway, direct HTTP by design);
the secret scan (rule 5) covers every tracked file, spikes/, logs and fixtures included.
"""
import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / "app" / "agents"
NETWORK_MODULES = {"requests", "httpx", "urllib", "urllib3", "aiohttp", "socket", "http"}
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


def imports_of(path):
    """Absolute module names imported by a file (relative imports resolved against its package)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    pkg = list(path.relative_to(ROOT).with_suffix("").parts[:-1])
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = pkg[: len(pkg) - (node.level - 1)]
                base = ".".join(anchor + ([base] if base else []))
            names.add(base)
            names.update(f"{base}.{a.name}" for a in node.names)
    return names


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / f for f in out.split("\0") if f]


def rel(p):
    return p.relative_to(ROOT).as_posix()


# --- Rule 1: agents get data only through run_sql() -- no direct HTTP -------------------------------------
def test_agents_never_import_network_libraries():
    bad = []
    for f in py_files("app/agents"):
        hits = {m for m in imports_of(f) if m.split(".")[0] in NETWORK_MODULES}
        if hits:
            bad.append(f"{rel(f)} imports {sorted(hits)}")
    assert not bad, "Agents must get data only via run_sql() (Zetaris), never direct HTTP:\n" + "\n".join(bad)


# --- Rule 1b: agents never use setup-only DDL (CREATE DATASOURCE) ------------------------------------------
def test_agents_never_use_setup_ddl():
    bad = [f"{rel(f)}:{i}" for f in py_files("app/agents")
           for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1) if re.search(r"setup\s*=\s*True", line)]
    assert not bad, "run_ddl(setup=True) is for scripts/ only, never agents:\n" + "\n".join(bad)


# --- Rule 2: never route through meterless/auto -------------------------------------------------------------
def test_no_meterless_auto():
    bad = [f"{rel(f)}:{i}" for f in py_files("app", "scripts", "run.py")
           for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1) if "meterless/auto" in line]
    assert not bad, "Never call meterless/auto - use lanes `fast` / `deep`:\n" + "\n".join(bad)


# --- Rule 3: no reading output_examples/ at runtime ---------------------------------------------------------
def test_runtime_never_reads_output_examples():
    bad = [f"{rel(f)}:{i}" for f in py_files("app", "run.py")
           for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1) if "output_examples" in line]
    assert not bad, "Runtime code must never read output_examples/ (no hard-coded outputs):\n" + "\n".join(bad)


# --- Rule 4: every agent writes trace -----------------------------------------------------------------------
def test_every_agent_uses_trace_logger():
    bad = [rel(f) for f in py_files("app/agents") if f.name != "__init__.py"
           and not any(m == TRACE_MODULE or m.startswith(TRACE_MODULE + ".") for m in imports_of(f))]
    assert not bad, f"Every agent must import the trace logger ({TRACE_MODULE}):\n" + "\n".join(bad)


# --- Rule 5: no secrets in any tracked file (spikes/, logs, fixtures included) ------------------------------
SECRET_PATTERNS = {
    "NVIDIA API key": re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    "Bearer token": re.compile(r"Bearer\s+[A-Za-z0-9._~+/\-]{20,}=*"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "password literal": re.compile(r"""(?i)(password|passwd|secret|token)\s*[=:]\s*["'][^"'\s{}<>]{8,}["']"""),
}
SECRET_ENV_KEY = re.compile(r"(?i)(TOKEN|KEY|PASSWORD|SECRET)")


def local_env_secrets():
    """Non-empty secret-looking values from the local .env (never printed)."""
    env = ROOT / ".env"
    if not env.exists():
        return []
    values = []
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        value = value.split(" #")[0].strip().strip("'\"")
        if SECRET_ENV_KEY.search(key) and len(value) >= 8:
            values.append((key.strip(), value))
    return values


def test_no_secrets_in_tracked_files():
    env_values = local_env_secrets()
    bad = []
    for f in tracked_files():
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary file
        for i, line in enumerate(text.splitlines(), 1):
            for label, pat in SECRET_PATTERNS.items():
                if pat.search(line):
                    bad.append(f"{rel(f)}:{i} looks like a {label}")
            for key, value in env_values:
                if value in line:
                    bad.append(f"{rel(f)}:{i} contains the value of {key} from .env")
    assert not bad, "Possible secrets in tracked files (values not shown):\n" + "\n".join(bad)


# --- Rule 6: .env is never tracked --------------------------------------------------------------------------
def test_env_file_not_tracked():
    assert not [rel(f) for f in tracked_files() if f.name == ".env"], ".env must never be committed"
