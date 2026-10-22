"""Git hook entry points (B-65): pre-commit guard + commit-msg backlog-ID check.

Called from .githooks/; turn on once per clone with:
    git config core.hooksPath .githooks

    python scripts/precommit.py                  # pre-commit: regenerate CODEMAP, run guard tests + secret scan
    python scripts/precommit.py msg <msg-file>   # commit-msg: require a backlog ID (B-xx / S-xx)
"""
import re
import subprocess
import sys
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


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "msg":
        sys.exit(commit_msg(sys.argv[2]))
    sys.exit(pre_commit())
