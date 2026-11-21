#!/bin/bash
# =============================================================================
#  Haushaltsbuch – Proxmox-Installer (Community-Scripts-Stil)
#
#  Erstellt einen unprivilegierten LXC (Debian 13) mit Haushaltsbuch:
#  lokales Haushaltsbuch mit CSV-Import, Kategorien und Auswertung.
#  Frontend: React/Vite · Backend: Python/FastAPI · Web-UI: Port 8098
#
#  Einzeiler:
#    bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/HausHaltsBuchServer/main/install/haushaltsbuch.sh)"
#
#  Optionen:
#    --id <CTID>       Container-ID (Standard: nächste freie ID)
#    --hostname <NAME> Container-Hostname (Standard: haushaltsbuch)
#    --cores <N>       vCPU-Kerne (Standard: 2)
#    --memory <MB>     RAM in MB (Standard: 2048)
#    --disk <GB>       Disk in GB (Standard: 8)
#    --update          Bestehende Installation aktualisieren (Code + Build)
#    --uninstall       Container löschen
#    --status          Status + URL anzeigen
#    --help            Hilfe anzeigen
# =============================================================================

set -Eeuo pipefail

# ----------------------------------------------------------------- Variablen
APP_ID="haushaltsbuch"
CT_HOSTNAME="haushaltsbuch"
REPO_RAW="https://raw.githubusercontent.com/HatchetMan111/HausHaltsBuchServer"
REPO_URL="https://github.com/HatchetMan111/HausHaltsBuchServer"
BRANCH="main"
WEB_PORT=8098
ONE_LINER='bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/HausHaltsBuchServer/main/install/haushaltsbuch.sh)"'

DEFAULT_CORES=2
DEFAULT_MEMORY=2048
DEFAULT_DISK=8

CORES="$DEFAULT_CORES"
MEMORY="$DEFAULT_MEMORY"
DISK="$DEFAULT_DISK"
FORCE_ID=""
MODE="install"

# ----------------------------------------------------------------- Farben
if [ -t 1 ]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'
else
  C_RESET=""; C_BOLD=""; C_DIM=""; C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""
fi

info()  { printf '%s[i]%s %s\n'   "$C_BLUE"   "$C_RESET" "$*"; }
ok()    { printf '%s[OK]%s %s\n'  "$C_GREEN"  "$C_RESET" "$*"; }
warn()  { printf '%s[!]%s %s\n'   "$C_YELLOW" "$C_RESET" "$*"; }
err()   { printf '%s[X]%s %s\n'   "$C_RED"    "$C_RESET" "$*" >&2; }
header(){ printf '\n%s%s%s\n' "$C_BOLD" "$*" "$C_RESET"; }

fetch_inner_script() {
  local ziel="$1" tmp
  tmp="$(mktemp)"
  local url_base="$REPO_RAW/$BRANCH/deploy/inner.sh"
  local sha_url=""

  for attempt in 1 2 3; do
    case "$attempt" in
      1) url="$url_base?cb=$(date +%s)-$$" ;;
      2)
        sha_url="$(curl -fsSL --max-time 20 "https://api.github.com/repos/HatchetMan111/HausHaltsBuchServer/commits/$BRANCH" 2>/dev/null \
          | grep -o '"sha": *"[0-9a-f]\{40\}"' | head -n1 | grep -o '[0-9a-f]\{40\}' || true)"
        if [ -n "$sha_url" ]; then
          url="$REPO_RAW/$sha_url/deploy/inner.sh"
        else
          url="$url_base"
        fi
        ;;
      3) url="$url_base" ;;
    esac
    if curl -fsSL --max-time 60 "$url" -o "$tmp" 2>/dev/null && [ -s "$tmp" ]; then
      mv "$tmp" "$ziel"
      chmod +x "$ziel"
      ok "Inner-Skript geladen (Versuch $attempt)."
      return 0
    fi
    warn "Download von inner.sh fehlgeschlagen (Versuch $attempt)."
  done
  rm -f "$tmp"
  err "Konnte deploy/inner.sh nicht von GitHub laden."
  err "URL: $REPO_RAW/$BRANCH/deploy/inner.sh"
  err "Bitte Internet-/DNS-Verbindung des Proxmox-Hosts prüfen."
  exit 1
}

