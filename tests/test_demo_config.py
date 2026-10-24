"""The public demo's safety settings stay in place (demo/compose.yaml, demo/nginx.conf). Text checks: no Docker needed."""
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


def test_open_streams_are_capped_per_visitor_and_in_all():
    """Audit 24 Oct: ~40 open /live/stream connections froze the app. 3 per visitor, 10 in all."""
    assert "events { worker_connections 1024; }" in NGINX
    assert "limit_conn_zone $visitor zone=streams_per_visitor" in NGINX and "limit_conn_status 429;" in NGINX
    assert 'map $host $everyone { default "all"; }' in NGINX and "limit_conn_zone $everyone zone=streams_all" in NGINX
    for loc in ("location = /run/stream {", "location = /live/stream {"):
        block = NGINX.split(loc, 1)[1].split("}", 1)[0]
        assert "limit_conn streams_per_visitor 3;" in block and "limit_conn streams_all 10;" in block


def test_banner_is_one_line_in_the_page_language_with_a_feedback_link():
    """Cowork 24 Oct: one small line (not bold), EN|BM following the page; Feedback / Maklum balas at the right;
    "Was this clear?" under each answer. Added by the proxy (demo/demo-banner.js) - the app is not changed."""
    banner = NGINX.split("sub_filter '<body>' '", 1)[1].split("';", 1)[0]
    assert "Demo · past flood replay · not an official warning" in banner and "font:400 16px" in banner
    assert 'id="veda-demo-banner"' in banner and 'href="/feedback"' in banner and "<br>" not in banner
    assert "sub_filter '</body>' '<script src=\"/demo-banner.js\"></script></body>';" in NGINX
    js = (DEMO / "demo-banner.js").read_text(encoding="utf-8")
    for words in ('"Demo · past flood replay · not an official warning"', 'feedback: "Feedback"',
                  '"Was this clear? 1-minute feedback ›"', '"Demo · banjir lalu · bukan amaran rasmi"',
                  'feedback: "Maklum balas"', '"Jelas tak? Maklum balas 1 minit ›"'):
        assert words in js
    assert "COPY demo-banner.js /etc/nginx/demo/demo-banner.js" in (DEMO / "proxy.Dockerfile").read_text(encoding="utf-8")


def test_banner_links_to_the_judges_page_and_is_on_it_too():
    """B-90: "For judges ›" / "Untuk juri ›" in the banner; /judges gets the banner like the home page and /live."""
    banner = NGINX.split("sub_filter '<body>' '", 1)[1].split("';", 1)[0]
    assert '<a id="veda-demo-judges" href="/judges"' in banner and ">For judges ›</a>" in banner
    assert banner.index("veda-demo-judges") < banner.index("veda-demo-feedback")
    assert "location ~ ^/(live|judges)?$ {" in NGINX
    js = (DEMO / "demo-banner.js").read_text(encoding="utf-8")
    assert 'judges: "For judges ›"' in js and 'judges: "Untuk juri ›"' in js
    assert 'judges.href = "/judges?lang=" + l;' in js


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
