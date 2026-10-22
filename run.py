"""Ask VEDA one question from the command line (B-12; the full CLI + API come in B-19).

    python run.py "Is Rantau Panjang at risk?"            short live progress, then the answer
    python run.py --verbose "Is Rantau Panjang at risk?"  every trace line as a sentence
    python run.py --replay nov2024 --at "2024-11-26 18:00" "Rantau Panjang selamat ke?"   flood replay (B-70)
"""
import argparse
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

from app import config, trace

STEP_LABELS = {"plan": "Understanding the question", "gather": "Checking river gauges, rain and warnings",
               "forecast": "Working out the risk", "draft": "Writing the answer", "critique": "Checking the answer",
               "revise": "Fixing the answer"}


def progress_printer():
    """A listener for loop.run(on_step=...): one short line per step, as it happens (B-17)."""
    t0 = time.monotonic()

    def show(rec):
        a, out = rec["action"], rec.get("output_summary") or ""
        line = None
        if a == "state":
            line = f"> {STEP_LABELS.get(rec['input_summary'], rec['input_summary'])}"
        elif a == "route":
            line = f"  {out}: {rec.get('decision') or ''}"
        elif a == "forecast.verdict":
            line = f"  verdict {out}"
        elif a == "critic.review":
            line = f"  review: {out}"
        elif a == "budget":
            line = f"  ! {out}"
        elif a == "replay":
            line = f"  {out} ({rec.get('decision')})"
        elif rec["status"] == "failed" and a not in ("run_end",):
            line = f"  ! {rec['agent_name']}: {out}"
        if line:
            print(f"{time.monotonic() - t0:6.1f}s {trace.redact(line)[:150]}", flush=True)
    return show


def main(argv):
    load_dotenv(config.ROOT / ".env")
    from app import loop
    ap = argparse.ArgumentParser(description="Ask VEDA one question")
    ap.add_argument("question", nargs="*")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--replay", choices=sorted(config.REPLAYS), help="replay a past flood (B-70)")
    ap.add_argument("--at", help="replay time in MYT, 'YYYY-MM-DD HH:MM' (default: the scenario's first scene)")
    args = ap.parse_args(argv[1:])
    question = " ".join(args.question) or "Is Rantau Panjang at risk of flooding?"
    at = None
    if args.replay:
        at = datetime.strptime(args.at or config.REPLAYS[args.replay]["default_at"], "%Y-%m-%d %H:%M").replace(
            tzinfo=config.MYT)
    result = loop.run(question, quiet=not args.verbose, on_step=None if args.verbose else progress_printer(),
                      replay=args.replay, at=at)
    answer = result["answer"]
    print("\n" + "=" * 72)
    print(trace.redact(answer["text"]))
    print(answer["safety_line"])
    print("=" * 72)
    print(f"status={result['status']} drafted_by={answer['drafted_by']} time={result['timing'].get('total')} s "
          f"trace={result['trace']}")
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