on_error() {
  local code=$? line=$1
  err "Abbruch in Zeile $line (Exit $code)."
  err "--- Diagnose (letzte 30 Zeilen) ---"
  tail -n 30 /tmp/haushaltsbuch-install.log 2>/dev/null >&2 || true
  err "--- pct status ---"
  [ -n "${CTID:-}" ] && pct status "$CTID" >&2 2>/dev/null || true
  err "--- Vollständiges Log: /tmp/haushaltsbuch-install.log"
  err "--- Tipp: mit 'bash -x' ausführen für ein komplettes Trace: $ONE_LINER"
  exit "$code"
}
trap 'on_error $? $LINENO' ERR

usage() {
  cat <<EOF
${C_BOLD}Haushaltsbuch – Proxmox-Installer${C_RESET}

${C_BOLD}Installation:${C_RESET}
  ${ONE_LINER}

${C_BOLD}Optionen:${C_RESET}
  --id <CTID>       Container-ID (Standard: nächste freie ID)
  --hostname <NAME> Hostname (Standard: haushaltsbuch)
  --cores <N>       vCPU-Kerne (Standard: $DEFAULT_CORES)
  --memory <MB>     RAM in MB (Standard: $DEFAULT_MEMORY)
  --disk <GB>       Disk in GB (Standard: $DEFAULT_DISK)
  --update          Bestehende Installation aktualisieren
  --uninstall       Container löschen
  --status          Status + URL anzeigen
  --help            Diese Hilfe

${C_BOLD}Nach der Installation:${C_RESET}
  Web-UI erreichbar unter http://<CONTAINER-IP>:$WEB_PORT
EOF
}

# ----------------------------------------------------------------- Argumente
# Grube (bekannt): `bash -c "$(wget -qLO - URL)" --id 105` belegt $0 statt $1.
# Daher: wenn $0 mit '-' beginnt, ist es der erste Parameter.
if [[ "${0:-}" == -* ]]; then
  set -- "$0" "$@"
fi

# Ein "nur "--"" wird aus der Dokumentation aehnlich `-- --update` entfernt,
# damit beide Varianten funktionieren (mit und ohne Trenner).
if [ "${1:-}" = "--" ]; then
  shift
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --)          shift ;;
    --id)        FORCE_ID="$2"; shift 2 ;;
    --hostname)  CT_HOSTNAME="$2"; shift 2 ;;
    --cores)     CORES="$2"; shift 2 ;;
    --memory)    MEMORY="$2"; shift 2 ;;
    --disk)      DISK="$2"; shift 2 ;;
    --update)    MODE="update"; shift ;;
    --uninstall) MODE="uninstall"; shift ;;
    --status)    MODE="status"; shift ;;
    --help|-h)   usage; exit 0 ;;
    *)           warn "Unbekannte Option: $1"; usage; exit 1 ;;
  esac
done

# ----------------------------------------------------------------- Helfer
need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "Benötigter Befehl fehlt: $1"; exit 1; }
}

find_free_id() {
  local used id
  used="$(pct list 2>/dev/null | awk 'NR>1 {print $1}')"
  for id in $(seq 100 999); do
    if ! grep -qx "$id" <<<"$used"; then
      echo "$id"
      return 0
    fi
  done
  return 1
}

# Host-Architektur (WICHTIG: Template-Arch muss zum Host passen!)
host_arch() {
  local arch
  arch="$(dpkg --print-architecture 2>/dev/null || echo "")"
  case "$arch" in
    amd64|arm64) echo "$arch" ;;
    "") case "$(uname -m)" in
          x86_64) echo amd64 ;;
          aarch64|arm64) echo arm64 ;;
          *) echo amd64 ;;
        esac ;;
    *) echo "$arch" ;;
  esac
}

