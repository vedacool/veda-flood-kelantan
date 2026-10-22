"""Ask VEDA one question from the command line (B-12; the full CLI + API come in B-19).

    python run.py "Is Rantau Panjang at risk?"
"""
import sys

from dotenv import load_dotenv

from app import config, trace


def main(argv):
    load_dotenv(config.ROOT / ".env")
    from app import loop
    question = " ".join(argv[1:]) or "Is Rantau Panjang at risk of flooding?"
    result = loop.run(question)
    answer = result["answer"]
    print("\n" + "=" * 72)
    print(trace.redact(answer["text"]))
    print(answer["safety_line"])
    print("=" * 72)
    print(f"status={result['status']} drafted_by={answer['drafted_by']} trace={result['trace']}")
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
