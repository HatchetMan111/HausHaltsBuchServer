#!/bin/bash
# Mock-Harness für install/haushaltsbuch.sh
# Führt den Installer in einem User-Namespace (EUID 0) mit gefälschten
# Proxmox-Befehlen aus und prüft den Ablauf (idempotent, ohne echten CT).
#
# Nutzung:  ./test-harness.sh
set -Eeuo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$HERE"
INSTALLER="$REPO/install/haushaltsbuch.sh"
WORK="$(mktemp -d)"
MOCKBIN="$WORK/bin"
MOCK_STATE="$WORK/pct-state"
CALLS="$WORK/calls.log"
INNER_SRC="$REPO/deploy/inner.sh"
INNER_MOCK="$INNER_SRC"
: > "$WORK/output.log"

pass=0; fail=0
ok()   { pass=$((pass+1)); printf '  \033[32mPASS\033[0m %s\n' "$*"; }
bad()  { fail=$((fail+1)); printf '  \033[31mFAIL\033[0m %s\n' "$*"; }
check(){ if eval "$2"; then ok "$1"; else bad "$1"; fi; }

cleanup() { [ "${KEEP:-0}" = "1" ] && { echo "WORK=$WORK"; return; }; rm -rf "$WORK"; }
trap cleanup EXIT

# ---------------------------------------------------------------- Mocks bauen
mkdir -p "$MOCKBIN"
cat > "$MOCKBIN/pct" <<'MOCK'
#!/bin/bash
echo "pct $*" >> "$MOCK_CALLS"
state="${MOCK_STATE:?MOCK_STATE fehlt}"
touch "$state"
exists() { [ "$1" = "100" ] || [ "$1" = "101" ] || grep -qx "$1" "$state"; }
case "$1" in
  list)
    # Format: VMID Status Name (Name = letzte Spalte)
    cat <<EOF
VMID Status  Name
100  running other-container
101  stopped haushaltsbuch
EOF
    ;;
  status)
    id="$2"
    if ! exists "$id"; then
      echo "CT $id does not exist" >&2
      exit 1
    fi
    if [ "$id" = "101" ] && ! grep -qx "$id" "$state.started" 2>/dev/null; then
      echo "status: stopped"
    else
      echo "status: running"
    fi
    ;;
  create)
    id="$2"
    echo "Creating CT $id ..."
    if [ "${FAIL_SPAWN:-0}" = "1" ]; then
      # pct meldet Erfolg, der Spawn scheitert aber (bekannte Proxmox-Grube)
      echo "sync_wait: Failed to spawn" >&2
      exit 0
    fi
    echo "$id" >> "$state"
    ;;
  start)
    echo "$2" >> "$state.started"
    ;;
  stop)
    if [ -f "$state.started" ]; then
      grep -vx "$2" "$state.started" > "$state.started.tmp" 2>/dev/null || true
      mv "$state.started.tmp" "$state.started" 2>/dev/null || true
    fi
    ;;
  destroy)
    if [ -f "$state.started" ]; then
      grep -vx "$2" "$state.started" > "$state.started.tmp" 2>/dev/null || true
      mv "$state.started.tmp" "$state.started" 2>/dev/null || true
    fi
    ;;
  push|set) ;;
  exec)
    shift 2
    # pct exec <id> -- <cmd>: den Separator ueberspringen (bekannte Grube)
    while [ "${1:-}" = "--" ]; do shift; done
    # In-Container-Aufrufe erkennen (auch mit vorgeschalteten env-Zuweisungen)
    if [[ " $* " == *"inner.sh"* ]]; then
      echo "INNER-RUN" >> "$MOCK_CALLS"
      exit 0
    fi
    case "$1" in
      hostname) echo "10.0.0.55 172.17.0.1" ;;
      systemctl) exit 0 ;;
      getent) exit 0 ;;
      curl) echo "200" ;;
      journalctl) echo "(mock journal)" ;;
      *) ;;
    esac
    exit 0
    ;;
  *) exit 0 ;;
esac
MOCK
chmod +x "$MOCKBIN/pct"

cat > "$MOCKBIN/pveam" <<'MOCK'
#!/bin/bash
echo "pveam $*" >> "$MOCK_CALLS"
case "$1" in
  list)
    echo "local:vztmpl/debian-13-standard_amd64.tar.zst"
    ;;
  available)
    echo "debian-13-standard_amd64.tar.zst 2024-01-01"
    ;;
  download|update) ;;
esac
MOCK
chmod +x "$MOCKBIN/pveam"

cat > "$MOCKBIN/pvesm" <<'MOCK'
#!/bin/bash
echo "pvesm $*" >> "$MOCK_CALLS"
cat <<EOF
Name        Type  Status  Total  Used  Available
local-lvm   lvm   active  100G   10G   90G
EOF
MOCK
chmod +x "$MOCKBIN/pvesm"

cat > "$MOCKBIN/wget" <<'MOCK'
#!/bin/bash
# wget -qLO - <url>  → gibt ein Stub-Skript aus
out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -O) out="$2"; shift 2 ;;
    *) shift ;;
  esac
done
cat > "${out:--}" <<'STUB'
#!/bin/bash
echo "STUB-INSTALLER"
STUB
MOCK
chmod +x "$MOCKBIN/wget"

cat > "$MOCKBIN/curl" <<'MOCK'
#!/bin/bash
url=""; out=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
case "$url" in
  *127.0.0.1*|*localhost*)
    # Healthcheck-Antwort (der Installer wertet den HTTP-Code aus)
    echo "200"
    exit 0
    ;;
