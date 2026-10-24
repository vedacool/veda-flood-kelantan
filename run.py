"""Ask VEDA one question from the command line (B-12; the full CLI + API come in B-19).

    python run.py "Is Rantau Panjang at risk?"            short live progress, then the answer
    python run.py --verbose "Is Rantau Panjang at risk?"  every trace line as a sentence
    python run.py --replay nov2024 --at "2024-11-26 18:00" "Rantau Panjang selamat ke?"   flood replay (B-70)
"""
import argparse
import sys
import time

from dotenv import load_dotenv

from app import config, progress, trace


def progress_printer():
    """A listener for loop.run(on_step=...): one short line per step, as it happens (B-17)."""
    t0 = time.monotonic()

    def show(rec):
        line = progress.describe(rec)
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
    ap.add_argument("--at", help="replay time in MYT, 'YYYY-MM-DD HH:MM' (default: the scenario's first scene; "
                                 "offline: only the scene's recorded times)")
    args = ap.parse_args(argv[1:])
    question = " ".join(args.question) or "Is Rantau Panjang at risk of flooding?"
    at = None
    if args.replay:                  # the API's own check (A-P3-5): the replay window, the time format, recorded times
        from app.main import BadInput, parse_input
        try:
            _, _, at = parse_input(question, args.replay, args.at or config.REPLAYS[args.replay]["default_at"])
        except BadInput as e:
            print(str(e).replace(" / ", "\n"))         # a notice, never a verdict
            return 2
    result = loop.run(question, quiet=not args.verbose, on_step=None if args.verbose else progress_printer(),
                      replay=args.replay, at=at, default_scene=True)
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
