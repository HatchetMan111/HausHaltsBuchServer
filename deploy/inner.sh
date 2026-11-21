#!/bin/bash
# Inner-Setup-Skript: läuft IM LXC (als root).
# Wird vom Host-Installer via `pct push` hochgeladen und mit `pct exec` ausgeführt.
# Erwartet Umgebungsvariablen: PORT, APP_DIR, REPO_URL, BRANCH

set -Eeuo pipefail

PORT="${PORT:-8098}"
APP_DIR="${APP_DIR:-/opt/haushaltsbuch}"
REPO_URL="${REPO_URL:-https://github.com/HatchetMan111/Haushaltsbuch-Proxmox}"
BRANCH="${BRANCH:-main}"
NODE_VERSION="${NODE_VERSION:-22.11.0}"
LOG=/var/log/haushaltsbuch.log

c_info() { printf '\033[1;34s[i]\033[0m %s\n' "$*"; }
c_ok()   { printf '\033[1;32s[OK]\033[0m %s\n' "$*"; }
c_warn() { printf '\033[1;33s[!]\033[0m %s\n' "$*"; }
c_err()  { printf '\033[1;31s[X]\033[0m %s\n' "$*" >&2; }

on_error() {
  local code=$? line=$1
  c_err "Inner-Setup fehlgeschlagen (Exit $code, Zeile $line)."
  c_err "Letzte 40 Zeilen $LOG:"
  tail -n 40 "$LOG" 2>/dev/null >&2 || true
  c_err "Letzte 25 Zeilen des Setup-Outputs (journalctl):"
  journalctl -u haushaltsbuch -n 25 --no-pager >&2 2>/dev/null || true
  exit "$code"
}
trap 'on_error $? $LINENO' ERR

# ---------------------------------------------------------------- Basispakete
c_info "Installiere Basispakete (curl, python3, venv, nginx, …) ..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  curl ca-certificates gnupg lsb-release \
  python3 python3-venv python3-pip \
  nginx sqlite3 logrotate \
  >/dev/null

c_ok "Basispakete installiert."

# ---------------------------------------------------------------- Node.js
if ! command -v node >/dev/null 2>&1 || [ "$(node -v 2>/dev/null | cut -c2- | cut -d. -f1)" -lt 20 ]; then
  c_info "Installiere Node.js $NODE_VERSION (offizielles Binary) ..."
  ARCH="$(dpkg --print-architecture)"
  TARBALL="node-v${NODE_VERSION}-linux-x64.tar.xz"
  case "$ARCH" in
    arm64|aarch64) TARBALL="node-v${NODE_VERSION}-linux-arm64.tar.xz" ;;
  esac
  curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/${TARBALL}" -o "/tmp/${TARBALL}"
  mkdir -p /opt/node
  tar -xJf "/tmp/${TARBALL}" -C /opt/node --strip-components=1
  rm -f "/tmp/${TARBALL}"
  ln -sf /opt/node/bin/node /usr/local/bin/node
  ln -sf /opt/node/bin/npm  /usr/local/bin/npm
  ln -sf /opt/node/bin/npx  /usr/local/bin/npx
  c_ok "Node.js $(node -v) installiert."
else
  c_ok "Node.js $(node -v) bereits vorhanden."
fi

# ---------------------------------------------------------------- App-Code
c_info "Lade App-Code von GitHub ($BRANCH) ..."
mkdir -p "$APP_DIR"
TMP="$(mktemp -d)"
curl -fsSL "${REPO_URL%.git}/archive/refs/heads/${BRANCH}.tar.gz" -o "$TMP/app.tar.gz"
tar -xzf "$TMP/app.tar.gz" -C "$TMP"
SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n1)"