# Nächste freie CT-ID oder --id
CTID="$FORCE_ID"
if [ -z "$CTID" ]; then
  CTID="$(find_free_id)" || { err "Keine freie Container-ID im Bereich 100-999 gefunden."; exit 1; }
  info "Verwende nächste freie ID: $CTID"
fi

# ----------------------------------------------------------------- Status/Update/Uninstall
ensure_ct_running() {
  local id="$1"
  local status
  status="$(pct status "$id" 2>/dev/null | awk '{print $2}')"
  if [ "$status" != "running" ]; then
    info "Container $id ist '$status' – starte ihn ..."
    pct start "$id"
    local i
    for i in $(seq 1 60); do
      sleep 1
      if [ "$(pct status "$id" 2>/dev/null | awk '{print $2}')" = "running" ]; then
        ok "Container $id läuft."
        return 0
      fi
    done
    err "Container $id startet nicht (Timeout 60s)."
    return 1
  fi
  return 0
}

ct_ip() {
  # Grube (bekannt): pct exec Exit != 0 unter pipefail → || true IN die Substitution.
  local ip
  ip="$(pct exec "$1" -- hostname -I 2>/dev/null | tr ' ' '\n' | grep -v '^$' | grep -v '^127\.' | head -n1 || true)"
  echo "$ip"
}

if [ "$MODE" = "status" ]; then
  header "Haushaltsbuch – Status"
  FOUND=""
  if [ -n "$FORCE_ID" ]; then
    if pct status "$FORCE_ID" >/dev/null 2>&1; then FOUND="$FORCE_ID"; fi
  else
    while read -r id rest; do
      name="$(echo "$rest" | awk '{print $NF}')"
      if [ "$name" = "$CT_HOSTNAME" ] || [ "$name" = "$APP_ID" ]; then FOUND="$id"; break; fi
    done < <(pct list 2>/dev/null | tail -n +2)
  fi
  if [ -z "$FOUND" ]; then
    err "Kein Haushaltsbuch-Container gefunden."
    err "Vorhandene Container:"
    pct list >&2 || true
    exit 1
  fi
  ensure_ct_running "$FOUND"
  IP="$(ct_ip "$FOUND")"
  ok "Container: $FOUND ($CT_HOSTNAME)"
  ok "IP:        ${IP:-unbekannt}"
  ok "Web-UI:    http://${IP:-<IP>}:$WEB_PORT"
  pct exec "$FOUND" -- systemctl is-active haushaltsbuch nginx 2>/dev/null || true
  exit 0
fi

if [ "$MODE" = "uninstall" ]; then
  header "Haushaltsbuch – Deinstallieren"
  FOUND="$FORCE_ID"
  if [ -z "$FOUND" ]; then
    while read -r id rest; do
      name="$(echo "$rest" | awk '{print $NF}')"
      if [ "$name" = "$CT_HOSTNAME" ] || [ "$name" = "$APP_ID" ]; then FOUND="$id"; break; fi
    done < <(pct list 2>/dev/null | tail -n +2)
  fi
  if [ -z "$FOUND" ]; then
    err "Kein Haushaltsbuch-Container gefunden."
    exit 1
  fi
  warn "Lösche Container $FOUND (inkl. aller Daten) ..."
  pct stop "$FOUND" >/dev/null 2>&1 || true
  pct destroy "$FOUND" --purge 2>/dev/null || pct destroy "$FOUND" || { err "Container konnte nicht gelöscht werden."; exit 1; }
  ok "Container $FOUND wurde gelöscht."
  exit 0
fi

