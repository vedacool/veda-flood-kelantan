"""Cowork full audit 27 Oct (docs/audit/2026-10-27-full-audit.md): the small fixes, one test each. Offline."""
import json
import os
import time

import pytest

from app import config, main, router, trace

PAGE = (config.ROOT / "app" / "web" / "index.html").read_text(encoding="utf-8")


def test_a_p2_25_the_screen_reader_answer_follows_the_language_switch():
    body = PAGE[PAGE.index("function applyLang() {"):]
    body = body[:body.index("\n}\n")]
    assert 'if (result && !$("s-answer").hidden) announce();' in body


def test_a_p2_26_the_live_docker_recipes_publish_on_this_computer_only():
    for name in ("README.md", "Dockerfile"):
        text = (config.ROOT / name).read_text(encoding="utf-8")
        assert "-p 8000:8000 --env-file" not in text and "-p 127.0.0.1:8000:8000 --env-file .env" in text, name


def test_a_p3_23_lang_from_the_address_is_an_own_key_of_the_words():
    assert 'if (!Object.hasOwn(UI, lang)) lang = "en";' in PAGE and "if (!UI[lang])" not in PAGE


def test_a_p3_24_a_cut_off_trace_line_is_no_500(tmp_path):
    path = tmp_path / "trace-x.jsonl"
    path.write_text(json.dumps({"agent_name": "Coordinator"}) + '\n{"agent_name": "Crit', encoding="utf-8")
    r = {"run_id": "x", "status": "success", "trace": str(path), "forecast": None, "card": None, "plan": {},
         "evidence": {}, "reviews": [], "answer": {"text": "t", "safety_line": "", "language": "en"}}
    try:
        main.result_json(r)
    except (KeyError, TypeError, AttributeError):
        pass                                  # the rest of this hand-made result is incomplete - not this test's point
    except ValueError as e:                   # the cut-off line itself must never raise
        pytest.fail(f"cut-off trace line raised {e!r}")


def test_a_p3_24_the_public_demo_keeps_the_newest_200_traces(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    now = time.time()
    for i in range(205):
        f = logs / f"trace-run{i:03d}.jsonl"
        f.write_text("{}\n", encoding="utf-8")
        os.utime(f, (now - 1000 + i, now - 1000 + i))                 # run204 is the newest
    (logs / "other.log").write_text("x", encoding="utf-8")
    monkeypatch.setattr(trace, "ROOT", tmp_path)
    main.prune_traces()
    left = sorted(p.name for p in logs.glob("trace-*.jsonl"))
    assert len(left) == 200 and left[0] == "trace-run005.jsonl" and (logs / "other.log").exists()


@pytest.mark.parametrize("question", ["We are stuck at Tumpat", "My family is on the roof in Pasir Mas",
                                      "Someone is drowning near Kota Bharu", "Kami tersekat di Tumpat",
                                      "Rumah kami terkepung air", "Kami di atas bumbung", "Anak saya lemas"])
def test_a_p3_25_more_emergency_words(question):
    assert router.emergency(question)


def test_a_p3_25_ordinary_questions_are_not_emergencies():
    for q in ("Is Tumpat at risk?", "Rantau Panjang selamat ke?", "Will the roof leak?"):
        assert router.emergency(q) is None, q


def test_a_p3_35_scenes_catch_all_is_not_in_the_schema_and_the_cli_prints_labels():
    assert all(getattr(r, "path", "") != "/scenes{tail:path}" or not r.include_in_schema for r in main.app.routes)
    src = (config.ROOT / "veda" / "__main__.py").read_text(encoding="utf-8")
    assert "({a['level']})" not in src and "name(j.get('final'))" in src


def test_a_p3_26_a_reading_from_the_future_is_unknown_with_5_min_tolerance():
    from app.agents import data_agent
    assert data_agent.freshness("jps_levels", -3) == "fresh"               # clocks a little apart
    assert data_agent.freshness("jps_levels", -5) == "fresh"
    assert data_agent.freshness("jps_levels", -6) == "unknown"             # dated in the future: never fresh
    assert data_agent.freshness("jps_levels", -600) == "unknown"


def test_a_p3_28_one_staleness_limit():
    from app.agents import data_agent
    assert main.NEWEST_STALE_MIN == data_agent.FRESHNESS["jps_levels"][1]
    src = (config.ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "NEWEST_STALE_MIN = 180" not in src


def test_a_p3_10_api_docs_load_a_pinned_swagger_with_integrity():
    from starlette.testclient import TestClient
    html = TestClient(main.app).get("/api/docs").text
    assert "swagger-ui-dist@5.17.14/" in html and "swagger-ui-dist@5/" not in html
    assert html.count('integrity="sha384-') == 2 and html.count('crossorigin="anonymous"') == 2
    assert "fastapi.tiangolo.com" not in html                       # nothing else from outside


def test_a_p2_9_importing_app_main_reads_no_env_file(tmp_path):
    """Audit 27 Oct A-P2-9: a fresh process that imports app.main gains no environment variable from .env (names only
    are compared; no value is printed)."""
    import subprocess
    import sys
    code = ("import os; before = set(os.environ); import app.main; "
            "print(sorted(k for k in set(os.environ) - before if not k.startswith(('PYTHON', 'SAMPLE'))))")
    out = subprocess.run([sys.executable, "-c", code], cwd=config.ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip().splitlines()[-1] == "[]"
