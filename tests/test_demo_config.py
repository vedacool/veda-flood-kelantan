"""The public demo's safety settings stay in place (demo/compose.yaml, demo/nginx.conf). Text checks: no Docker needed."""
import re
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / "demo"
NGINX = (DEMO / "nginx.conf").read_text(encoding="utf-8")
COMPOSE = (DEMO / "compose.yaml").read_text(encoding="utf-8")


def test_operator_screens_and_run_logs_are_closed():
    assert re.search(r"location \^~ /admin\s+\{ return 404; \}", NGINX)
    assert re.search(r"location \^~ /trace/run/ \{[^}]*return 404 ", NGINX)


def test_rate_limit_headers_and_banner():
    assert "zone=answers:10m rate=20r/m" in NGINX and "limit_req_status 429" in NGINX
    for loc in ("location = /run {", "location = /run/stream {", "location ^~ /feedback {"):     # asking costs most
        assert "limit_req zone=answers" in NGINX.split(loc, 1)[1].split("}", 1)[0]
    for h in ("Content-Security-Policy", "frame-ancestors 'none'", "X-Content-Type-Options \"nosniff\""):
        assert h in NGINX
    assert ("Public demo: past flood replay and made-up test scenes only. Not live data. Not an official warning."
            in NGINX)
    assert 'href="/feedback"' in NGINX


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