if [ "$MODE" = "update" ]; then
  header "Haushaltsbuch – Update"
  FOUND="$FORCE_ID"
  if [ -z "$FOUND" ]; then
    while read -r id rest; do
      name="$(echo "$rest" | awk '{print $NF}')"
      if [ "$name" = "$CT_HOSTNAME" ] || [ "$name" = "$APP_ID" ]; then FOUND="$id"; break; fi
    done < <(pct list 2>/dev/null | tail -n +2)
  fi
  if [ -z "$FOUND" ]; then
    err "Kein Haushaltsbuch-Container gefunden – bitte --id setzen oder neu installieren."
    exit 1
  fi
  ensure_ct_running "$FOUND"
  # DNS-Zustand prüfen (bekannte Grube: flaky resolv.conf im CT)
  if ! pct exec "$FOUND" -- getent hosts raw.githubusercontent.com >/dev/null 2>&1; then
    warn "DNS im Container defekt – setze Fallback-Nameserver ..."
    pct exec "$FOUND" -- bash -c 'printf "nameserver 1.1.1.1\nnameserver 8.8.8.8\n" > /etc/resolv.conf' || true
    pct exec "$FOUND" -- getent hosts raw.githubusercontent.com >/dev/null 2>&1 || warn "DNS weiterhin defekt – ggf. pct set $FOUND --nameserver 1.1.1.1 + Reboot."
  fi
  info "Aktualisiere Code + Build in Container $FOUND ..."
  # Inner-Skript frisch vom Repo ziehen und ausführen (rollenkonform, Grube 14: pipefail)
  fetch_inner_script /tmp/haushaltsbuch-inner.sh
  pct push "$FOUND" /tmp/haushaltsbuch-inner.sh /root/inner.sh
  pct exec "$FOUND" -- env PORT="$WEB_PORT" APP_DIR="/opt/haushaltsbuch" \
    REPO_URL="$REPO_URL" BRANCH="$BRANCH" \
    bash -c 'set -o pipefail; bash /root/inner.sh 2>&1 | tee -a /var/log/haushaltsbuch.log'
  IP="$(ct_ip "$FOUND")"
  header "Update abgeschlossen"
  ok "Web-UI: http://${IP:-<IP>}:$WEB_PORT"
  exit 0
fi

# ----------------------------------------------------------------- Installation
header "Haushaltsbuch – Installation"

# Root-Prüfung
if [ "$(id -u)" -ne 0 ]; then
  err "Dieses Skript muss als root ausgeführt werden (Proxmox-Host)."
  exit 1
fi

# Basis-Abhängigkeiten
for cmd in pct pveam wget curl; do
  need_cmd "$cmd"
done

# Template bereitstellen (arch-korrekt, Grube aus LastBook/Gladys)
ARCH="$(host_arch)"
# WICHTIG (Live auf ProxSmartHome): Debian-Templates tragen Versions-Suffixe,
# z. B. "debian-13-standard_13.6-1_amd64.tar.zst" (NICHT ohne Versionsnummer!).
# Darum: Template DYNAMISCH aus pveam available suchen (Pattern mit Wildcard).
TEMPLATE=""

template_suchen() {
  # Liefert den besten verfügbaren Debian-13/12-Template-Namen für die Host-Arch.
  # Sortiert nach Version (absteigend), neuestes zuerst.
  pveam available 2>/dev/null \
    | grep -E "debian-1[23]-standard[_-][0-9][^_]*_${ARCH}\.tar\.zst" \
    | sort -rV \
    | head -n1 \
    | awk '{print $2}'
}

# Schritt 1: Template-Download
info "Suche passendes Debian-Template für $ARCH ..."
pveam update >/dev/null 2>&1 || warn "pveam update fehlgeschlagen – fahre mit vorhandener Liste fort."

# Erst: ist bereits ein passendes Template im Cache?
TEMPLATE="$(pveam list local 2>/dev/null \
  | grep -E "debian-1[23]-standard[_-][0-9][^_]*_${ARCH}\.tar\.zst" \
  | sort -rV | head -n1 | awk '{print $1}' || true)"
