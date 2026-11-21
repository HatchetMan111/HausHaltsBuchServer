# Haushaltsbuch (Proxmox-LXC)

Lokales Haushaltsbuch für dein Proxmox-Homelab – vollständig offline, ohne Cloud,
ohne Konto. CSV-Umsätze von der Bank importieren, Kategorien automatisch zuordnen
lassen und Einnahmen/Ausgaben auf einen Blick sehen.

Frontend: **React + Vite** (komplett neu, modern) · Backend: **Python/FastAPI + SQLite**
· Web-UI: **http://&lt;LXC-IP&gt;:8098** · Basis: Debian 13 LXC (unprivilegiert, 2 vCPU / 2 GB / 8 GB)

> Datengrundlage: [Sleepwalker86/Haushaltsbuch](https://github.com/Sleepwalker86/Haushaltsbuch)
> (Flask + MySQL). Diese Version übernimmt das Konzept (CSV → Kategorien → Dashboard),
> portiert es auf FastAPI/SQLite (kein externer DB-Server nötig) und ersetzt die
> Server-gerenderten Templates durch ein modernes React-Frontend.

---

## 1. Installation (Einzeiler auf dem Proxmox-Host)

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/HausHaltsBuchServer/main/install/haushaltsbuch.sh)"
```

> **CDN-Hinweis:** GitHub Raw kann nach einem Push einige Minuten veraltet sein.
> Wenn der Einzeiler oben noch eine alte Version lädt, nimm den Stand des
> aktuellen Commits (funktioniert sofort, kein Cache):
>
> ```bash
> bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/HausHaltsBuchServer/2ac7684/install/haushaltsbuch.sh)"
> ```

Das Skript erstellt selbstständig einen LXC (nächste freie CT-ID, Debian 13,
unprivilegiert, nesting, `onboot=1`), installiert Node 22 + Python-Abhängigkeiten,
baut das React-Frontend, richtet nginx (Port 8098) + systemd-Service ein und
verifiziert am Ende Service, Web-UI und API.

### Optionen

```bash
# Eigene Container-ID / Ressourcen
bash -c "$(wget -qLO - .../install/haushaltsbuch.sh)" -- --id 120 --cores 2 --memory 2048 --disk 8

# Aktuellen Stand aktualisieren (Code + Build, Daten bleiben erhalten)
bash -c "$(wget -qLO - .../install/haushaltsbuch.sh)" -- --update

# Status / Deinstallation
bash -c "$(wget -qLO - .../install/haushaltsbuch.sh)" -- --status
bash -c "$(wget -qLO - .../install/haushaltsbuch.sh)" -- --uninstall
```

> **Aufruf-Kuriosum:** `bash -c "$(wget …)" --update` schickt `--update` in `$0`.
> Das Skript fängt das ab (`$0`-Fallback) – **beide** Varianten funktionieren:
> `… --update` und `… -- --update`. Der `--`-Trenner wird dabei entfernt.
> Beispiel: `bash -c "$(wget -qLO - <URL>)" -- --update --id 120`

---

## 2. Funktionen

| Bereich | Was es tut |
|---|---|
| **Dashboard** | Einnahmen, Ausgaben, Überschuss, Sparquote, Kontensalden; Ausgaben nach Kategorie; Monatsverlauf; größte Empfänger |
| **Buchungen** | Alle Buchungen, filterbar (Jahr, Monat, Typ, Konto, Freitext), anlegen/bearbeiten/löschen |
| **Analyse** | Jahresvergleich (z. B. 2026 vs. 2025), Sparquote, Ausgaben je Kategorie, Monatsvergleich |
| **Import & Export** | Bank-CSV (Sparkasse, ING, Comdirect, Volksbank …), deutsches Format 1.234,56 €; Duplikatprüfung; CSV-Export (Excel-kompatibel) |
| **Verwaltung** | Konten, Kategorien (Icon + Farbe), Auto-Regeln (Schlüsselwort → Kategorie), Batch-Zuordnung, Systemstatus + Logs |

**Auto-Kategorisierung:** Neue CSV-Buchungen werden anhand der Regeln in
*Verwaltung → Auto-Regeln* zugeordnet (z. B. `rewe` → Lebensmittel, `shell` → Tanken).
Regeln lassen sich jederzeit ergänzen; bestehende Buchungen können per
*Batch-Zuordnung* nachträglich sortiert werden.

---

## 3. Architektur (Container)

```
Browser ──► nginx :8098 ──► FastAPI :8099 (127.0.0.1)
                 │
                 └─ statisches React-Build (/opt/haushaltsbuch/static)
