"""B1: the checking screen tags each step with its agent - from the trace's own step names, coloured as in /live."""
import re

from app import progress, trace

PAGE = (trace.ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")
LIVE = (trace.ROOT / "app" / "web" / "live.html").read_text(encoding="utf-8")


def js_object(name):
    body = PAGE.split(f"const {name} = {{", 1)[1].split("};", 1)[0]
    return dict(re.findall(r'(\w+): \[?"([^"]+)"', body))


def test_every_trace_step_has_an_agent_tag_and_nothing_else():
    agent_of = PAGE.split("const AGENT_OF = {", 1)[1].split("};", 1)[0]
    assert set(re.findall(r"(\w+): \[", agent_of)) == set(progress.STEP_LABELS)
    for stage, label in progress.STEP_LABELS.items():          # the page maps the same heading lines
        assert f'"{label}": "{stage}"' in PAGE


def test_who_does_what_matches_the_trace():
    """plan/route: Coordinator · gather: Data & Reconciler · forecast: Forecast · draft/revise: Coordinator calling
    Nemotron · critique: Critic (agent_name of the records inside each step)."""
    agent_of = js_object("AGENT_OF")
    assert agent_of == {"plan": "ag_coordinator", "gather": "ag_data", "forecast": "ag_forecast",
                        "draft": "ag_writer", "revise": "ag_writer", "critique": "ag_critic"}
    for key, en, ms in (("ag_coordinator", "Coordinator", "Penyelaras"), ("ag_data", "Data agent", "Ejen Data"),
                        ("ag_forecast", "Forecast agent", "Ejen Ramalan"),
                        ("ag_writer", "Coordinator + Nemotron", "Penyelaras + Nemotron"),
                        ("ag_critic", "Critic", "Penyemak")):
        assert f'{key}: "{en}"' in PAGE and f'{key}: "{ms}"' in PAGE


def test_offline_the_writing_step_does_not_claim_nemotron():
    """SAMPLE_MODE calls no model: the draft step is tagged Coordinator only (Nemotron is named only live)."""
    assert 'a[0] === "ag_writer" && sampleMode ? "ag_coordinator" : a[0]' in PAGE


def test_agent_colours_are_the_live_logs():
    for token in ("--c-coordinator", "--c-data", "--c-forecast", "--c-critic"):
        live = re.search(token + r": (#[0-9a-f]{6})", LIVE)[1]
        page = re.search(token + r": (#[0-9a-f]{6})", PAGE)[1]
        assert page == live, token


def test_icons_per_agent():
    body = PAGE.split("const AGENT_OF = {", 1)[1].split("};", 1)[0]
    icons = dict(re.findall(r'(\w+): \["\w+", "(\w+)"', body))
    assert icons == {"plan": "compass", "gather": "gauge", "forecast": "cloud", "draft": "compass",
                     "revise": "compass", "critique": "magnifier"}
