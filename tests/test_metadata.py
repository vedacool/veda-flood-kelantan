"""B-24 / D-12: metadata.json is valid JSON, has the agreed shape (no G42 Agentathon fields), and says nothing the
README does not say - where each sponsor sits, the models, the data sources, sample mode and the entry points."""
import json

from app import trace

META = json.loads((trace.ROOT / "metadata.json").read_text(encoding="utf-8"))
README = (trace.ROOT / "README.md").read_text(encoding="utf-8")


def test_shape():
    assert set(META) >= {"project", "track", "team", "agents", "sponsors", "data_sources", "sample_mode", "entrypoints"}
    assert set(META["sponsors"]) == {"zetaris", "meterless_engine", "meterless_nightshift", "nvidia", "cursor"}
    text = json.dumps(META).lower()
    assert "compass" not in text and "use_case_id" not in text          # G42 Agentathon fields are not ours


def test_project_track_team_match_the_readme():
    assert META["track"] in README and META["hackathon"] in README and f"Team {META['team']['name']}" in README
    assert all(m in README for m in META["team"]["members"])
    assert META["project"]["full_name"] in README and "MIT License" in README


def test_agents_and_models_match_the_readme():
    for a in META["agents"]:
        assert f"**{a['name']}** (`{a['files'][0]}`" in README, a["name"]
        if a["model"]:
            assert a["model"] in README and "meterless/fast" in a["via"]
    assert {a["name"] for a in META["agents"] if a["model"]} == {"Coordinator", "Critic"}
    assert META["sponsors"]["nvidia"]["models"] == ["nvidia/nemotron-3.5-lightning-30b-a3b"]
    assert "meterless/deep" not in json.dumps(META) and "meterless/auto" not in json.dumps(META)


def test_sponsor_tests_and_code_paths_exist():
    for cmd in META["sponsors"]["meterless_engine"]["tests"]:
        assert cmd in README
    for s in META["sponsors"].values():
        for path in s.get("code", []):
            assert (trace.ROOT / path).exists(), path


def test_data_sources_are_the_readmes():
    for d in META["data_sources"]:
        if d.get("url"):
            assert d["url"].rstrip("/") in README, d["name"]
        assert d["name"].split(" ")[0].split(":")[0] in README, d["name"]
    assert any(d["licence"] == "ODbL" for d in META["data_sources"]) and "ODbL" in README
    assert any(d["mode"] == "synthetic" for d in META["data_sources"])


def test_entrypoints_are_in_the_readme():
    for name, cmd in META["entrypoints"].items():
        assert cmd in README, name
    assert "SAMPLE_MODE=true" in README and META["sample_mode"]["how"] == "SAMPLE_MODE=true"
