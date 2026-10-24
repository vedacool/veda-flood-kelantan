"""B-77 step 5 (Monday, only after the public repo exists): point every link at the public repo.

    python scripts/public_links.py                    # dry run: what would change, and what is left on purpose
    python scripts/public_links.py --apply            # write the changes (then commit in the public repo's clone)
    python scripts/public_links.py --to https://github.com/vedacool/<name> --apply

Only exact links to the private repo change. Lines that name the private repo on purpose (it stays private as build
evidence) are kept and listed, so a person can check them.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = "https://github.com/vedacool/veda"
PUBLIC = "https://github.com/vedacool/veda-kelantan"
# a private-repo link not followed by more of a repo name (so ...veda-kelantan is never matched)
LINK = re.compile(re.escape(PRIVATE) + r"(?![\w-])")
NAME = re.compile(r"vedacool/veda(?![\w-])")          # any mention of the private repo, link or not
# lines that must keep naming the private repo
KEEP = ("stays **PRIVATE and untouched**", "fresh mirror of", "never the private")
# never swept: this script (its PRIVATE constant would become the public link) and its test (the private links are
# its inputs) - B-98
SKIP = {"scripts/public_links.py", "tests/test_public_links.py"}


def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines() if p not in SKIP]


def plan(to):
    changes, kept = [], []
    for path in tracked():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "vedacool/veda" not in text:
            continue
        lines = text.splitlines(keepends=True)
        new = []
        for i, line in enumerate(lines, 1):
            if any(k in line for k in KEEP) or not LINK.search(line):
                if NAME.search(line):
                    kept.append((path, i, line.strip()))
                new.append(line)
                continue
            fixed = LINK.sub(to, line)
            changes.append((path, i, line.strip(), fixed.strip()))
            new.append(fixed)
        if "".join(new) != text:
            changes.append((path, None, "".join(new), None))
    return changes, kept


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--to", default=PUBLIC)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    changes, kept = plan(a.to.rstrip("/"))
    for path, line, old, new in changes:
        if line is not None:
            print(f"CHANGE {path.relative_to(ROOT)}:{line}\n   - {old}\n   + {new}")
    for path, line, text in kept:
        print(f"KEEP   {path.relative_to(ROOT)}:{line}  {text[:110]}")
    if a.apply:
        for path, line, text, _ in changes:
            if line is None:
                path.write_text(text, encoding="utf-8", newline="")
        print(f"applied: {len({c[0] for c in changes if c[1] is None})} files")
    else:
        print("dry run - nothing written (add --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
