"""The public demo's safety settings stay in place (demo/compose.yaml, demo/nginx.conf). Text checks: no Docker needed."""
import importlib.util
import re
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / "demo"
NGINX = (DEMO / "nginx.conf").read_text(encoding="utf-8")
COMPOSE = (DEMO / "compose.yaml").read_text(encoding="utf-8")


def test_operator_screens_and_run_logs_are_closed():
    assert re.search(r"location \^~ /admin\s+\{ return 404; \}", NGINX)
    assert re.search(r"location \^~ /trace/run/ \{[^}]*return 404 ", NGINX)


def test_rate_limit_and_headers():
    assert "zone=answers:10m rate=20r/m" in NGINX and "limit_req_status 429" in NGINX
    for loc in ("location = /run {", "location = /run/stream {", "location ^~ /feedback {"):     # asking costs most
        assert "limit_req zone=answers" in NGINX.split(loc, 1)[1].split("}", 1)[0]
    for h in ("Content-Security-Policy", "frame-ancestors 'none'", "X-Content-Type-Options \"nosniff\""):
        assert h in NGINX
    assert 'add_header Strict-Transport-Security "max-age=31536000" always;' in NGINX


def test_the_public_api_has_the_run_stream_limits_and_fastapi_docs_are_closed():
    """Cowork 24 Oct night: /api/v1/ and /api/docs get the same per-visitor limits as /run/stream; FastAPI's own
    /docs, /redoc and /openapi.json answer 404 at the proxy (the app closes them too in demo mode)."""
    def block(loc):
        return NGINX.split(loc, 1)[1].split("\n        }", 1)[0]
    for loc in ("location ^~ /api/v1/ {", "location = /api/docs {"):
        b = block(loc)
        for rule in ("limit_conn streams_per_visitor 3;", "limit_conn streams_all 10;",
                     "limit_req zone=pages burst=60 nodelay;", "limit_req zone=answers burst=10 nodelay;",
                     "proxy_pass http://veda;"):
            assert rule in b, (loc, rule)
    docs = block("location = /api/docs {")
    assert "Content-Security-Policy" not in docs.split("#", 1)[0].split("add_header", 1)[-1]  # the app's DOCS_CSP passes
    assert 'add_header X-Frame-Options "DENY" always;' in docs and "Strict-Transport-Security" in docs
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert re.search(rf"location = {re.escape(path)}\s+\{{ return 404; \}}", NGINX), path


def test_open_streams_are_capped_per_visitor_and_in_all():
    """Audit 24 Oct: ~40 open /live/stream connections froze the app. 3 per visitor, 10 in all."""
    assert "events { worker_connections 1024; }" in NGINX
    assert "limit_conn_zone $visitor zone=streams_per_visitor" in NGINX and "limit_conn_status 429;" in NGINX
    assert 'map $host $everyone { default "all"; }' in NGINX and "limit_conn_zone $everyone zone=streams_all" in NGINX
    for loc in ("location = /run/stream {", "location = /live/stream {"):
        block = NGINX.split(loc, 1)[1].split("}", 1)[0]
        assert "limit_conn streams_per_visitor 3;" in block and "limit_conn streams_all 10;" in block


def test_the_demo_strip_comes_from_the_app_not_the_proxy():
    """B-96: the shared frame (app/frame.py) carries the demo strip, top bar and footer, and the answer has its own
    feedback line; the proxy adds nothing to VEDA's pages (it would show twice)."""
    assert "sub_filter" not in NGINX and "demo-banner" not in NGINX and "veda-demo-banner" not in NGINX
    assert not (DEMO / "demo-banner.js").exists()
    assert "demo-banner" not in (DEMO / "proxy.Dockerfile").read_text(encoding="utf-8")
    sh = (DEMO / "setup_wyse.sh").read_text(encoding="utf-8")
    assert "vf-strip" in sh and "demo-banner" not in sh


def test_the_feedback_page_wears_the_shared_frame():
    """B-96: the feedback service builds from the repo root and copies app/frame.py + app/config.py (standard
    library only); its pages carry the top bar, the demo strip and the footer - and no second link to VEDA's home."""
    docker = (DEMO / "feedback" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY app/__init__.py app/config.py app/frame.py app/" in docker
    assert "build: { context: .., dockerfile: demo/feedback/Dockerfile }" in COMPOSE
    spec = importlib.util.spec_from_file_location("feedback_frame", DEMO / "feedback" / "feedback.py")
    fb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fb)
    for html in (fb.form_page("en"), fb.thanks_page("ms")):
        assert html.count('class="vf-top"') == 1 and 'class="vf-strip"' in html and html.count('class="vf-foot"') == 1
        assert html.count('href="/"') == 1                                      # VEDA in the top bar only


def test_docker_logs_rotate_and_the_proxy_has_a_process_cap():
    assert 'options: { max-size: "10m", max-file: "3" }' in COMPOSE
    assert COMPOSE.count("logging: *logging") == 3
    proxy = COMPOSE.split("\n  proxy:\n", 1)[1].split("\nnetworks:", 1)[0]
    assert "pids_limit: 32" in proxy


def test_no_visitor_address_is_logged_or_passed_on():
    assert "access_log off;" in NGINX and "error_log /dev/stderr crit;" in NGINX
    assert 'proxy_set_header X-Forwarded-For "";' in NGINX


def test_veda_runs_offline_on_an_internal_network_with_limits():
    veda = COMPOSE.split("\n  veda:\n", 1)[1].split("\n  feedback:\n", 1)[0]
    assert 'SAMPLE_MODE: "true"' in veda and "env_file" not in COMPOSE
    assert "networks: [inside]" in veda and "mem_limit: 1g" in veda and "read_only: true" in veda
    assert "restart: unless-stopped" in veda and "ports" not in veda
    assert "inside: { internal: true }" in COMPOSE
    assert re.search(r'ports: \["127\.0\.0\.1:\$\{DEMO_PORT:-\d+\}:8080"\]', COMPOSE)   # this machine only


def test_share_links_get_the_public_address_from_the_machine_never_from_the_repo():
    """VEDA_PUBLIC_URL comes from setup_wyse.sh at run time (this machine's Tailscale name); compose only passes it on.
    No real tailnet name is committed anywhere: only placeholders (<your-tailnet>, <tailnet>) and example names."""
    import subprocess
    veda = COMPOSE.split("\n  veda:\n", 1)[1].split("\n  feedback:\n", 1)[0]
    assert 'VEDA_PUBLIC_URL: "${VEDA_PUBLIC_URL:-}"' in veda
    sh = (DEMO / "setup_wyse.sh").read_text(encoding="utf-8")
    assert 'export VEDA_PUBLIC_URL="${PRESET_URL:-$(public_url "$(saved FUNNEL_PORT)")}"' in sh
    assert 'url="${PRESET_URL:-$(public_url "$fport")}"' in sh
    names = subprocess.run(["git", "grep", "-h", "-o", "-I", "-E", r"[A-Za-z0-9<>_-]+(\.[A-Za-z0-9<>_-]+)*\.ts\.net"],
                           cwd=DEMO.parent, capture_output=True, text=True).stdout.split()
    assert names and all(re.search(r"<(your-)?tailnet>|\.example\.ts\.net$", n) for n in names), names
