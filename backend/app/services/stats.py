"""Abfrage- und Statistik-Logik des Haushaltsbuchs (SQL-Baukasten)."""
from __future__ import annotations

from typing import Any, Iterable

from .. import db
from ..db import money


# --------------------------------------------------------------------------- #
# Filter
# --------------------------------------------------------------------------- #
def month_filters(year: int | None, month: int | None) -> tuple[str, list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    if year:
        where.append("strftime('%Y', datum) = ?")
        params.append(f"{int(year):04d}")
    if month:
        where.append("strftime('%m', datum) = ?")
        params.append(f"{int(month):02d}")
    return (" AND ".join(where), params)


def available_years() -> list[int]:
    rows = db.query(
        "SELECT DISTINCT strftime('%Y', datum) AS y FROM buchungen ORDER BY y DESC"
    )
    return [int(r["y"]) for r in rows if r["y"]]


def available_months() -> list[dict[str, Any]]:
    rows = db.query(
        """
        SELECT strftime('%Y', datum) AS year, strftime('%m', datum) AS month,
               COUNT(*) AS anzahl
        FROM buchungen GROUP BY year, month ORDER BY year DESC, month DESC
        """
    )
    return [
        {"year": int(r["year"]), "month": int(r["month"]), "anzahl": r["anzahl"]}
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# Konten & Kategorien
# --------------------------------------------------------------------------- #
def list_konten() -> list[dict[str, Any]]:
    rows = db.query("SELECT * FROM konten ORDER BY name COLLATE NOCASE")
    out = []
    for r in rows:
        item = dict(r)
        agg = db.query_one(
            """
            SELECT COALESCE(SUM(CASE WHEN typ='einnahme' THEN betrag ELSE -betrag END),0) AS saldo,
                   COUNT(*) AS anzahl
            FROM buchungen WHERE konto_id = ?
            """,
            (r["id"],),
        )
        item["saldo"] = money(agg["saldo"]) if agg else 0.0
        item["anzahl"] = agg["anzahl"] if agg else 0
        out.append(item)
    return out


def list_kategorien(art: str | None = None) -> list[dict[str, Any]]:
    if art:
        rows = db.query(
            "SELECT * FROM kategorien WHERE art = ? OR art = 'beide' ORDER BY art, name",
            (art,),
        )
    else:
        rows = db.query("SELECT * FROM kategorien ORDER BY art, name")
    return [dict(r) for r in rows]


def save_kategorie(data: dict[str, Any]) -> int:
    if data.get("id"):
        db.execute(
            "UPDATE kategorien SET name=?, art=?, icon=?, farbe=? WHERE id=?",
            (data["name"].strip(), data.get("art", "beide"), data.get("icon", "📦"),
             data.get("farbe", "#6366f1"), data["id"]),
        )
        return int(data["id"])
    cur = db.execute(
        "INSERT OR IGNORE INTO kategorien (name, art, icon, farbe) VALUES (?,?,?,?)",
        (data["name"].strip(), data.get("art", "beide"), data.get("icon", "📦"),
         data.get("farbe", "#6366f1")),
    )
    row = db.query_one("SELECT id FROM kategorien WHERE name=?", (data["name"].strip(),))
    return int(row["id"]) if row else int(cur.lastrowid or 0)


def delete_kategorie(kategorie_id: int) -> None:
    db.execute("DELETE FROM kategorien WHERE id=?", (kategorie_id,))


def save_konto(data: dict[str, Any]) -> int:
    if data.get("id"):
        db.execute(
            "UPDATE konten SET name=?, beschreibung=?, iban=? WHERE id=?",
            (data["name"].strip(), data.get("beschreibung", ""), data.get("iban", ""), data["id"]),
        )
        return int(data["id"])
    cur = db.execute(
        "INSERT INTO konten (name, beschreibung, iban) VALUES (?,?,?)",
        (data["name"].strip(), data.get("beschreibung", ""), data.get("iban", "")),
    )
    return int(cur.lastrowid or 0)


def delete_konto(konto_id: int) -> None:
    db.execute("DELETE FROM konten WHERE id=?", (konto_id,))


def list_keywords() -> list[dict[str, Any]]:
    rows = db.query(
        """
        SELECT k.id, k.schluesselwort, k.kategorie_id, ka.name AS kategorie,
               ka.icon AS icon, ka.farbe AS farbe
        FROM keyword_kategorie k JOIN kategorien ka ON ka.id = k.kategorie_id
        ORDER BY ka.name COLLATE NOCASE, k.schluesselwort
        """
    )
    return [dict(r) for r in rows]


def save_keyword(schluesselwort: str, kategorie_id: int, mapping_id: int | None = None) -> None:
    if mapping_id:
        db.execute(
            "UPDATE keyword_kategorie SET schluesselwort=?, kategorie_id=? WHERE id=?",
            (schluesselwort.strip().lower(), kategorie_id, mapping_id),
        )
    else:
        db.execute(
            "INSERT OR IGNORE INTO keyword_kategorie (schluesselwort, kategorie_id) VALUES (?,?)",
            (schluesselwort.strip().lower(), kategorie_id),
        )


def delete_keyword(mapping_id: int) -> None:
    db.execute("DELETE FROM keyword_kategorie WHERE id=?", (mapping_id,))


def auto_kategorisieren(beschreibung: str) -> int | None:
    text = (beschreibung or "").lower()
    if not text:
        return None
    for row in db.query(
        "SELECT k.schluesselwort AS wort, k.kategorie_id AS kid FROM keyword_kategorie k ORDER BY LENGTH(k.schluesselwort) DESC"
    ):
        if row["wort"] in text:
            return int(row["kid"])
    return None


# --------------------------------------------------------------------------- #
# Buchungen
# --------------------------------------------------------------------------- #
BUCHUNG_SELECT = """
    SELECT b.id, b.datum, b.betrag, b.typ, b.beschreibung, b.art, b.gegen_iban,
           b.notiz, b.beleg_name, b.manually_edit, b.created_at,
           b.kategorie_id, ka.name AS kategorie, ka.icon AS kategorie_icon,
           ka.farbe AS kategorie_farbe,
           b.konto_id, ko.name AS konto
    FROM buchungen b
    LEFT JOIN kategorien ka ON ka.id = b.kategorie_id
    LEFT JOIN konten     ko ON ko.id = b.konto_id
"""


def list_buchungen(
    year: int | None = None,
    month: int | None = None,
    konto_id: int | None = None,
    kategorie_id: int | None = None,
    typ: str | None = None,
    suche: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if year:
        where.append("strftime('%Y', b.datum) = ?")
        params.append(f"{int(year):04d}")
    if month:
        where.append("strftime('%m', b.datum) = ?")
        params.append(f"{int(month):02d}")
    if konto_id:
        where.append("b.konto_id = ?")
        params.append(int(konto_id))
    if kategorie_id:
        where.append("b.kategorie_id = ?")
        params.append(int(kategorie_id))
    if typ in ("einnahme", "ausgabe"):
        where.append("b.typ = ?")
        params.append(typ)
    if suche:
        where.append("(b.beschreibung LIKE ? OR b.notiz LIKE ? OR b.gegen_iban LIKE ?)")
        like = f"%{suche.strip()}%"
        params.extend([like, like, like])

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    rows = db.query(
        f"{BUCHUNG_SELECT} {where_sql} ORDER BY b.datum DESC, b.id DESC LIMIT ? OFFSET ?",
        params + [max(1, min(limit, 2000)), max(0, offset)],
    )
    return [dict(r) for r in rows]


def count_buchungen(**filters: Any) -> int:
    where: list[str] = []
    params: list[Any] = []
    year, month = filters.get("year"), filters.get("month")
    if year:
        where.append("strftime('%Y', datum) = ?")
        params.append(f"{int(year):04d}")
    if month:
        where.append("strftime('%m', datum) = ?")
        params.append(f"{int(month):02d}")
    if filters.get("typ") in ("einnahme", "ausgabe"):
        where.append("typ = ?")
        params.append(filters["typ"])
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    row = db.query_one(f"SELECT COUNT(*) AS n FROM buchungen {where_sql}", params)
    return int(row["n"]) if row else 0


def get_buchung(buchung_id: int) -> dict[str, Any] | None:
    row = db.query_one(f"{BUCHUNG_SELECT} WHERE b.id = ?", (buchung_id,))
    return dict(row) if row else None


def create_buchung(data: dict[str, Any]) -> int:
    kategorie_id = data.get("kategorie_id") or auto_kategorisieren(data.get("beschreibung", ""))
    konto_id = data.get("konto_id") or None
    typ = "einnahme" if str(data.get("typ", "ausgabe")).startswith("ein") else "ausgabe"
    betrag = abs(money(data.get("betrag", 0)))
    cur = db.execute(
        """
        INSERT INTO buchungen
            (datum, betrag, typ, beschreibung, kategorie_id, konto_id,
             gegen_iban, art, notiz, beleg_name, manually_edit)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            data["datum"], betrag, typ, (data.get("beschreibung") or "").strip(),
            kategorie_id, konto_id, (data.get("gegen_iban") or "").strip(),
            data.get("art", "Manuell"), (data.get("notiz") or "").strip(),
            data.get("beleg_name", ""), 1 if data.get("manually_edit") else 0,
        ),
    )
    return int(cur.lastrowid or 0)


def update_buchung(buchung_id: int, data: dict[str, Any]) -> None:
    typ = "einnahme" if str(data.get("typ", "ausgabe")).startswith("ein") else "ausgabe"
    db.execute(
        """
        UPDATE buchungen
        SET datum=?, betrag=?, typ=?, beschreibung=?, kategorie_id=?, konto_id=?,
            gegen_iban=?, notiz=?, art=?, manually_edit=?
        WHERE id=?
        """,
        (
            data["datum"], abs(money(data.get("betrag", 0))), typ,
            (data.get("beschreibung") or "").strip(), data.get("kategorie_id"),
            data.get("konto_id"), (data.get("gegen_iban") or "").strip(),
            (data.get("notiz") or "").strip(), data.get("art", "Manuell"),
            1 if data.get("manually_edit") else 0, buchung_id,
        ),
    )


def delete_buchung(buchung_id: int) -> None:
    db.execute("DELETE FROM buchungen WHERE id=?", (buchung_id,))


# --------------------------------------------------------------------------- #
# Statistik
# --------------------------------------------------------------------------- #
def _year_range(year: int | None, month: int | None) -> tuple[str, str]:
    """Liefert (start, end) als ISO-Datums-Grenzen für den Filter."""
    if year and month:
        return (f"{int(year):04d}-{int(month):02d}-01", f"{int(year):04d}-{int(month):02d}-31")
    if year:
        return (f"{int(year):04d}-01-01", f"{int(year):04d}-12-31")
    return ("1970-01-01", "2999-12-31")


def _filter_sql(year: int | None, month: int | None, alias: str = "", prefix: str = " AND ") -> str:
    parts = []
    if year:
        parts.append(f"strftime('%Y', {alias}datum) = {int(year):04d}")
    if month:
        parts.append(f"strftime('%m', {alias}datum) = {int(month):02d}")
    return prefix + " AND ".join(parts) if parts else ""


def dashboard(year: int | None = None, month: int | None = None) -> dict[str, Any]:
    start, end = _year_range(year, month)
    totals = db.query_one(
        """
        SELECT
          COALESCE(SUM(CASE WHEN typ='einnahme' THEN betrag ELSE 0 END),0) AS einnahmen,
          COALESCE(SUM(CASE WHEN typ='ausgabe'  THEN betrag ELSE 0 END),0) AS ausgaben,
          COUNT(*) AS anzahl
        FROM buchungen WHERE datum >= ? AND datum <= ?
        """,
        (start, end),
    ) or {}
    totals = dict(totals)

    konten = [
        {"id": k["id"], "name": k["name"], "saldo": k["saldo"], "anzahl": k["anzahl"]}
        for k in list_konten()
    ]
    saldo_konten = money(sum(k["saldo"] for k in konten))

    kategorien = [
        {
            "id": r["id"], "name": r["name"], "icon": r["icon"], "farbe": r["farbe"],
            "einnahmen": money(r["einnahmen"]), "ausgaben": money(r["ausgaben"]),
        }
        for r in db.query(
            """
            SELECT ka.id, ka.name, ka.icon, ka.farbe,
                   COALESCE(SUM(CASE WHEN b.typ='einnahme' THEN b.betrag ELSE 0 END),0) AS einnahmen,
                   COALESCE(SUM(CASE WHEN b.typ='ausgabe'  THEN b.betrag ELSE 0 END),0) AS ausgaben
            FROM kategorien ka
            LEFT JOIN buchungen b ON b.kategorie_id = ka.id AND b.datum >= ? AND b.datum <= ?
            GROUP BY ka.id
            HAVING einnahmen != 0 OR ausgaben != 0
            ORDER BY ausgaben DESC
            """,
            (start, end),
        )
    ]

    monthly = [
        {
            "monat": r["monat"],
            "einnahmen": money(r["einnahmen"]),
            "ausgaben": money(r["ausgaben"]),
        }
        for r in db.query(
            """
            SELECT substr(datum,1,7) AS monat,
                   COALESCE(SUM(CASE WHEN typ='einnahme' THEN betrag ELSE 0 END),0) AS einnahmen,
                   COALESCE(SUM(CASE WHEN typ='ausgabe'  THEN betrag ELSE 0 END),0) AS ausgaben
            FROM buchungen
            GROUP BY monat ORDER BY monat DESC LIMIT 12
            """
        )
    ]
    monthly.reverse()

    top_empfaenger = [
        {"name": r["empfaenger"], "summe": money(r["summe"]), "anzahl": r["anzahl"]}
        for r in db.query(
            f"""
            SELECT COALESCE(NULLIF(gegen_iban,''), 'Unbekannt') AS empfaenger,
                   SUM(betrag) AS summe, COUNT(*) AS anzahl
            FROM buchungen
            WHERE typ = 'ausgabe' AND datum >= ? AND datum <= ?
            GROUP BY empfaenger ORDER BY summe DESC LIMIT 8
            """,
            (start, end),
        )
    ]

    einnahmen = money(totals.get("einnahmen", 0))
    ausgaben = money(totals.get("ausgaben", 0))
    return {
        "einnahmen": einnahmen,
        "ausgaben": ausgaben,
        "ueberschuss": money(einnahmen - ausgaben),
        "anzahl": int(totals.get("anzahl", 0) or 0),
        "saldo_konten": saldo_konten,
        "sparquote": round((einnahmen - ausgaben) / einnahmen * 100, 1) if einnahmen else 0.0,
        "kategorien": kategorien,
        "monatsverlauf": monthly,
        "top_empfaenger": top_empfaenger,
        "konten": konten,
    }


def analyse(year: int, compare_year: int | None = None, month: int | None = None) -> dict[str, Any]:
    """Gegenüberstellung zweier Jahre inkl. Sparquote und Monatsreihen."""
    def _block(y: int) -> dict[str, Any]:
        w, p = month_filters(y, month)
        row = db.query_one(
            f"""
            SELECT COALESCE(SUM(CASE WHEN typ='einnahme' THEN betrag ELSE 0 END),0) AS einnahmen,
                   COALESCE(SUM(CASE WHEN typ='ausgabe'  THEN betrag ELSE 0 END),0) AS ausgaben,
                   COUNT(*) AS anzahl
            FROM buchungen {'WHERE ' + w if w else ''}
            """,
            p,
        ) or {}
        row = dict(row)
        einnahmen = money(row.get("einnahmen", 0))
        ausgaben = money(row.get("ausgaben", 0))
        kat_rows = db.query(
            f"""
            SELECT ka.name, ka.icon, ka.farbe,
                   COALESCE(SUM(CASE WHEN b.typ='einnahme' THEN b.betrag ELSE 0 END),0) AS einnahmen,
                   COALESCE(SUM(CASE WHEN b.typ='ausgabe'  THEN b.betrag ELSE 0 END),0) AS ausgaben
            FROM buchungen b JOIN kategorien ka ON ka.id = b.kategorie_id
            {'WHERE ' + w if w else ''}
            GROUP BY b.kategorie_id ORDER BY ausgaben DESC
            """,
            p,
        )
        monate = db.query(
            f"""
            SELECT strftime('%m', datum) AS monat,
                   COALESCE(SUM(CASE WHEN typ='einnahme' THEN betrag ELSE 0 END),0) AS einnahmen,
                   COALESCE(SUM(CASE WHEN typ='ausgabe'  THEN betrag ELSE 0 END),0) AS ausgaben
            FROM buchungen
            {'WHERE ' + w if w else ''}
            GROUP BY monat ORDER BY monat
            """,
            p,
        )
        return {
            "einnahmen": einnahmen,
            "ausgaben": ausgaben,
            "ueberschuss": money(einnahmen - ausgaben),
            "anzahl": int(row.get("anzahl", 0) or 0),
            "sparquote": round((einnahmen - ausgaben) / einnahmen * 100, 1) if einnahmen else 0.0,
            "kategorien": [
                {"name": r["name"], "icon": r["icon"], "farbe": r["farbe"],
                 "einnahmen": money(r["einnahmen"]), "ausgaben": money(r["ausgaben"])}
                for r in kat_rows
            ],
            "monate": [
                {"monat": int(r["monat"]), "einnahmen": money(r["einnahmen"]),
                 "ausgaben": money(r["ausgaben"])}
                for r in monate
            ],
        }

    current = _block(year)
    previous = _block(compare_year) if compare_year else None
    deltas: dict[str, float] = {}
    if previous:
        for key in ("einnahmen", "ausgaben", "ueberschuss"):
            deltas[key] = money(current[key] - previous[key])
            base = previous[key]
            deltas[f"{key}_pct"] = (
                round((current[key] - base) / abs(base) * 100, 1) if base else 0.0
            )
        deltas["sparquote"] = round(current["sparquote"] - previous["sparquote"], 1)
    return {"current": current, "previous": previous, "deltas": deltas}


def zuordnung_vorschlaege(kategorie_id: int) -> list[str]:
    rows = db.query(
        """
        SELECT b.beschreibung, COUNT(*) AS n FROM buchungen b
        WHERE b.kategorie_id = ? AND b.beschreibung != ''
        GROUP BY b.beschreibung ORDER BY n DESC LIMIT 25
        """,
        (kategorie_id,),
    )
    return [r["beschreibung"] for r in rows]


def bulk_kategorisieren(kategorie_id: int, suchbegriff: str) -> int:
    cur = db.execute(
        "UPDATE buchungen SET kategorie_id=?, manually_edit=1 WHERE beschreibung LIKE ?",
        (kategorie_id, f"%{suchbegriff}%"),
    )
    return int(cur.rowcount or 0)


def reset_demodaten() -> None:
    """Löscht alle Buchungen (nicht Konten/Kategorien)."""
    db.execute("DELETE FROM buchungen")


def seed_demo() -> int:
    """Legt eine kleine Beispiel-Buchungsliste an (für Tests/Demo)."""
    import random
    from datetime import date, timedelta

    random.seed(7)
    konten = list_konten()
    if not konten:
        konto_id = save_konto({"name": "Girokonto", "beschreibung": "Hauptkonto", "iban": "DE00 0000 0000 0000 0000 00"})
        konto_id2 = save_konto({"name": "Sparkonto", "beschreibung": "Tagesgeld", "iban": ""})
    else:
        konto_id = konten[0]["id"]
        konto_id2 = konten[min(1, len(konten) - 1)]["id"]
    today = date.today()
    for offset in range(0, 75, 3):
        day = today - timedelta(days=offset)
        if random.random() < 0.85:
            create_buchung({
                "datum": day.isoformat(),
                "betrag": f"{random.uniform(8, 85):.2f}",
                "typ": "ausgabe",
                "beschreibung": random.choice(["REWE SAGT DANKE", "EDEKA Center", "Shell Tankstelle", "Netflix", "Restaurant Zur Mühle"]),
                "konto_id": konto_id,
                "gegen_iban": random.choice(["DE02 3006 0000 0000 1111 11", "DE11 1001 0000 0000 2222 22", ""]),
                "art": "CSV-Import",
            })
        if random.random() < 0.22:
            create_buchung({
                "datum": day.isoformat(),
                "betrag": f"{random.uniform(950, 2400):.2f}",
                "typ": "einnahme",
                "beschreibung": "Arbeitgeber Gehalt",
                "konto_id": konto_id,
                "art": "CSV-Import",
            })
        if random.random() < 0.08:
            create_buchung({
                "datum": day.isoformat(),
                "betrag": f"{random.uniform(20, 200):.2f}",
                "typ": "einnahme",
                "beschreibung": "Erstattung Krankenkasse",
                "konto_id": konto_id2,
                "art": "Manuell",
            })
    return int(db.query_one('SELECT COUNT(*) AS n FROM buchungen')['n'])