esac
if [ -n "$out" ] && [ "$out" != "/dev/null" ]; then
  if [ -n "${INNER_MOCK:-}" ] && [ -f "${INNER_MOCK}" ]; then
    cp "$INNER_MOCK" "$out"
  else
    echo "#!/bin/bash" > "$out"
  fi
fi
MOCK
chmod +x "$MOCKBIN/curl"

# ---------------------------------------------------------------- Runner
run_installer() {
  : > "$CALLS"
  : > "$WORK/output.log"
  rm -f "$MOCK_STATE" 2>/dev/null || true
  local rc=0
  if command -v unshare >/dev/null 2>&1; then
    # EUID 0 via User-Namespace, damit die Root-Prüfung des Installers greift.
    # Argumente werden positional durchgereicht ($1 = Installer, ab $2 die Optionen),
    # damit keine Anführungszeichen-Eskalation nötig ist.
    MOCK_CALLS="$CALLS" MOCK_STATE="$MOCK_STATE" INNER_MOCK="$INNER_MOCK" INNER_SRC="$INNER_SRC" \
      PATH="$MOCKBIN:$PATH" \
      unshare -rm bash -c 'bash "$1" "${@:2}"' _ "$INSTALLER" "$@" \
      > "$WORK/output.log" 2>&1 || rc=$?
  else
    # Fallback (lokale Smoke-Tests): Installer ohne Root-Prüfung ausführen
    env MOCK_CALLS="$CALLS" MOCK_STATE="$MOCK_STATE" INNER_MOCK="$INNER_MOCK" INNER_SRC="$INNER_SRC" \
      PATH="$MOCKBIN:$PATH" bash "$INSTALLER" "$@" > "$WORK/output.log" 2>&1 || rc=$?
  fi
  cat "$WORK/output.log"
  return $rc
}

header() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# ---------------------------------------------------------------- Tests
header "1) Hilfe"
run_installer --help >/dev/null
check "Beendet mit 0" 'grep -q "Proxmox-Installer" "$WORK/output.log"'
grep -q "raw.githubusercontent.com" "$WORK/output.log" && ok "Einzeiler-URL im --help" || bad "Einzeiler-URL im --help fehlt"

header "1b) Options-Trenner '--' (Doku-Variante -- --update)"
set +e; run_installer -- --help; rc=$?; set -e
cp "$WORK/output.log" "$WORK/t1b.log"
check "Trenner-Variante Exit 0" '[ "$rc" -eq 0 ]'
grep -q "Proxmox-Installer" "$WORK/t1b.log" && ok "Hilfe ueber -- --help erreichbar" || bad "-- --help zeigt keine Hilfe"

header "2) Status mit unbekannter ID (→ Exit != 0)"
set +e; run_installer --status --id 999 >/dev/null; rc=$?; set -e
[ "$rc" -ne 0 ] && ok "Unbekannte ID schlägt fehl (Exit $rc)" || bad "Status mit unbekannter ID sollte fehlschlagen"

header "2b) Status mit vorhandenem CT 101 (→ Exit 0 + URL)"
run_installer --status --id 101 >/dev/null
rc=$?
check "Status Exit 0" '[ "$rc" -eq 0 ]'
grep -q "http://10.0.0.55:8098" "$WORK/output.log" && ok "URL im Status" || bad "URL im Status fehlt"

header "3) Uninstall (CT 101 vorhanden)"
run_installer --uninstall >/dev/null
rc=$?
check "Uninstall Exit 0" '[ "$rc" -eq 0 ]'
grep -q "pct destroy 101" "$CALLS" && ok "pct destroy 101 aufgerufen" || bad "pct destroy fehlt"

header "4) Volle Installation (Happy Path)"
INNER_MOCK="$INNER_SRC"
run_installer --id 150 --cores 2 --memory 2048 --disk 8 >/dev/null
rc=$?
check "Installation Exit 0" '[ "$rc" -eq 0 ]'
grep -q "pct create 150" "$CALLS" && ok "pct create 150" || bad "pct create 150 fehlt"
grep -q -- "--onboot 1" "$CALLS" && ok "onboot=1 gesetzt" || bad "onboot=1 fehlt"
grep -q "pct exec 150 -- env" "$CALLS" && ok "In-Container-Setup aufgerufen" || bad "In-Container-Setup fehlt"
grep -q "haushaltsbuch-inner.sh" "$CALLS" && ok "inner.sh hochgeladen" || bad "inner.sh push fehlt"
grep -q "http://10.0.0.55:8098" "$WORK/output.log" && ok "URL in Zusammenfassung" || bad "URL fehlt"
grep -q "pct create 150" "$CALLS" && grep -q "haushaltsbuch" "$WORK/output.log" && ok "CT-Name haushaltsbuch" || true

header "5) Arch-Falle (FAIL_SPAWN=1 → Installer muss fehlschlagen)"
set +e; FAIL_SPAWN=1 run_installer --id 151 >/dev/null; rc=$?; set -e
[ "$rc" -ne 0 ] && ok "Spawn-Fehler erkannt (Exit $rc)" || bad "Spawn-Fehler nicht erkannt (Exit 0!)"
grep -qi "startet nicht\|nicht.*running\|Diagnose" "$WORK/output.log" && ok "Diagnose ausgegeben" || bad "Diagnose fehlt"

header "6) Update-Pfad (CT 101 → inner.sh)"
INNER_MOCK="yes"
run_installer --update --id 101 >/dev/null
rc=$?
check "Update Exit 0" '[ "$rc" -eq 0 ]'
grep -q "INNER-RUN" "$CALLS" && ok "inner.sh im Update ausgeführt" || bad "inner.sh im Update nicht ausgeführt"

header "Ergebnis"
printf '  %d PASS, %d FAIL\n' "$pass" "$fail"
[ "$fail" -eq 0 ]