Daten:  /opt/haushaltsbuch/data/haushaltsbuch.db (SQLite, WAL)
Logs:   /var/log/haushaltsbuch.log + journalctl -u haushaltsbuch
```

| Datei | Zweck |
|---|---|
| `install/haushaltsbuch.sh` | Host-Installer (Proxmox): CT erstellen, Setup, Verifikation |
| `deploy/inner.sh` | In-Container-Setup: Pakete, Node, App-Code, Build, nginx, systemd |
| `deploy/haushaltsbuch.service` | systemd-Unit (Referenz; wird von `inner.sh` geschrieben) |
| `backend/` | FastAPI-App (`app/`), SQLite-Schema, CSV-Parser, Statistik |
| `frontend/` | React/Vite-Spa (Build landet in `backend/static` bzw. `static/`) |

### Verifikation (automatisch am Ende der Installation)

- `systemctl is-active haushaltsbuch` und `nginx`
- `curl -L http://127.0.0.1:8098/` → **HTTP 200**
- `curl -L http://127.0.0.1:8098/api/health` → **HTTP 200** (JSON)

Ausgabe am Ende enthält IP, URL, Update-/Deinstall-Befehl.

---

## 4. Bedienung (Browser)

Beim ersten Start ist die Datenbank leer. Zwei Wege, Daten zu sehen:

1. **Demo-Daten**: *Verwaltung → System → Demo-Daten laden* (31 realistische Buchungen).
2. **Echte Daten**: *Import & Export → CSV-Import* – Bank-Export hochladen,
   Ziel-Konto wählen, fertig. Eigene Buchungen lassen sich unter *Buchungen*
   ergänzen; CSV-Export gibt alles im Excel-Format zurück.

---

## 5. Update / Deinstallation / Wartung

```bash
# Update (Code + Build; DB bleibt erhalten)
bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/HausHaltsBuchServer/main/install/haushaltsbuch.sh)" -- --update

# Status inkl. URL
bash -c "$(wget -qLO - .../install/haushaltsbuch.sh)" -- --status

# Deinstallieren (Container + Daten)
bash -c "$(wget -qLO - .../install/haushaltsbuch.sh)" -- --uninstall

# Logs
pct exec <CTID> -- journalctl -u haushaltsbuch -n 100 --no-pager
pct exec <CTID> -- tail -f /var/log/haushaltsbuch.log
```

### Bekannte Stolperfallen (aus anderen Installern gelernt)

- **Arch-Filter**: `pveam`-Cache enthält oft amd64 UND arm64 – der Installer wählt
  das Template passend zur Host-Architektur (`dpkg --print-architecture`), sonst
  bootet der CT nicht.
- **`pct create --start 1` meldet Exit 0**, auch wenn der Start scheitert – deshalb
  prüft der Installer den Status aktiv (`verify_ct_started`) und gibt bei Misserfolg
  den Deinstallations-Befehl aus.
- **DNS im CT** kann nach DHCP-Lease-Erneuerung flaky sein – der Installer prüft
  `getent hosts` und setzt Fallback-Nameserver.
- **Bekannter Bash-Eigenbau**: `bash -c "$(...)" --update` schluckt Optionen;
  das Skript hat einen `$0`-Fallback eingebaut.

---

## 6. Lizenz

Projektlizenz: MIT (siehe `LICENSE`). Daten bleiben zu 100 % lokal.