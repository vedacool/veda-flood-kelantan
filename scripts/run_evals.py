"""Run VEDA's eval scenarios offline and print a pass/fail table (B-58 safety evals; B-59 grows the set).

    python scripts/run_evals.py                 # every scenario in tests/evals/*/
    python scripts/run_evals.py safety          # one folder

Each scenario (tests/evals/<set>/<name>.json) gives a question, optionally a replay scene, a data situation
("stale_hours": the controlling gauge is that much older) and a stand-in AI ("llm": the explanation it writes and
whether the Critic approves, rejects or is down - used for the hostile cases - and, Part 7, "judge": the level the
stand-in AI gives with its cited fact ids), plus what the answer must and must
not contain. Runs in SAMPLE_MODE from the committed fixtures: no network, no keys. Real agent logic throughout.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EVALS = ROOT / "tests" / "evals"


def stand_in(spec):
    """The scenario's stand-in for Nemotron: writes the given explanation; the Critic approves / rejects / is down
    ("down" = both its lanes fail)."""
    from app.adapters import nightshift
    from app.agents import critic
    spec = spec or {}

    def llm(lane, messages, agent, **kw):
        if messages[0]["content"] == critic.JUDGE_SYSTEM:      # Part 7: the facts-only judgement (draft failed)
            if spec.get("critic", "approve") == "down":
                raise nightshift.NightshiftError("eval: Critic AI unavailable")
            return SimpleNamespace(data=dict(spec.get("judge") or {}), text="")
        if messages[0]["content"] in (critic.CRITIC_SYSTEM, critic.SMALL_SYSTEM):   # the Critic, on the deep or the fallback fast lane
            if spec.get("critic", "approve") == "down" or (spec.get("critic") == "deep_down" and lane == "deep"):
                raise nightshift.NightshiftError("eval: Critic AI unavailable")
            decision = "approve" if spec.get("critic") == "deep_down" else spec.get("critic", "approve")
            problems = [] if decision == "approve" else [{"type": "unclear", "detail": "eval rejection"}]
            return SimpleNamespace(data={"decision": decision, "problems": problems, "fix": "eval",
                                         "ok": decision == "approve", "reason": "eval rejection",
                                         **(spec.get("judge") or {})}, text="")      # Part 7: the AI's own level
        if spec.get("explanation") is None:
            raise nightshift.NightshiftError("eval: no explanation")
        return SimpleNamespace(data={"explanation": spec["explanation"]}, text="")
    return llm


def _clock_plus(hours):
    from app.adapters import zetaris
    from app.agents import data_agent
    now = data_agent._clock(zetaris.run_sql(data_agent.CLOCK_SQL, agent="Eval", purpose="data clock"))
    return now + timedelta(hours=hours)


def run_one(sc, log_dir):
    """Run one scenario -> (passed, problems, result)."""
    from app import config, gazetteer, loop, trace
    gazetteer.clear_cache()
    at = None
    if sc.get("replay"):
        at = datetime.strptime(sc["at"], "%Y-%m-%d %H:%M").replace(tzinfo=config.MYT)
    now = None
    if sc.get("stale_hours"):
        trace.start_run("eval clock", log_dir=log_dir, quiet=True)
        try:
            now = _clock_plus(sc["stale_hours"])
        finally:
            trace.end_run()
    from app.agents import data_agent
    real_gather = data_agent.gather
    if sc.get("met_warning"):          # test-only stub (rule A evals): a SYNTHETIC MetMalaysia warning for this run only
        def gather(*a, **k):
            ev = real_gather(*a, **k)
            ev["met_warnings"] = {"status": "ok", "active": [sc["met_warning"]], "note": "SYNTHETIC warning (eval stub)"}
            return ev
        data_agent.gather = gather
    real_resolve = gazetteer.resolve
    if sc.get("zetaris_down"):         # test-only stub (audit 24 Oct P1-3): Zetaris cannot be reached for this run
        from app.adapters import zetaris

        def resolve(*a, **k):
            raise zetaris.ZetarisError("connection", "eval stub: Zetaris cannot be reached")
        gazetteer.resolve = resolve
    try:
        r = loop.run(sc["question"], llm=stand_in(sc.get("llm")), log_dir=log_dir, quiet=True,
                     replay=sc.get("replay"), at=at, now=now, default_scene=True)
    finally:
        data_agent.gather, gazetteer.resolve = real_gather, real_resolve
    text = r["answer"]["text"] + "\n" + r["answer"]["safety_line"]
    ex, problems = sc.get("expect", {}), []
    verdict = (r.get("forecast") or {}).get("verdict")
    if "verdict" in ex and verdict != ex["verdict"]:
        problems.append(f"verdict {verdict}, expected {ex['verdict']}")
    if ex.get("path") and (r.get("plan") or {}).get("effort") != ex["path"]:
        problems.append(f"path {(r.get('plan') or {}).get('effort')}, expected {ex['path']}")
    if ex.get("drafted_by") and r["answer"].get("drafted_by") != ex["drafted_by"]:
        problems.append(f"drafted_by {r['answer'].get('drafted_by')}, expected {ex['drafted_by']}")
    if ex.get("language") and r["answer"].get("language") != ex["language"]:
        problems.append(f"language {r['answer'].get('language')}, expected {ex['language']}")
    if ex.get("first_line") and text.split("\n")[0] != ex["first_line"]:
        problems.append(f"first line {text.split(chr(10))[0]!r}")
    problems += [f"missing {m!r}" for m in ex.get("must", []) if m not in text]
    problems += [f"must not contain {m!r}" for m in ex.get("must_not", []) if m in text]
    if ex.get("must_trace"):                       # B-71: a line the trace must hold (the agents' collaboration)
        steps = open(r["trace"], encoding="utf-8").read()
        problems += [f"trace lacks {m!r}" for m in ex["must_trace"] if m not in steps]
    return not problems, problems, r


def load(sets=None):
    folders = [EVALS / s for s in sets] if sets else sorted(p for p in EVALS.iterdir() if p.is_dir())
    return [(f.parent.name, json.loads(f.read_text(encoding="utf-8"))) for d in folders for f in sorted(d.glob("*.json"))]


def main(argv=None):
    sets = (argv if argv is not None else sys.argv[1:]) or None
    saved = dict(os.environ)                   # offline judge conditions for the run, restored afterwards
    os.environ["SAMPLE_MODE"] = "true"
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        os.environ.pop(key, None)
    try:
        return _run(load(sets))
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _run(scenarios):
    passed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for group, sc in scenarios:
            ok, problems, _ = run_one(sc, tmp)
            passed += ok
            print(f"{'PASS' if ok else 'FAIL'}  {group}/{sc['name']:36} {sc.get('about', '')}")
            for p in problems:
                print(f"        - {p}")
    print(f"\n{passed}/{len(scenarios)} passed ({100 * passed // max(1, len(scenarios))}%)")
    return 0 if passed == len(scenarios) else 1


if __name__ == "__main__":
    sys.exit(main())
