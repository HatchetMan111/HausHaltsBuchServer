"""CSV-Import/Export für Buchungen (deutsches Semikolon-Format)."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any

from .. import db
from ..db import money
from . import stats
from .csvio import parse_csv_text

EXPORT_HEADER = [
    "Datum", "Typ", "Betrag", "Beschreibung", "Kategorie", "Konto",
    "Gegen-IBAN", "Art", "Beleg", "Notiz",
]


def _typ(row: dict[str, Any]) -> str:
    return "Einnahme" if row.get("typ") == "einnahme" else "Ausgabe"


def export_csv(year: int | None = None, month: int | None = None, konto_id: int | None = None) -> str:
    buchungen = stats.list_buchungen(
        year=year, month=month, konto_id=konto_id, limit=100000
    )
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(EXPORT_HEADER)
    for b in buchungen:
        writer.writerow([
            datetime.strptime(b["datum"], "%Y-%m-%d").strftime("%d.%m.%Y"),
            _typ(b),
            f"{(1 if b['typ'] == 'einnahme' else -1) * abs(float(b['betrag'] or 0)):.2f}".replace(".", ","),
            b["beschreibung"] or "",
            b["kategorie"] or "",
            b["konto"] or "",
            b["gegen_iban"] or "",
            b["art"] or "",
            b["beleg_name"] or "",
            b["notiz"] or "",
        ])
    return out.getvalue()


def import_text(text: str, konto_id: int | None = None, quelle: str = "CSV-Import") -> dict[str, Any]:
    """Importiert CSV/Umsatzdaten; Duplikate werden anhand Datum+Betrag+Beschreibung übersprungen."""
    parsed = parse_csv_text(text)
    if not parsed.rows:
        return {"importiert": 0, "uebersprungen": 0, "fehler": len(parsed.skipped),
                "details": parsed.skipped[:20], "eigene_iban": parsed.eigene_iban}

    existing: set[tuple[str, str, str, str]] = set()
    for r in db.query("SELECT datum, beschreibung, betrag, typ FROM buchungen"):
        existing.add((r["datum"], (r["beschreibung"] or "").strip().lower(),
                      f"{abs(float(r['betrag'] or 0)):.2f}", r["typ"]))

    importiert = uebersprungen = fehler = 0
    zeilen: list[tuple[Any, ...]] = []
    for row in parsed.rows:
        typ = "einnahme" if row.betrag > 0 else "ausgabe"
        key = (row.datum, (row.beschreibung or "").strip().lower(), f"{abs(row.betrag):.2f}", typ)
        if key in existing:
            uebersprungen += 1
            continue
        existing.add(key)
        betrag = abs(row.betrag)
        kategorie_id = stats.auto_kategorisieren(row.beschreibung)
        zeilen.append((
            row.datum, betrag, typ, row.beschreibung, kategorie_id, konto_id,
            row.gegen_iban, quelle, "", 0,
        ))
        importiert += 1
    fehler = len(parsed.skipped)
    if zeilen:
        db.execute_many(
            """
            INSERT INTO buchungen
                (datum, betrag, typ, beschreibung, kategorie_id, konto_id,
                 gegen_iban, art, beleg_name, manually_edit)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            zeilen,
        )
    return {
        "importiert": importiert,
        "uebersprungen": uebersprungen,
        "fehler": fehler,
        "details": parsed.skipped[:20],
        "eigene_iban": parsed.eigene_iban,
    }


def duplicates_check() -> list[dict[str, Any]]:
    rows = db.query(
        """
        SELECT datum, beschreibung, betrag, COUNT(*) AS n
        FROM buchungen GROUP BY datum, beschreibung, betrag HAVING n > 1
        ORDER BY n DESC LIMIT 50
        """
    )
    return [dict(r) for r in rows]


def today_str() -> str:
    return date.today().isoformat()


def to_float(value: Any) -> float:
    return money(value)