if [ -n "$TEMPLATE" ]; then
  ok "Verwendbares Template bereits im Cache: $TEMPLATE"
else
  # Zweit: aus pveam available suchen und herunterladen
  TEMPLATE="$(template_suchen || true)"
  TEMPLATE="${TEMPLATE:-}"
  if [ -n "$TEMPLATE" ]; then
    info "Verfügbares Template: $TEMPLATE – lade herunter ..."
    if pveam download local "$TEMPLATE" 2>/dev/null; then
      ok "Template geladen: $TEMPLATE"
    else
      err "pveam download local $TEMPLATE ist fehlgeschlagen."
      err "Diagnose:"
      err "  Host-Architektur: $(uname -m)"
      err "  pveam available | grep debian:"
      pveam available 2>/dev/null | grep -i debian | head -5 >&2 || true
      err "  Vorhandene Templates:"
      pveam list local 2>/dev/null | head -5 >&2 || true
      err "Bitte prüfen: pveam update, Storage-Content 'vztmpl' aktiv?"
      exit 1
    fi
  else
    # Dritt: manueller Download von GitHub (Fallback, falls pveam-Index fehlt)
    warn "Kein Debian-Template in pveam available – versuche manuellen Download ..."
    GITHUB_URL="https://github.com/proxmox/container-templates/raw/master/debian-13-standard_${ARCH}.tar.zst"
    TEMPLATE="debian-13-standard_${ARCH}.tar.zst"
    mkdir -p /var/lib/vz/template/cache 2>/dev/null || true
    if curl -fsSL --max-time 180 "$GITHUB_URL" -o "/var/lib/vz/template/cache/$TEMPLATE" 2>/dev/null; then
      ok "Template manuell nach /var/lib/vz/template/cache geladen."
    else
      err "Kein Debian-Template für $ARCH verfügbar (pveam und manueller Download fehlgeschlagen)."
      err "Diagnose:"
      err "  Host-Architektur: $(uname -m)"
      err "  pveam available | grep debian:"
      pveam available 2>/dev/null | grep -i debian | head -5 >&2 || true
      err "  Vorhandene Templates:"
      pveam list local 2>/dev/null | head -5 >&2 || true
      err "Bitte prüfen: pveam update, Storage-Content 'vztmpl' aktiv?"
      exit 1
    fi
  fi
fi
ok "Template bereit: $TEMPLATE"

# Speicher prüfen
# pvesm status liefert: Name Type Status Total Used Available → Status ist Spalte 3!
STORAGE="$(pvesm status 2>/dev/null | awk 'NR>1 && $3=="active" {print $1; exit}')"
if [ -z "$STORAGE" ]; then
  # Fallback: Speicher mit Typ dir/lvm/zfs (kein NFS/ISO-Lager)
  STORAGE="$(pvesm status 2>/dev/null | awk 'NR>1 && ($2=="dir" || $2=="lvm" || $2=="zfs" || $2=="zfspool") {print $1; exit}')"
fi
if [ -z "$STORAGE" ]; then
  STORAGE="local-lvm"
  warn "Kein aktiver Storage erkannt – verwende $STORAGE (bitte prüfen!)."
fi
ok "Verwende Storage: $STORAGE"

# WICHTIG (Live auf ProxSmartHome): vztmpl muss NICHT aktiviert sein!
# pct download lädt das Template direkt in den lokalen Cache (/var/lib/vz/template/cache),
# und pct create nutzt den lokalen Pfad "local:vztmpl/...". Das funktioniert AUCH,
# wenn der Ziel-Storage (z. B. local-lvm) kein vztmpl unterstützt – die
# vztmpl-Beschränkung gilt NUR für den Storage, NICHT für den lokalen Template-Cache.

# CT anlegen (unprivileged, nesting, onboot)
info "Erstelle Container $CTID ($CT_HOSTNAME, ${CORES} vCPU, ${MEMORY} MB RAM, ${DISK} GB) ..."
if pct status "$CTID" >/dev/null 2>&1; then
  err "Container $CTID existiert bereits. Andere ID mit --id wählen."
  exit 1
