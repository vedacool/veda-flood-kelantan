"""Publish a recorded live run: copy logs/trace-<run_id>.jsonl into data/sample/live_traces/ with every JPS reading
redacted (B-75, organiser ruling 23 Oct 2026: JPS readings are not redistributed).

    python scripts/publish_trace.py logs/trace-20261025-101500-abcd.jsonl --label critic-ai-approved

Kept: steps, times, ids, step numbers, durations, the Critic's results and reasons, cited JPS thresholds and historic
peaks (they are published), Open-Meteo rain (mm). Every other river level in metres - readings, changes, distances to
thresholds (they reveal the reading), ranges, values inside AI explanations and inside the prompts sent to the AI -
becomes '[JPS reading — not redistributed]'. The first line says so. tests/test_no_jps_readings.py checks the result.
The unredacted original stays in logs/ (never committed).
"""
import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sample" / "live_traces"
MARK = "[JPS reading — not redistributed]"
NOTE = ("JPS readings not redistributed, per organiser ruling 23 Oct 2026. Redacted: every river level derived from a "
        "JPS reading (readings, changes, distances to Alert / Danger, projected ranges, values in the AI explanations "
        "and in the prompts sent to the AI, reconcile values) reads '[JPS reading — not redistributed]'. Kept: steps, "
        "timings, Critic results and reasons, cited JPS thresholds and historic peaks, Open-Meteo rain, times, run ids. "
        "The unredacted original is kept privately by the team outside the repo and is never committed.")
NUM = r"-?\d+(?:\.\d+)?"
RANGE = re.compile(rf"(?<![\w.]){NUM}\s?[^\w\s\[]{{1,4}}\s?(?:{NUM}\s?m(?![m\w])|\[JPS)")
TRUNC = re.compile(rf"(?<![\w.]){NUM}(?=\.\.\.$|…$)")      # a summary cut off before its unit
METRES = re.compile(rf"(?<![\w.]){NUM}\s?m(?![m\w])")
LEVEL_KEYS = re.compile(r"(level|change_|rate|projection|min_7d|raw_level|diff_m|level_m|range|^min$|^max$|^value$)")
KEEP_FIELDS = ("timestamp", "trace_id", "run_id", "step", "duration_ms", "retry_count")


def published_values():
    """Cited thresholds and historic peaks: public, so they may stay as metre values."""
    keep = set()
    for r in csv.DictReader((ROOT / "data" / "stations_mapping.csv").open(encoding="utf-8")):
        keep |= {round(float(v), 2) for k, v in r.items() if k.startswith("jps") and k.endswith("_m") and v}
    for r in csv.DictReader((ROOT / "data" / "historic_peaks.csv").open(encoding="utf-8")):
        if r.get("peak_m"):
            keep.add(round(float(r["peak_m"]), 2))
    return keep


def redact_text(s, keep):
    s = RANGE.sub(lambda m: MARK if not m.group(0).endswith("[JPS") else MARK + " [JPS", s)
    s = s.replace(MARK + " [JPS reading — not redistributed]", MARK)
    s = TRUNC.sub(MARK, s)
    s = re.sub(rf"(?<![\w.]){NUM}[^\x00-\x7f]+(?=\[JPS)", "", s)

    def one(m):
        v = float(re.match(NUM, m.group(0)).group(0))
        return m.group(0) if round(abs(v), 2) in keep and v >= 0 else MARK
    return METRES.sub(one, s)


def walk(x, keep, key=""):
    if isinstance(x, dict):
        return {k: walk(v, keep, k) for k, v in x.items()}
    if isinstance(x, list):
        return [walk(v, keep, key) for v in x]
    if isinstance(x, str):
        return redact_text(x, keep)
    if isinstance(x, (int, float)) and not isinstance(x, bool) and LEVEL_KEYS.search(key or ""):
        return MARK
    return x


def redact_records(records, keep=None):
    keep = published_values() if keep is None else keep
    out = []
    for d in records:
        nd = walk(d, keep)
        nd.update({k: d[k] for k in KEEP_FIELDS if k in d})       # times, ids and step numbers are not readings
        out.append(nd)
    return out


def publish(path, label, out_dir=OUT):
    records = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    records = [r for r in records if "action" in r]
    run_id = records[0]["run_id"]
    when = datetime.strptime(run_id[:13], "%Y%m%d-%H%M")
    target = Path(out_dir) / f"{when:%Y-%m-%d_%H%M}MYT_{label}_{run_id}.trace.jsonl"
    lines = [{"redaction": NOTE, "run_id": run_id}] + redact_records(records)
    target.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n", encoding="utf-8", newline="\n")
    return target


def main(argv=None):
    ap = argparse.ArgumentParser(description="Publish a recorded live run with JPS readings redacted (B-75)")
    ap.add_argument("traces", nargs="+", help="logs/trace-<run_id>.jsonl")
    ap.add_argument("--label", required=True, help="short tag in the file name, e.g. critic-ai-approved")
    args = ap.parse_args(argv)
    for t in args.traces:
        print("published:", publish(t, args.label).relative_to(ROOT))
    print("now run: python -m pytest tests/test_no_jps_readings.py -q, and add a row to data/sample/live_traces/README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
