"""Generate output_examples/ from input_examples/ (B-20): real, unedited runs - nothing hand-written.

    python scripts/make_examples.py            # offline (SAMPLE_MODE, recorded data) - what the committed files are
    python scripts/make_examples.py --live     # live Zetaris + Nightshift (answers then include the AI explanation)

Each input (input_examples/NN_name.json: question, optional replay / at / stale_hours) runs through the real agent
loop; the API's JSON answer is saved as output_examples/NN_name.json and its trace as NN_name.trace.jsonl.
VEDA never reads output_examples/ at runtime (guard test).
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INPUTS = ROOT / "input_examples"
OUTPUTS = ROOT / "output_examples"


def run_example(ex, log_dir):
    from app import config, gazetteer, loop
    from app.main import result_json
    import run_evals                                    # same clock handling as the eval scenarios
    gazetteer.clear_cache()
    at = (datetime.strptime(ex["at"], "%Y-%m-%d %H:%M").replace(tzinfo=config.MYT) if ex.get("replay") else None)
    now = None
    if ex.get("stale_hours"):
        from app import trace
        trace.start_run("example clock", log_dir=log_dir, quiet=True)
        try:
            now = run_evals._clock_plus(ex["stale_hours"])
        finally:
            trace.end_run()
    r = loop.run(ex["question"], quiet=True, log_dir=log_dir, replay=ex.get("replay"), at=at, now=now,
                 default_scene=True)
    return r, result_json(r)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(ROOT / "scripts"))
    if args.live:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    else:
        os.environ["SAMPLE_MODE"] = "true"
        for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
            os.environ.pop(key, None)
    OUTPUTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for f in sorted(INPUTS.glob("*.json")):
            ex = json.loads(f.read_text(encoding="utf-8"))
            r, body = run_example(ex, tmp)
            shutil.copy(r["trace"], OUTPUTS / f"{f.stem}.trace.jsonl")
            body["log_file"] = f"output_examples/{f.stem}.trace.jsonl"
            body["input"] = {k: v for k, v in ex.items() if k != "about"}
            body["about"] = ex.get("about")
            body["mode"] = "live" if args.live else "SAMPLE_MODE (offline, recorded data)"
            (OUTPUTS / f"{f.stem}.json").write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8", newline="\n")
            print(f"{f.stem:28} {body['status']:8} verdict={body['verdict']} drafted_by={body['drafted_by']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