fi
# Template aus dem lokalen Cache beziehen (local:vztmpl/...), nicht vom Ziel-Storage.
# WICHTIG (Live auf ProxSmartHome): pct create kennt KEIN --disk!
# Die Root-Disk wird über --rootfs <storage>:<größe> gesetzt (z. B. local-lvm:8).
pct create "$CTID" "local:vztmpl/$TEMPLATE" \
  --hostname "$CT_HOSTNAME" \
  --cores "$CORES" \
  --memory "$MEMORY" \
  --rootfs "${STORAGE}:${DISK}" \
  --net0 "name=eth0,bridge=vmbr0,ip=dhcp" \
  --nameserver "1.1.1.1 8.8.8.8" \
  --onboot 1 \
  --features nesting=1 \
  --unprivileged 1 \
  --description "Haushaltsbuch (lokal, React + FastAPI) – Port $WEB_PORT" \
  --start 1
ok "Container $CTID erstellt."

# Grube (bekannt): pct create --start 1 liefert Exit 0, auch wenn der Spawn scheitert.
verify_ct_started() {
  local id="$1" status
  for i in $(seq 1 15); do
    sleep 1
    status="$(pct status "$id" 2>/dev/null | awk '{print $2}')"
    [ "$status" = "running" ] && { ok "Container $id läuft."; return 0; }
  done
  status="$(pct status "$id" 2>/dev/null | awk '{print $2}')"
  if [ "$status" = "running" ]; then return 0; fi
  err "Container $id läuft nicht (Status: ${status:-unbekannt})."
  if [ "$ARCH" != "$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')" ]; then
    err "Architektur-Konflikt möglich (Host: $(uname -m), Template: $ARCH)."
  fi
  err "Diagnose: pct start $id; pct status $id"
  err "Deinstallieren: $ONE_LINER --uninstall --id $id"
  exit 1
}
verify_ct_started "$CTID"

# Auf Netz warten (DHCP-Race, nicht blind schlafen)
info "Warte auf Netz im Container ..."
for i in $(seq 1 90); do
  if [ -n "$(pct exec "$CTID" -- hostname -I 2>/dev/null | tr -d ' ' | grep -v '^$' | grep -v '^127\.' || true)" ]; then
    break
  fi
  sleep 1
  [ "$i" -eq 90 ] && { err "Container $CTID bekommt keine IP (DHCP-Timeout)."; exit 1; }
done
IP="$(ct_ip "$CTID")"
[ -n "$IP" ] || { err "Konnte Container-IP nicht ermitteln."; exit 1; }
ok "Container läuft unter $IP"

# DNS im Container prüfen (Grube: flaky resolv.conf)
if ! pct exec "$CTID" -- getent hosts raw.githubusercontent.com >/dev/null 2>&1; then
  warn "DNS im Container defekt – Fallback-Nameserver werden gesetzt ..."
  pct exec "$CTID" -- bash -c 'printf "nameserver 1.1.1.1\nnameserver 8.8.8.8\n" > /etc/resolv.conf' || true
  pct set "$CTID" --nameserver "1.1.1.1 8.8.8.8" 2>/dev/null || true
fi

# Inner-Setup-Skript laden – gegen GitHub-Raw-Lag gehärtet:
# 1. Versuch mit Cache-Buster (frisch), 2. Fallback auf den aktuellen Commit-SHA
#    (Raw nach SHA ist nicht vom main-Cache betroffen), 3. letzter Versuch ohne.
# Inner-Setup ausführen (Code + Build + nginx + systemd)
info "Führe In-Container-Setup aus ..."
fetch_inner_script /tmp/haushaltsbuch-inner.sh
pct push "$CTID" /tmp/haushaltsbuch-inner.sh /root/inner.sh
pct exec "$CTID" -- env PORT="$WEB_PORT" APP_DIR="/opt/haushaltsbuch" \
  REPO_URL="$REPO_URL" BRANCH="$BRANCH" \
  bash -c 'set -o pipefail; bash /root/inner.sh 2>&1 | tee -a /var/log/haushaltsbuch.log'

