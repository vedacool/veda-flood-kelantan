"""Ask VEDA one question from the command line (B-12; the full CLI + API come in B-19).

    python run.py "Is Rantau Panjang at risk?"            short live progress, then the answer
    python run.py --verbose "Is Rantau Panjang at risk?"  every trace line as a sentence
"""
import sys
import time

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
        elif rec["status"] == "failed" and a not in ("run_end",):
            line = f"  ! {rec['agent_name']}: {out}"
        if line:
            print(f"{time.monotonic() - t0:6.1f}s {trace.redact(line)[:150]}", flush=True)
    return show


def main(argv):
    load_dotenv(config.ROOT / ".env")
    from app import loop
    verbose = "--verbose" in argv
    question = " ".join(a for a in argv[1:] if a != "--verbose") or "Is Rantau Panjang at risk of flooding?"
    result = loop.run(question, quiet=not verbose, on_step=None if verbose else progress_printer())
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
