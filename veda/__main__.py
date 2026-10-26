"""VEDA from the command line (B-92) - the same function as POST /api/v1/ask (app.api.ask), no web server needed.

    python -m veda ask "Is Tumpat safe tonight?"                 # plain text
    python -m veda ask "Kota Bharu banjir tak?" --lang bm --scene nov2024 --json
    python -m veda scenes
    python -m veda doctor                                         # B-106: is this machine ready? (read-only)

With no keys (no .env) it runs in offline sample mode and says so in one line; it never asks for keys.
Exit codes: 0 answered, 2 bad input, 3 busy.
"""
import argparse
import contextlib
import json
import os
import sys

try:
    from dotenv import load_dotenv
except ImportError:                 # B-106: the doctor still runs (and says so) when the packages are missing
    load_dotenv = None


def _mode_line():
    """Decide the mode with the server's rule (main.offline_reason): live, or offline sample mode with the reason
    (said in one line)."""
    from app import config
    if not config.demo_mode():
        load_dotenv(config.ROOT / ".env")
    if config.sample_mode():
        return "Offline sample mode: VEDA answers from its recorded and made-up scenes (no live data, no AI calls)."
    from app import main                       # audit 26 Oct: the server's own start-up rule (B-104), one rule
    reason = main.offline_reason()
    if reason:
        os.environ["SAMPLE_MODE"] = "true"     # this one-shot process only
        return (f"Offline sample mode ({reason}): VEDA answers from its recorded and made-up scenes "
                "(no live data, no AI calls).")
    note = main.nightshift_note()
    if note:
        return f"Live mode: river data through Zetaris; {note} - the answer is written by code."
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
    sub.add_parser("doctor", help="check this machine (read-only) and say which mode VEDA will start in")
    sub.add_parser("init-env", help="installers: .env from .env.example, only when .env does not exist")
    s = sub.add_parser("start", help="installers: start the web server on 127.0.0.1 and print the link")
    s.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)
    if args.cmd in ("doctor", "init-env", "start"):                   # B-106: before any key is read or mode set
        from veda import doctor
        if args.cmd == "doctor":
            doctor.run()
            return 0                                                  # always 0: the lines say what to fix
        if args.cmd == "init-env":
            doctor.init_env()
            return 0
        return doctor.start(args.port)
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