# ----------------------------------------------------------------- Verifikation
header "Verifikation"
VERIFY_OK=1

info "Prüfe systemd-Service ..."
if pct exec "$CTID" -- systemctl is-active haushaltsbuch >/dev/null 2>&1; then
  ok "haushaltsbuch.service ist aktiv."
else
  err "haushaltsbuch.service ist NICHT aktiv."
  pct exec "$CTID" -- journalctl -u haushaltsbuch -n 30 --no-pager >&2 || true
  VERIFY_OK=0
fi

info "Prüfe nginx ..."
if pct exec "$CTID" -- systemctl is-active nginx >/dev/null 2>&1; then
  ok "nginx ist aktiv."
else
  err "nginx ist NICHT aktiv."
  VERIFY_OK=0
fi

info "Prüfe Web-UI (localhost im Container, Port $WEB_PORT) ..."
CODE="$(pct exec "$CTID" -- curl -sL -o /dev/null -w '%{http_code}' "http://127.0.0.1:$WEB_PORT/" 2>/dev/null || true)"
if [ "$CODE" = "200" ]; then
  ok "Web-UI antwortet mit HTTP 200."
else
  err "Web-UI antwortet mit '$CODE' (erwartet 200)."
  pct exec "$CTID" -- journalctl -u haushaltsbuch -n 30 --no-pager >&2 || true
  VERIFY_OK=0
fi

info "Prüfe API-Endpoint ..."
ACODE="$(pct exec "$CTID" -- curl -sL -o /dev/null -w '%{http_code}' "http://127.0.0.1:$WEB_PORT/api/health" 2>/dev/null || true)"
if [ "$ACODE" = "200" ]; then
  ok "API /api/health antwortet mit HTTP 200."
else
  err "API /api/health antwortet mit '$ACODE'."
  VERIFY_OK=0
fi

# ----------------------------------------------------------------- Zusammenfassung
header "Installation abgeschlossen"
cat <<EOF
  ${C_BOLD}Haushaltsbuch${C_RESET} läuft jetzt lokal auf deinem Proxmox-Host.

  ${C_BOLD}Container${C_RESET}   $CTID ($CT_HOSTNAME)
  ${C_BOLD}IP-Adresse${C_RESET}  $IP
  ${C_BOLD}Web-UI${C_RESET}      http://$IP:$WEB_PORT
  ${C_BOLD}API-Doku${C_RESET}    http://$IP:$WEB_PORT/docs

  ${C_BOLD}Services im Container${C_RESET}
    systemctl status haushaltsbuch    # FastAPI-Backend (Port 8099, intern)
    systemctl status nginx           # Web-UI + Reverse-Proxy (Port $WEB_PORT)
    journalctl -u haushaltsbuch -f    # Logs live

  ${C_BOLD}Daten${C_RESET}         /opt/haushaltsbuch/data/haushaltsbuch.db
  ${C_BOLD}Frontend-Build${C_RESET} /opt/haushaltsbuch/static

  ${C_BOLD}Update${C_RESET}
    ${ONE_LINER} --update
  ${C_BOLD}Deinstallieren${C_RESET}
    ${ONE_LINER} --uninstall
  ${C_BOLD}Status${C_RESET}
    ${ONE_LINER} --status

  ${C_DIM}nächster Schritt: im Browser http://$IP:$WEB_PORT öffnen${C_RESET}
EOF

if [ "$VERIFY_OK" -eq 0 ]; then
  warn "Mindestens eine Verifikation ist fehlgeschlagen – Details oben."
  exit 1
fi
ok "Alle Verifikationen grün."