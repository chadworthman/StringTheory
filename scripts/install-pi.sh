#!/usr/bin/env bash
# Install String Theory on a Raspberry Pi (or any Debian/Ubuntu-style Linux with systemd).
#
#   git clone https://github.com/chadworthman/StringTheory.git string-theory && cd string-theory && ./scripts/install-pi.sh
#
# Sets up Python, helps you get your keys and pick your strings, then runs String Theory as two services
# that start at boot: the light engine and the control page on port 8080. Safe to run again to update.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DATA="${STRINGTHEORY_DATA:-$REPO/data}"
VENV="$REPO/.venv"
PY="$VENV/bin/python"
ME="$(id -un)"
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ask() { local a; read -r -p "$1 [y/N] " a || true; [[ "$a" =~ ^[Yy] ]]; }

say "1. Python"
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  echo "String Theory needs Python 3.11 or newer (Raspberry Pi OS Bookworm or later has it)."; exit 1
fi
python3 -c 'import venv, ensurepip' 2>/dev/null || { sudo apt-get update -q && sudo apt-get install -y -q python3-venv; }
[ -x "$PY" ] || python3 -m venv "$VENV"
"$PY" -m pip install -q --upgrade pip tinytuya HAP-python   # HAP-python: the Apple Home bridge
echo "Python environment ready in $VENV"

say "2. Your keys"
mkdir -p "$DATA"; chmod 700 "$DATA"
if [ ! -f "$DATA/devices.json" ]; then
  echo "String Theory needs devices.json, made by the tinytuya wizard from your free Tuya developer account."
  echo "See 'Get each controller's local key' in the README for the account steps."
  if ask "Run the wizard now (you'll need your Tuya project's Access ID and Secret)?"; then
    (cd "$DATA" && "$PY" -m tinytuya wizard)
  else
    echo "Then copy your devices.json to $DATA/ and run this script again."; exit 0
  fi
fi
chmod 600 "$DATA"/devices.json "$DATA"/tinytuya.json 2>/dev/null || true

say "3. Your strings"
if [ ! -f "$DATA/config.json" ] || ask "Change which strings String Theory uses?"; then
  STRINGTHEORY_DATA="$DATA" "$PY" "$REPO/pi/configure.py"
fi

say "4. Services"
unit() {   # name, description, command
  sudo tee "/etc/systemd/system/$1.service" >/dev/null <<EOF
[Unit]
Description=$2
After=network-online.target
Wants=network-online.target

[Service]
User=$ME
WorkingDirectory=$REPO/pi
Environment=STRINGTHEORY_DATA=$DATA
ExecStart=$3
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
}
unit string-theory "String Theory light engine" "$PY $REPO/pi/lights.py run"
unit string-theory-web "String Theory control page (port 8080)" "$PY $REPO/pi/web.py"
unit string-theory-homekit "String Theory in Apple Home (port 51826)" "$PY $REPO/pi/homekit.py"
sudo rm -f /usr/local/bin/lights   # replace, never write through an old symlink
sudo tee /usr/local/bin/lights >/dev/null <<EOF
#!/bin/sh
STRINGTHEORY_DATA="$DATA" exec "$PY" "$REPO/pi/lights.py" "\$@"
EOF
sudo chmod +x /usr/local/bin/lights
sudo systemctl daemon-reload
sudo systemctl enable -q string-theory string-theory-web string-theory-homekit
sudo systemctl restart string-theory string-theory-web string-theory-homekit
echo "Running. Check with: systemctl status string-theory   Logs: journalctl -u string-theory -f"

say "5. Keep it on your home network"
if command -v ufw >/dev/null && sudo ufw status | grep -q "Status: active"; then
  NET="$(ip -o -f inet addr show | awk '/scope global/ {print $4; exit}')"
  if [ -n "$NET" ] && ask "Your firewall is on. Allow the control page from your home network ($NET) only?"; then
    sudo ufw allow from "$NET" to any port 8080 proto tcp comment 'String Theory control page'
  fi
  if [ -n "$NET" ] && ask "Allow Apple Home to reach String Theory from your home network ($NET)?"; then
    sudo ufw allow from "$NET" to any port 51826 proto tcp comment 'String Theory Apple Home bridge'
    sudo ufw allow from "$NET" to any port 5353 proto udp comment 'mDNS, so Home can find it'
  fi
fi
echo "From your home network the page needs no login. Don't forward port 8080 on your router; for a tunnel, set a password first (see the README)."

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
say "Done. Open http://${IP:-<this-pi>}:8080 on your phone (on your home Wi-Fi) and add it to your home screen."
