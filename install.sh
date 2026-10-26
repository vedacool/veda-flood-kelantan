#!/usr/bin/env sh
# VEDA one-click installer for macOS / Linux (B-106). Safe to run twice.
#   ./install.sh               install, check, start the server on http://127.0.0.1:8000
#   ./install.sh --no-start    install + check only
# No sudo, no deletes, packages only from PyPI, never writes a key, never touches Docker or Nightshift.
set -eu
cd "$(dirname "$0")"

NO_START=0
PORT=8000
for arg in "$@"; do
  case "$arg" in
    --no-start) NO_START=1 ;;
    --port=*) PORT="${arg#--port=}" ;;
    *) echo "unknown option: $arg (use --no-start)"; exit 2 ;;
  esac
done

# 1. Python 3.10 or newer
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "X  Python 3.10 or newer not found. Install it (python.org, or your package manager; [JPS reading] recommended),"
  echo "   then run ./install.sh again."
  exit 1
fi
echo "Python: $("$PY" --version)"

# 2. .venv (created once) + the pinned packages from PyPI
if [ ! -x .venv/bin/python ]; then
  echo "Creating .venv ..."
  "$PY" -m venv .venv || { echo "X  Could not create .venv (on Debian/Ubuntu: install the python3-venv package)"; exit 1; }
fi
echo "Installing packages from requirements-lock.txt (PyPI) ..."
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements-lock.txt || {
  echo "X  pip install failed - check your internet connection, then run ./install.sh again"; exit 1; }

# 3. .env from .env.example, only if there is no .env yet (never overwritten, no key written)
.venv/bin/python -m veda init-env

# 4. The doctor: what is ready, what to fix, which mode VEDA will start in
.venv/bin/python -m veda doctor

# 5. The server on 127.0.0.1 (not reachable from other computers) + the link
if [ "$NO_START" = 1 ]; then
  echo "Installed and checked (--no-start). Start later with: ./install.sh"
  exit 0
fi
exec .venv/bin/python -m veda start --port "$PORT"
