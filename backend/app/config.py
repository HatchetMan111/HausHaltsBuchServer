"""Zentrale Konfiguration des Haushaltsbuchs.

Alle Pfade werden aus Umgebungsvariablen bzw. aus /opt/haushaltsbuch abgeleitet,
damit die App sowohl im LXC als auch lokal (Entwicklung) läuft.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(os.environ.get("HAUSHALTSBUCH_APP_DIR", "/opt/haushaltsbuch"))
DATA_DIR = Path(os.environ.get("HAUSHALTSBUCH_DATA_DIR", APP_DIR / "data"))
DB_PATH = Path(os.environ.get("HAUSHALTSBUCH_DB", DATA_DIR / "haushaltsbuch.db"))
HOST = os.environ.get("HAUSHALTSBUCH_HOST", "0.0.0.0")
PORT = int(os.environ.get("HAUSHALTSBUCH_PORT", "8098"))
STATIC_DIR = APP_DIR / "static"


def ensure_dirs() -> None:
    """Legt Daten- und Upload-Verzeichnisse an (idempotent).

    Schlägt fehl, wenn DATA_DIR nicht beschreibbar ist – der systemd-Unit
    setzt HAUSHALTSBUCH_DATA_DIR/DB explizit; ohne Env greift /opt/haushaltsbuch.
    """
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
        # Schreibtest: startet die App auf einem read-only oder fremden Pfad,
        # soll sie hier mit klarer Meldung abbrechen statt später im Betrieb.
        probe = DATA_DIR / ".write-test"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        raise RuntimeError(
            f"Datenverzeichnis {DATA_DIR} ist nicht beschreibbar: {exc}. "
            "Bitte HAUSHALTSBUCH_DATA_DIR/DB im systemd-Unit prüfen."
        ) from exc