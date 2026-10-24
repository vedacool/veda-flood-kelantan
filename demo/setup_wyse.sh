#!/usr/bin/env bash
# VEDA public OFFLINE demo on the Wyse - one command (docs/DEPLOY_DEMO.md). Run from the unpacked bundle:
#   bash demo/setup_wyse.sh            # check the machine, build, start, test, then offer to publish on Funnel
#   bash demo/setup_wyse.sh --export   # all feedback answers -> feedback-<date>.csv in the current folder
#   bash demo/setup_wyse.sh --stop     # Funnel off for the demo + containers down (the answers volume is kept)
# Never installs anything and never runs a Tailscale reset command.
set -euo pipefail

CALLER="$PWD"                                # --export writes here, where the command was typed
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"
COMPOSE=(docker compose -f demo/compose.yaml --profile demo)
STATE="$HERE/demo/.state"                    # the chosen local port and Funnel port, for --stop / --export
REPLAY_LINK='?replay=nov2024&at=2024-11-27%2019:30'

say()  { printf '%s\n' "$*"; }
fail() { printf 'STOP: %s\n' "$*" >&2; exit 1; }
saved() { [ -f "$STATE" ] && grep -E "^$1=" "$STATE" | cut -d= -f2 || true; }

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

docker_steps() {
  cat <<'EOF'
Docker is needed. Install it yourself (DEPLOY_DEMO.md step 2), then run this script again:
  curl -fsSL https://get.docker.com -o get-docker.sh     # Docker's official install script
  less get-docker.sh                                     # read it first
  sudo sh get-docker.sh
  sudo usermod -aG docker "$USER"                        # then log out and back in
  docker run --rm hello-world
EOF
}

# ---------------------------------------------------------------- --export / --stop
if [ "${1:-}" = "--export" ]; then
  out="$CALLER/feedback-$(date +%F).csv"
  if ! "${COMPOSE[@]}" exec -T feedback python feedback.py export > "$out"; then
    rm -f "$out"                             # never leave a half-written CSV behind
    fail "export failed (is the demo running? bash demo/setup_wyse.sh) - nothing saved"
  fi
  say "Saved $(($(wc -l < "$out") - 1)) answers to $out"
  exit 0
fi

if [ "${1:-}" = "--stop" ]; then
  fport="$(saved FUNNEL_PORT)"
  if [ -n "$fport" ] && command -v tailscale >/dev/null 2>&1; then
    say "Funnel off for https port $fport (the demo only):"
    sudo tailscale funnel --https="$fport" off || say "  (could not turn it off - check: tailscale funnel status)"
    tailscale funnel status || true
  else
    say "No Funnel port saved by this script."
  fi
  # Funnel may also have been turned on by hand on 443 (DEPLOY_DEMO.md step 5). Ask: something else of yours
  # may be served on 443, and turning it off could stop that too.
  if [ "$fport" != 443 ] && command -v tailscale >/dev/null 2>&1; then
    say "What Tailscale serves now:"
    tailscale funnel status 2>&1 | sed 's/^/    /' || true
    if [ -t 0 ]; then
      read -r -p "  Also run 'tailscale funnel --https=443 off'? Only if the demo is what is on 443. [y/N] " ans
      if [ "$ans" = y ] || [ "$ans" = Y ]; then
        sudo tailscale funnel --https=443 off || say "  (could not turn it off - check: tailscale funnel status)"
      fi
    else
      say "  If the demo is on 443, also run: sudo tailscale funnel --https=443 off"
    fi
  fi
  DEMO_PORT="$(saved DEMO_PORT)" "${COMPOSE[@]}" down
  say "Stopped. The feedback answers are kept (volume veda-demo_feedback); export them with --export."
  say "To delete them for good, after exporting: docker compose -f demo/compose.yaml --profile demo down -v"
  exit 0
fi

[ -z "${1:-}" ] || fail "unknown option $1 (use no option, --export or --stop)"

# ---------------------------------------------------------------- 1. checks
say "== 1. Checking this machine"
arch="$(uname -m)"
[ "$arch" = "x86_64" ] || fail "this is $arch; the demo is built for x86_64"
say "  machine: $arch - ok"

mem_kb="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
[ "$mem_kb" -ge 1572864 ] || fail "only $((mem_kb / 1024)) MB of memory available; the demo needs 1.5 GB"
say "  memory available: $((mem_kb / 1024)) MB - ok"

disk_kb="$(df -Pk "$HERE" | awk 'NR == 2 {print $4}')"
[ "$disk_kb" -ge 3145728 ] || fail "only $((disk_kb / 1024)) MB free disk here; the demo needs 3 GB"
say "  disk free: $((disk_kb / 1024)) MB - ok"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  docker_steps; exit 1
fi
for tool in curl awk; do command -v "$tool" >/dev/null 2>&1 || fail "'$tool' is missing (sudo apt install $tool)"; done
if ! docker info >/dev/null 2>&1; then
  say "Docker is installed but this user cannot use it (or it is not running)."
  say "  sudo systemctl start docker; sudo usermod -aG docker \"\$USER\"  - then log out, log in and run this again."
  exit 1
fi
say "  docker: $(docker --version | cut -d, -f1), compose $(docker compose version --short) - ok"

port="${DEMO_PORT:-8765}"
start="$port"
if [ -z "${DEMO_PORT:-}" ] && [ "$(saved DEMO_PORT)" != "" ]; then port="$(saved DEMO_PORT)"; start="$port"; fi
running="$("${COMPOSE[@]}" ps -q proxy 2>/dev/null || true)"
while [ -z "$running" ] && port_busy "$port"; do
  port=$((port + 1))
  [ "$port" -le $((start + 30)) ] || fail "no free port between $start and $((start + 30))"
