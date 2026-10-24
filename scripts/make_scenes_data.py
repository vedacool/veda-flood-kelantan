"""B-91: build data/scenes/scenes_data.json - the inputs each scene shows before its run - from the fixtures.

    python scripts/make_scenes_data.py           # rebuild (offline: SAMPLE_MODE, the same path a run takes)
    python scripts/make_scenes_data.py --check   # fail if the committed file differs from what the fixtures give

Only the Data & Reconciler's inputs are kept (river levels with their fixture query hash, rain, warnings, what was
missing or stale) - never the verdict. Demo data only: replay readings reported in the news, or made up.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["SAMPLE_MODE"] = "true"                 # offline: the recorded fixtures, never live data

from app import scenes  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = json.dumps(scenes.build_all(), ensure_ascii=False, indent=1) + "\n"
    if a.check:
        old = scenes.DATA.read_text(encoding="utf-8") if scenes.DATA.exists() else ""
        if old != text:
            sys.exit("data/scenes/scenes_data.json differs from the fixtures - run scripts/make_scenes_data.py")
        print("scenes_data.json matches the fixtures")
        return 0
    scenes.DATA.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {scenes.DATA.relative_to(ROOT)} ({len(json.loads(text)['scenes'])} scenes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
