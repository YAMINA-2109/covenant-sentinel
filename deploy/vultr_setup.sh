#!/usr/bin/env bash
# CovenantSentinel — one-shot deploy on a fresh Vultr Ubuntu 24.04 VM (run as root).
# The built frontend is committed in frontend/dist, so the server needs Python only.
set -euo pipefail

REPO_URL="https://github.com/YAMINA-2109/covenant-sentinel.git"
APP_DIR="/opt/covenant-sentinel"

apt-get update -y
apt-get install -y python3-venv python3-pip git ufw curl fonts-dejavu-core

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull
else
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR/backend"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo ">>> ACTION REQUIRED: edit $APP_DIR/backend/.env and set VULTR_API_KEY,"
  echo ">>> then re-run this script."
  exit 1
fi

cat >/etc/systemd/system/covenantsentinel.service <<'UNIT'
[Unit]
Description=CovenantSentinel agentic covenant auditor
After=network.target

[Service]
WorkingDirectory=/opt/covenant-sentinel/backend
ExecStart=/opt/covenant-sentinel/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 80
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now covenantsentinel
systemctl restart covenantsentinel

ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw --force enable >/dev/null

sleep 2
systemctl --no-pager status covenantsentinel | head -5
echo ""
echo "✅ Deployed: http://$(curl -s ifconfig.me)/  (health: /healthz)"