# Bestandsupdate: altes Verzeichnis als Rollback wegschieben
if [ -d "$APP_DIR" ]; then
  c_info "Bestehende Installation gefunden – Update-Modus."
  rm -rf "$APP_DIR/app.old" 2>/dev/null || true
  mkdir -p "$APP_DIR/app.old"
  for item in backend frontend deploy; do
    [ -e "$APP_DIR/$item" ] && mv "$APP_DIR/$item" "$APP_DIR/app.old/" || true
  done
fi

cp -a "$SRC/backend" "$APP_DIR/backend"
cp -a "$SRC/frontend" "$APP_DIR/frontend"
cp -a "$SRC/deploy" "$APP_DIR/deploy"
rm -rf "$TMP"
c_ok "App-Code unter $APP_DIR."

# ---------------------------------------------------------------- Python-Backend
c_info "Erstelle Python-vEnv und installiere Abhängigkeiten ..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/backend/requirements.txt"
c_ok "Python-Abhängigkeiten installiert."

# ---------------------------------------------------------------- React-Build
c_info "Baue React-Frontend (vite) ..."
cd "$APP_DIR/frontend"
if [ ! -d node_modules ]; then
  npm install --no-audit --no-fund --loglevel=error
fi
npm run build
rm -rf "$APP_DIR/static"
mkdir -p "$APP_DIR/static"
cp -a "$APP_DIR/frontend/dist/." "$APP_DIR/static/"
c_ok "Frontend gebaut und nach $APP_DIR/static kopiert."

# ---------------------------------------------------------------- nginx-Konfig
c_info "Schreibe nginx-Konfiguration (Port $PORT) ..."
cat > /etc/nginx/sites-available/haushaltsbuch <<NGINXEOF
server {
    listen ${PORT} default_server;
    listen [::]:${PORT} default_server;
    server_name _;

    client_max_body_size 25m;

    access_log /var/log/nginx/haushaltsbuch_access.log;
    error_log  /var/log/nginx/haushaltsbuch_error.log;

    location /api/ {
        proxy_pass http://127.0.0.1:8099;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
    }

    location /assets/ {
        alias ${APP_DIR}/static/assets/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        root ${APP_DIR}/static;
        try_files \$uri \$uri/ /index.html;
    }
}
NGINXEOF
ln -sf /etc/nginx/sites-available/haushaltsbuch /etc/nginx/sites-enabled/haushaltsbuch
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx >/dev/null 2>&1 || true
systemctl restart nginx

# ---------------------------------------------------------------- systemd
c_info "Schreibe systemd-Unit ..."
cat > /etc/systemd/system/haushaltsbuch.service <<UNITEOF
[Unit]
Description=Haushaltsbuch (FastAPI + React, lokal)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}/backend
Environment=HAUSHALTSBUCH_APP_DIR=${APP_DIR}
Environment=HAUSHALTSBUCH_DATA_DIR=${APP_DIR}/data
Environment=HAUSHALTSBUCH_DB=${APP_DIR}/data/haushaltsbuch.db
Environment=HAUSHALTSBUCH_PORT=8099
ExecStart=${APP_DIR}/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8099
Restart=always
RestartSec=3
StandardOutput=append:${LOG}
StandardError=append:${LOG}

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable haushaltsbuch >/dev/null 2>&1 || true
systemctl restart haushaltsbuch

# ---------------------------------------------------------------- Logrotate
cat > /etc/logrotate.d/haushaltsbuch <<'LOGEOF'
/var/log/haushaltsbuch.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
LOGEOF

# ---------------------------------------------------------------- Datenverzeichnis
mkdir -p "$APP_DIR/data/uploads"
touch "$LOG"

c_info "Warte auf API ..."
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:8099/api/health" >/dev/null 2>&1; then
    c_ok "API antwortet."
    break
  fi
  sleep 1
  [ "$i" -eq 30 ] && { c_err "API antwortet nicht nach 30s."; journalctl -u haushaltsbuch -n 40 --no-pager >&2; exit 1; }
done

c_ok "Inner-Setup abgeschlossen."