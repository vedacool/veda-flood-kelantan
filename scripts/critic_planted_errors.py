"""Test harness (not live use): does the Critic's AI review reject planted errors and pass correct explanations?

    python scripts/critic_planted_errors.py [--tries 3] [--restart-nightshift]

The facts are the SYNTHETIC rising-river card for Kota Bharu (made-up readings), built offline by VEDA's own code.
Four explanations are reviewed with the production prompt (critic.SMALL_SYSTEM) through Nightshift: a correct one and a
planted error in English and in Malay. The planted errors exist only here - never in VEDA or its answers. Needs live
Nightshift (.env); prints one line per call and a summary. Writes nothing.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CASES = [  # (name, language, explanation, should the review approve it?)
    ("correct_en", "en", "The river at Kota Bharu is 0.65 m above its Alert level, so keep watching official updates.",
     True),
    ("planted_contradiction_en", "en", "The river at Kota Bharu is below its Alert level, so there is nothing to "
                                       "worry about.", False),
    ("correct_ms", "ms", "Paras sungai di Kota Bharu 0.65 m di atas paras Waspada, jadi teruskan memantau maklumat "
                         "rasmi.", True),
    ("planted_exaggeration_ms", "ms", "Sungai di Kota Bharu sudah melepasi paras Bahaya dan semua orang mesti "
                                      "berpindah sekarang.", False),
]
RESTART = (r"Get-Process | Where-Object { $_.Path -like '*Nightshift*' -or $_.Path -like '*meterless*' } | "
           r"Stop-Process -Force -Confirm:$false; Start-Sleep -Seconds 2; "
           r"Start-Process (Join-Path $env:LOCALAPPDATA 'Nightshift\meterless-runtime.exe'); Start-Sleep -Seconds 8")


def facts():
    """The card's facts (EN and BM) from an offline run of the SYNTHETIC rising-river scene."""
    os.environ["SAMPLE_MODE"] = "true"
    from app import config, loop
    from app.agents import critic
    at = datetime.strptime("2024-11-25 18:00", "%Y-%m-%d %H:%M").replace(tzinfo=config.MYT)
    with tempfile.TemporaryDirectory() as d:
        r = loop.run("Is Kota Bharu at risk in the next two days?", replay="synthetic_rising", at=at, log_dir=d,
                     quiet=True)
    out = {lang: critic.judge_facts(r["card"], r["forecast"], lang)[0] for lang in ("en", "ms")}
    os.environ["SAMPLE_MODE"] = "false"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--restart-nightshift", action="store_true", help="Windows: restart Nightshift before each call "
                                                                       "(its memory is held in the running process)")
    args = ap.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    card_facts = facts()
    from app import trace
    from app.adapters import nightshift
    from app.agents import critic
    rows = []
    with tempfile.TemporaryDirectory() as d:
        trace.start_run("Critic planted-error harness", log_dir=Path(d), quiet=True)
        for i in range(args.tries):
            for name, lang, text, should_pass in CASES:
                if args.restart_nightshift:
                    subprocess.run(["powershell", "-NoProfile", "-Command", RESTART], capture_output=True, timeout=90)
                msgs = [{"role": "system", "content": critic.SMALL_SYSTEM},
                        {"role": "user", "content": json.dumps({"FACTS": card_facts[lang], "EXPLANATION": text},
                                                               ensure_ascii=False)}]
                t = time.monotonic()
                try:
                    r = nightshift.chat(nightshift.AI_LANE, msgs, agent="Critic", json_mode=True,
                                        max_tokens=critic.SMALL_MAX_TOKENS, budget_s=critic.REVIEW_CAP_S,
                                        max_attempts=1, purpose="planted-error harness")
                    ok = (r.data or {}).get("ok")
                    right = ok is should_pass
                    row = {"try": i + 1, "case": name, "s": round(time.monotonic() - t, 1), "model": r.served_model,
                           "ok": ok, "right": right, "reason": str((r.data or {}).get("reason"))[:90]}
                except nightshift.NightshiftError as e:
                    row = {"try": i + 1, "case": name, "s": round(time.monotonic() - t, 1), "error": str(e)[:90]}
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
        trace.end_run()
    for name, _, _, should_pass in CASES:
        rs = [r for r in rows if r["case"] == name]
        answered = [r for r in rs if "error" not in r]
        print(f"{name:28} {'should pass' if should_pass else 'planted   '}: right {sum(r['right'] for r in answered)} "
              f"of {len(answered)} answered ({len(rs) - len(answered)} not answered)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
