"""SQLite-Zugriffsschicht (WAL-Mode, Thread-local connections)."""
from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Sequence

from .config import DB_PATH, ensure_dirs

_local = threading.local()

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS konten (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    beschreibung TEXT   DEFAULT '',
    iban        TEXT    DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS kategorien (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    art  TEXT NOT NULL DEFAULT 'beide' CHECK (art IN ('einnahme','ausgabe','beide')),
    icon TEXT NOT NULL DEFAULT '📦',
    farbe TEXT NOT NULL DEFAULT '#6366f1'
);

CREATE TABLE IF NOT EXISTS buchungen (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    datum       TEXT    NOT NULL,             -- ISO: YYYY-MM-DD
    betrag      REAL    NOT NULL,             -- immer positiv
    typ         TEXT    NOT NULL CHECK (typ IN ('einnahme','ausgabe')),
    beschreibung TEXT   NOT NULL DEFAULT '',
    kategorie_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
    konto_id    INTEGER REFERENCES konten(id) ON DELETE SET NULL,
    gegen_iban  TEXT    DEFAULT '',
    art         TEXT    DEFAULT 'Manuell',
    notiz       TEXT    DEFAULT '',
    beleg_name  TEXT    DEFAULT '',
    manually_edit INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_buchungen_datum  ON buchungen(datum DESC);
CREATE INDEX IF NOT EXISTS idx_buchungen_monat  ON buchungen(substr(datum,1,7));
CREATE INDEX IF NOT EXISTS idx_buchungen_kat    ON buchungen(kategorie_id);

CREATE TABLE IF NOT EXISTS keyword_kategorie (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    schluesselwort TEXT NOT NULL UNIQUE,
    kategorie_id INTEGER NOT NULL REFERENCES kategorien(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS meta (
    schluessel TEXT PRIMARY KEY,
    wert     TEXT
);
"""

DEFAULT_KATEGORIEN: list[tuple[str, str, str, str]] = [
    # name, art, icon, farbe
    ("Lebensmittel", "ausgabe", "🛒", "#22c55e"),
    ("Restaurant", "ausgabe", "🍽️", "#f97316"),
    ("Tanken", "ausgabe", "⛽", "#ef4444"),
    ("Mobilität", "ausgabe", "🚗", "#0ea5e9"),
    ("Wohnen", "ausgabe", "🏠", "#8b5cf6"),
    ("Energie", "ausgabe", "💡", "#eab308"),
    ("Versicherungen", "ausgabe", "🛡️", "#64748b"),
    ("Gesundheit", "ausgabe", "💊", "#14b8a6"),
    ("Freizeit", "ausgabe", "🎬", "#ec4899"),
    ("Abos", "ausgabe", "🔁", "#a855f7"),
    ("Kleidung", "ausgabe", "👕", "#f43f5e"),
    ("Geschenke", "ausgabe", "🎁", "#d946ef"),
    ("Sonstiges", "ausgabe", "📦", "#94a3b8"),
    ("Gehalt", "einnahme", "💼", "#16a34a"),
    ("Nebenverdienst", "einnahme", "💵", "#10b981"),
    ("Erstattung", "einnahme", "↩️", "#06b6d4"),
]

DEFAULT_KEYWORDS: list[tuple[str, str]] = [
    ("rewe", "Lebensmittel"), ("edeka", "Lebensmittel"), ("aldi", "Lebensmittel"),
    ("lidl", "Lebensmittel"), ("penny", "Lebensmittel"), ("kaufland", "Lebensmittel"),
    ("dm-", "Sonstiges"), ("rossmann", "Sonstiges"),
    ("shell", "Tanken"), ("aral", "Tanken"), ("total", "Tanken"), ("esso", "Tanken"),
    ("mcdonald", "Restaurant"), ("burger king", "Restaurant"), ("gastro", "Restaurant"),
    ("netflix", "Abos"), ("spotify", "Abos"), ("disney", "Abos"),
    ("gehalt", "Gehalt"), ("lohn", "Gehalt"), ("salary", "Gehalt"),
]


def money(value: float | int | Decimal | str | None) -> float:
    """Beträge auf 2 Nachkommastellen normalisieren (Banklogik)."""
    if value in (None, ""):
        return 0.0
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def get_conn() -> sqlite3.Connection:
    """Thread-lokale Verbindung (WAL erlaubt parallele Reader)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = connect()
        _local.conn = conn
    return conn


def query(sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return list(get_conn().execute(sql, params).fetchall())


def query_one(sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    return get_conn().execute(sql, params).fetchone()


def execute(sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
    cur = get_conn().execute(sql, params)
    if get_conn().in_transaction:
        get_conn().commit()
    return cur


def execute_many(sql: str, rows: Iterable[Sequence[Any]]) -> None:
    cur = get_conn().executemany(sql, rows)
    if get_conn().in_transaction:
        get_conn().commit()
    del cur


def iso_today() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db() -> None:
    """Legt Schema + Standard-Kategorien an (idempotent)."""
    ensure_dirs()
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) FROM kategorien").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO kategorien (name, art, icon, farbe) VALUES (?,?,?,?)",
                DEFAULT_KATEGORIEN,
            )
        kw_count = conn.execute("SELECT COUNT(*) FROM keyword_kategorie").fetchone()[0]
        if kw_count == 0:
            for wort, kat in DEFAULT_KEYWORDS:
                row = conn.execute("SELECT id FROM kategorien WHERE name=?", (kat,)).fetchone()
                if row:
                    conn.execute(
                        "INSERT OR IGNORE INTO keyword_kategorie (schluesselwort, kategorie_id) VALUES (?,?)",
                        (wort, row["id"]),
                    )
        meta = conn.execute("SELECT wert FROM meta WHERE schluessel='schema_version'").fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO meta (schluessel, wert) VALUES ('schema_version','1')",
        )
        conn.commit()
    finally:
        conn.close()