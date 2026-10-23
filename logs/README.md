# logs/

Every run writes its trace here: **`logs/trace-<run_id>.jsonl`**, one JSON line per agent step, Zetaris call and
Nightshift call (timestamp, agent, action, input / output summary, target agent, confidence, retry count, status,
source, duration, and for model calls the model that actually answered with its Nightshift receipt id). Phone, IC,
email and secret values are masked before anything is written.

The same steps go to **stdout**: the CLI prints one sentence per step (`python run.py "..."`, add `--verbose` for
every line); the web server (`python -m app.main`, or `docker logs` in Docker) prints one short progress line per
important step, prefixed with the run id - never the question text.

These files stay on the machine that ran VEDA (`logs/*.jsonl` is gitignored: live traces hold JPS readings, which are
not redistributed). Committed examples to read instead:
- `output_examples/*.trace.jsonl` - 6 SAMPLE_MODE runs (scenes), each with its answer JSON;
- `data/sample/live_traces/` - recorded **live** runs with the Critic's AI review, JPS readings redacted (labelled
  "Recorded live run · date time MYT").
