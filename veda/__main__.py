"""VEDA from the command line (B-92) - the same function as POST /api/v1/ask (app.api.ask), no web server needed.

    python -m veda ask "Is Tumpat safe tonight?"                 # plain text
    python -m veda ask "Kota Bharu banjir tak?" --lang bm --scene nov2024 --json
    python -m veda scenes

With no keys (no .env) it runs in offline sample mode and says so in one line; it never asks for keys.
Exit codes: 0 answered, 2 bad input, 3 busy.
"""
import argparse
import contextlib
import json
import os
import sys

from dotenv import load_dotenv


def _mode_line():
    """Decide the mode before VEDA is imported: keys -> live, no keys -> offline sample mode (said in one line)."""
    from app import config
    if not config.demo_mode():
        load_dotenv(config.ROOT / ".env")
    if config.sample_mode():
        return "Offline sample mode: VEDA answers from its recorded and made-up scenes (no live data, no AI calls)."
    if not (os.getenv("ZETARIS_API_KEY") and os.getenv("ZETARIS_API_URL")):
        os.environ["SAMPLE_MODE"] = "true"
        return ("Offline sample mode (no keys found): VEDA answers from its recorded and made-up scenes "
                "(no live data, no AI calls).")
    return "Live mode: river data through Zetaris, Nemotron through Meterless Nightshift."


def _text(a):
    lines = []
    if a.get("level"):
        lines.append(f"{a['place']}: {a['level_label']['bm' if a['language'] == 'bm' else 'en']} ({a['level']})"
                     + (f"  [{a['scene']}]" if a.get("scene") else ""))
        lines += ["What to do: " + " ".join(a["what_to_do"])] + [f"Why: {w}" for w in a["why"]]
        j = a["ai_judgement"]
        lines.append("Nemotron's judgement: " + (j if isinstance(j, str) else
                                                 f"rules {j.get('code_level')}, Nemotron {j.get('ai_level') or '-'}, "
                                                 f"final {j.get('final')} ({j.get('status')})"))
        lines.append(f"Critic: {'approved' if a['critic_checks']['approved'] else 'not approved'} "
                     f"(checked by {', '.join(a['critic_checks']['checked_by'])}; {len(a['critic_checks']['checks'])} "
                     "code checks)")
    else:
        lines.append(a.get("text") or "")
    lines.append("Steps: " + " · ".join(f"{s['step']} ({s['agent']})" for s in a["steps"]))
    lines += [a.get("disclaimer") or "", f"Run id: {a['run_id']} · mode: {a['mode']}"]
    return "\n".join(x for x in lines if x)


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m veda", description="Ask VEDA about flood risk in Kelantan.")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="ask one question")
    a.add_argument("question")
    a.add_argument("--lang", choices=("en", "bm"), default="en", help="answer language for the screens' words")
    a.add_argument("--scene", help="an offline scene id (see: python -m veda scenes)")
    a.add_argument("--json", action="store_true", help="print the API's JSON")
    sub.add_parser("scenes", help="list the offline scenes")
    args = p.parse_args(argv)
    print(_mode_line(), file=sys.stderr)
    from app import api
    if args.cmd == "scenes":
        for s in api.scenes():
            print(f"{s['id']:28} {s['title']} ({s['source']})")
        return 0
    try:
        with contextlib.redirect_stdout(sys.stderr):        # the agents' progress lines -> stderr; the answer -> stdout
            answer = api.ask(args.question, args.lang, args.scene)
    except api.BadInput as e:
        print(f"error ({e.code}): {e}", file=sys.stderr)
        return 3 if e.status == 429 else 2
    print(json.dumps(answer, ensure_ascii=False, indent=1) if args.json else _text(answer))
    return 0


if __name__ == "__main__":
    sys.exit(main())
