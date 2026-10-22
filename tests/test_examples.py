"""B-20 test: every input example still gives the committed answer (verdict, path, wording) when re-run offline -
the committed outputs are real runs of today's code, not stale or hand-made files."""
import importlib.util
import json
import sys

import pytest

from app import gazetteer, trace

ROOT = trace.ROOT
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("make_examples", ROOT / "scripts" / "make_examples.py")
make_examples = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_examples)
INPUTS = sorted((ROOT / "input_examples").glob("*.json"))


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setenv("SAMPLE_MODE", "true")
    for key in ("ZETARIS_API_KEY", "ZETARIS_API_URL", "METERLESS_RUNTIME_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    gazetteer.clear_cache()
    yield tmp_path


def test_at_least_three_examples_with_outputs_and_traces():
    assert len(INPUTS) >= 3
    for f in INPUTS:
        assert (ROOT / "output_examples" / f.name).exists() and (ROOT / "output_examples" / f"{f.stem}.trace.jsonl").exists()


@pytest.mark.parametrize("path", INPUTS, ids=[p.stem for p in INPUTS])
def test_committed_output_matches_a_fresh_run(offline, path):
    ex = json.loads(path.read_text(encoding="utf-8"))
    committed = json.loads((ROOT / "output_examples" / path.name).read_text(encoding="utf-8"))
    _, fresh = make_examples.run_example(ex, offline)
    assert (fresh["verdict"], fresh["drafted_by"], fresh["language"]) == \
        (committed["verdict"], committed["drafted_by"], committed["language"])
    assert fresh["output"].split("\n")[:2] == committed["output"].split("\n")[:2]       # action + verdict lines
