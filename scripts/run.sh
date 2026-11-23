#!/usr/bin/env bash
# Run String Theory on a Mac or Linux home computer (desktop or laptop), no Raspberry Pi needed.
#
#   ./scripts/run.sh
#
# Starts the light engine and the control page together; Ctrl-C stops both. The lights only follow the
# show and the schedule while this is running, so keep the computer awake and on your home Wi-Fi.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
export STRINGTHEORY_DATA="${STRINGTHEORY_DATA:-$REPO/data}"
VENV="$REPO/.venv"
PY="$VENV/bin/python"
PORT="${PORT:-8080}"; export PORT

python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null || { echo "Needs Python 3.11 or newer (python.org)."; exit 1; }
[ -x "$PY" ] || python3 -m venv "$VENV"
"$PY" -c 'import tinytuya' 2>/dev/null || "$PY" -m pip install -q tinytuya

mkdir -p "$STRINGTHEORY_DATA"; chmod 700 "$STRINGTHEORY_DATA"
if [ ! -f "$STRINGTHEORY_DATA/devices.json" ]; then
  echo "First, your keys: the tinytuya wizard makes devices.json (see the README for the Tuya account steps)."
  a=""; read -r -p "Run the wizard now? [y/N] " a || true
  [[ "$a" =~ ^[Yy] ]] || { echo "Put devices.json in $STRINGTHEORY_DATA and run this again."; exit 0; }
  (cd "$STRINGTHEORY_DATA" && "$PY" -m tinytuya wizard)
fi
[ -f "$STRINGTHEORY_DATA/config.json" ] || "$PY" "$REPO/pi/configure.py"

# Stop both when either stops, or on Ctrl-C.
trap 'kill 0' EXIT INT TERM
"$PY" "$REPO/pi/lights.py" run & ENGINE=$!
"$PY" "$REPO/pi/web.py" & WEB=$!
IP="$( (ipconfig getifaddr en0 || ipconfig getifaddr en1 || hostname -I | awk '{print $1}') 2>/dev/null | head -1)"
echo
echo "String Theory is running. On your phone (same Wi-Fi), open http://${IP:-<this-computer>}:$PORT"
echo "If it doesn't load, allow incoming connections for Python in your firewall. Ctrl-C to stop."
# (macOS ships an old bash without `wait -n`, so poll instead)
while kill -0 "$ENGINE" 2>/dev/null && kill -0 "$WEB" 2>/dev/null; do sleep 2; done