done
[ "$port" = "$start" ] && say "  port $port: free - ok" || say "  port $start is in use - using port $port instead"
export DEMO_PORT="$port"
printf 'DEMO_PORT=%s\nFUNNEL_PORT=%s\n' "$port" "$(saved FUNNEL_PORT)" > "$STATE"

# ---------------------------------------------------------------- 2. build + start
say "== 2. Building and starting (the first time takes 5-10 min)"
"${COMPOSE[@]}" up -d --build < /dev/null          # never let the build read the keyboard (the Funnel question)
B="http://127.0.0.1:$port"
say "  waiting for VEDA to answer ..."
for i in $(seq 1 90); do
  if curl -fsS "$B/health" >/dev/null 2>&1; then break; fi
  [ "$i" -lt 90 ] || fail "VEDA did not answer in 3 minutes - see: docker compose -f demo/compose.yaml --profile demo logs"
  sleep 2
done
say "  VEDA is up on $B"

# ---------------------------------------------------------------- 3. checks
say "== 3. Checking the demo"
fails=0
check() {   # name, command...
  local name="$1"; shift
  if "$@" >/dev/null 2>&1 < /dev/null; then say "  PASS  $name"; else say "  FAIL  $name"; fails=$((fails + 1)); fi
}
check "offline: /health says sample_mode true" sh -c "curl -fsS '$B/health' | grep -q '\"sample_mode\":true'"
check "/admin closed (404 from the proxy)"     sh -c "[ \"\$(curl -s -o /dev/null -w '%{http_code}' '$B/admin')\" = 404 ]"
check "/admin closed in the app too (404)" \
  sh -c "${COMPOSE[*]} exec -T proxy wget -S -O /dev/null http://veda:8000/admin 2>&1 | grep -q ' 404 '"
check "demo banner on the page"                sh -c "curl -fsS '$B/' | grep -q 'id=\"veda-demo-banner\"'"
check "banner script (EN/BM, feedback link)"   sh -c "curl -fsS '$B/demo-banner.js' | grep -q 'bukan amaran rasmi'"
check "feedback form answers"                  sh -c "curl -fsS '$B/feedback' | grep -q 'name=\"place\"'"
check "a scene answers (Rantau Panjang, 27 Nov 2024 19:30 -> ACT)" \
  sh -c "curl -fsS -X POST '$B/run' -H 'Content-Type: application/json' -d '{\"question\":\"Is Rantau Panjang safe?\",\"replay\":\"nov2024\",\"at\":\"2024-11-27 19:30\"}' | grep -q '\"verdict\":\"ACT\"'"
check "no way out to the internet from VEDA" \
  sh -c "! ${COMPOSE[*]} exec -T veda python -c \"import urllib.request; urllib.request.urlopen('https://api.open-meteo.com', timeout=5)\""
[ "$fails" -eq 0 ] || fail "$fails check(s) failed - not publishing. Logs: docker compose -f demo/compose.yaml --profile demo logs"

# ---------------------------------------------------------------- 4. Funnel (asks first)
say "== 4. Publishing with Tailscale Funnel"
fport=""
if ! command -v tailscale >/dev/null 2>&1; then
  say "  tailscale is not installed here - skipping. The demo runs on $B (this machine only)."
else
  say "  What Tailscale already serves on this machine (nothing will be removed):"
  tailscale serve status 2>&1 | sed 's/^/    /' || true
  tailscale funnel status 2>&1 | sed 's/^/    /' || true
  used443=no
  if tailscale serve status --json 2>/dev/null | grep -q '"443"'; then used443=yes; fi
  if [ ! -t 0 ]; then
    say "  Not an interactive terminal - skipping. Publish later: sudo tailscale funnel --bg --https=8443 $port"
  else
    if [ "$used443" = yes ]; then
      say "  Port 443 is already served by something else - the demo will use 8443."
      read -r -p "  Publish on Funnel port 8443? [8443/skip] " ans
    else
      read -r -p "  Publish on Funnel port 443 or 8443? [443/8443/skip] " ans
    fi
    case "$ans" in
      443)  [ "$used443" = no ] && fport=443 || fport=8443 ;;
      8443) fport=8443 ;;
      *)    say "  Skipped. The demo runs on $B (this machine only)." ;;
    esac
    if [ -n "$fport" ]; then
      sudo tailscale funnel --bg --https="$fport" "$port"
      printf 'DEMO_PORT=%s\nFUNNEL_PORT=%s\n' "$port" "$fport" > "$STATE"
      tailscale funnel status 2>&1 | sed 's/^/    /' || true
    fi
  fi
fi

# ---------------------------------------------------------------- 5. links
host="$(tailscale status --json 2>/dev/null | tr -d '\n' | sed -n 's/.*"Self": *{[^}]*"DNSName": *"\([^"]*\)\.".*/\1/p' || true)"
[ -n "$host" ] || host="wyse5070.<your-tailnet>.ts.net"
base="https://$host"; [ "$fport" = 8443 ] && base="$base:8443"
say ""
say "== Done"
if [ -n "$fport" ]; then
  say "  Public link (flood replay): $base/$REPLAY_LINK   -> tap Rantau Panjang"
  say "  Feedback:                   $base/feedback"
  say "  Test it on a phone on mobile data (not on the tailnet), then the rate-limit check in DEPLOY_DEMO.md step 6."
else
  say "  Local only:                 $B/$REPLAY_LINK"
fi
say "  Export feedback:            bash demo/setup_wyse.sh --export"
say "  Stop after judging (6 Nov): bash demo/setup_wyse.sh --export && bash demo/setup_wyse.sh --stop"
