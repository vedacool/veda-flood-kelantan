"""Git hook entry points (B-65): pre-commit guard + commit-msg backlog-ID check.

Called from .githooks/; turn on once per clone with:
    git config core.hooksPath .githooks

    python scripts/precommit.py                  # pre-commit: regenerate CODEMAP, run guard tests + secret scan
    python scripts/precommit.py msg <msg-file>   # commit-msg: require a backlog ID (B-xx / S-xx)
    python scripts/precommit.py push             # pre-push (refs on stdin): full suite + evals, see pre_push()
"""
import fnmatch
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKLOG_ID = re.compile(r"\b[BS]-\d{2,3}\b")


def pre_commit():
    """Regenerate CODEMAP (and stage it), then run the architecture guard tests. Non-zero = commit blocked."""
    subprocess.run([sys.executable, "scripts/codemap.py"], cwd=ROOT, check=True)
    subprocess.run(["git", "add", "docs/CODEMAP.md"], cwd=ROOT, check=True)
    tests = subprocess.run([sys.executable, "-m", "pytest", "tests/test_architecture.py", "-q", "--no-header", "-p",
                            "no:cacheprovider"], cwd=ROOT)
    if tests.returncode != 0:
        print("\nCOMMIT BLOCKED: an architecture rule or the secret scan failed (see above).")
        print("Fix the code - do not skip the hook.")
        return 1
    return 0


def commit_msg(path):
    """Require a backlog ID in the first line; merges and reverts are allowed."""
    first = Path(path).read_text(encoding="utf-8").strip().splitlines()[0] if Path(path).read_text(encoding="utf-8").strip() else ""
    if first.startswith(("Merge ", "Revert ")) or BACKLOG_ID.search(first):
        return 0
    print(f"COMMIT BLOCKED: message needs a backlog ID, e.g. 'feat: B-02 trace logger'. Got: {first!r}")
    return 1


# B-99 (Cowork 25 Oct): CI minutes are scarce, so every push is gated locally. The same paths CI ignores
# (.github/workflows/ci.yml paths-ignore) skip the gate: a docs- or media-only push runs nothing.
DOC_ONLY = ("docs/*", "*.md", "*.png", "*.jpg", "*.mp4")
CODE_DIRS = ("app/", "tests/", "scripts/", "veda/", "data/", "db/", "demo/")
ZERO = "0" * 40


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout


def _pushed_files(stdin_text):
    """Files changed by the commits being pushed (git passes '<local ref> <local sha> <remote ref> <remote sha>')."""
    files = set()
    for line in stdin_text.splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO:                 # a branch delete pushes no files
            continue
        local, remote = parts[1], parts[3]
        base = remote if remote != ZERO else (_git("merge-base", local, "origin/main").strip() or None)
        if base is None:
            return None                                         # nothing to compare with: run the gate
        files |= {f for f in _git("diff", "--name-only", f"{base}..{local}").splitlines() if f}
    return files


def _doc_only(files):
    return bool(files) and all(any(fnmatch.fnmatch(f, pat) for pat in DOC_ONLY) for f in files)


def _counts(text, pattern):
    m = re.findall(pattern, text)
    return m[-1] if m else "?"


def pre_push(stdin_text):
    """Block the push unless the working tree is committed and the full offline suite + evals pass."""
    files = _pushed_files(stdin_text)
    if files is not None and _doc_only(files):
        print(f"pre-push: docs / media only ({len(files)} file(s)) - no tests needed.")
        return 0
    dirty = [ln for ln in _git("status", "--porcelain").splitlines()
             if not ln.startswith("??") or ln[3:].startswith(CODE_DIRS)]
    if dirty:
        print("PUSH BLOCKED: the working tree has uncommitted changes (the tests run on the working tree, so they must")
        print("match what is pushed). Commit or stash them first:")
        print("\n".join("  " + ln for ln in dirty[:10]))
        return 1
    start = time.monotonic()
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    env = {**os.environ, "SAMPLE_MODE": "true", "PYTHONIOENCODING": "utf-8"}
    evals = subprocess.run([sys.executable, "scripts/run_evals.py"], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
    took = time.monotonic() - start
    summary = (tests.stdout.strip().splitlines() or ["?"])[-1]
    evals_line = _counts(evals.stdout, r"\d+/\d+ passed[^\n]*")
    print(f"pre-push: tests: {summary} | evals: {evals_line} | {took:.0f} s")
    if tests.returncode != 0 or evals.returncode != 0:
        print(tests.stdout[-3000:] if tests.returncode != 0 else evals.stdout[-3000:])
        print("PUSH BLOCKED: a test or an eval failed (see above). Fix it - do not skip the hook.")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "msg":
        sys.exit(commit_msg(sys.argv[2]))
    if len(sys.argv) >= 2 and sys.argv[1] == "push":
        sys.exit(pre_push(sys.stdin.read()))
    sys.exit(pre_commit())
