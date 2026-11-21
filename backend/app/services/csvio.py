"""Bank-CSV-Parser ( Nachbau von utils/csv_parser.py , aber ohne pandas ).

Unterstützt die gängigen deutschen Bank-Exportformate (CSV mit Semikolon/Komma,
Header-Zeile variabel, Datumsformate DD.MM.YYYY / YYYY-MM-DD, Beträge 1.234,56).
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

DATE_FORMATS = (
    "%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y",
    "%d/%m/%y", "%Y/%m/%d", "%d-%m-%Y", "%d-%m-%y",
)

COLUMN_MAPPINGS: dict[str, list[str]] = {
    "datum": ["buchungsdatum", "datum", "buchungstag", "wertstellung",
              "valutadatum", "date", "transaction date"],
    "betrag": ["betrag (€)", "betrag", "umsatz", "amount", "betrag in eur",
               "betrag in €", "value"],
    "typ": ["typ", "sparte", "spart", "soll/haben", "verkehrter zeichen",
            "vorzeichen", "transaction type"],
    "beschreibung": ["beschreibung", "verwendungszweck", "verwendungszweck/zweck",
                     "buchungstext", "buchungstext/verwendungszweck", "text", "zweck",
                     "description", "memo", "reference", "details", "bemerkung"],
    "empfaenger": ["zahlungsempfänger*in", "zahlungsempfänger", "empfänger",
                   "empfänger*in", "auftraggeber", "begünstigter", "name",
                   "payee", "recipient"],
    "iban": ["gegen-iban", "gegeniban", "iban", "gegenkonto", "kontonummer",
             "empfänger iban", "account"],
    "kategorie": ["kategorie", "category"],
    "konto": ["konto", "eigenes konto", "von konto"],
    "art": ["umsatztyp", "art", "buchungsart"],
    "notiz": ["notiz", "bemerkung", "note"],
}


HEADER_KEYWORDS = (
    "buchungsdatum", "datum", "betrag", "empfänger", "verwendungszweck",
    "date", "amount", "payee", "description", "umsatz", "saldo",
    "beschreibung", "kategorie", "konto", "typ", "notiz",
)


def parse_amount(raw: str) -> float:
    """Parst 1.234,56 / 1,234.56 / -85,40 / 1234.56 zu float."""
    if raw is None:
        return 0.0
    text = str(raw).strip()
    if not text:
        return 0.0
    text = re.sub(r"[€$£\s]", "", text)
    text = text.replace("\u00a0", "")
    if not text:
        return 0.0
    negative = text.startswith("-") or text.startswith("(") or text.endswith("-")
    text = text.lstrip("-(").rstrip(")").rstrip("-")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        head, _, tail = text.partition(",")
        text = f"{head}.{tail}" if len(tail) <= 2 else head + tail
    try:
        value = float(text)
    except ValueError:
        return 0.0
    return -value if negative else value


def parse_date(raw: str) -> str | None:
    """Parst ein Datum in ISO (YYYY-MM-DD) oder liefert None."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    text = text[:10] if len(text) >= 10 else text
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _detect_delimiter(sample: str) -> str:
    counts = {d: sample.count(d) for d in (";", ",", "\t", "|")}
    best = max(counts.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else ";"


@dataclass
class ParsedRow:
    datum: str
    betrag: float
    beschreibung: str
    empfaenger: str = ""
    verwendungszweck: str = ""
    gegen_iban: str = ""
    art: str = ""
    konto: str = ""
    typ: str = ""            # "einnahme" / "ausgabe" / "" (aus Spalte "Typ", falls vorhanden)


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    eigene_iban: str = ""
    delimiter: str = ";"
    mapping: dict[str, str] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.rows)


def _norm(name: str) -> str:
    return name.strip().lower().lstrip("\ufeff")


def find_mapping(columns: Iterable[str]) -> dict[str, str]:
    """Ordnet CSV-Spalten den internen Feldern zu.

    Priorität: exakter Treffer (normalisiert) vor Teiltreffer. Jede Spalte wird
    nur einmal vergeben, damit z. B. "Beschreibung" nicht als Empfänger durchgeht.
    """
    cols = [(orig, _norm(orig)) for orig in columns]
    mapping: dict[str, str] = {}
    belegt: set[str] = set()

    def zuordnen(cand: str, teils: bool) -> str | None:
        for orig, low in cols:
            if orig in belegt:
                continue
            if low == cand or (teils and cand in low):
                return orig
        return None

    # Zuerst die Felder mit den spezifischsten Kandidaten, damit generische
    # Namen ("Text", "Name") nicht die eigentliche Beschreibung schlucken.
    reihenfolge = ["datum", "betrag", "typ", "beschreibung", "empfaenger",
                   "iban", "kategorie", "konto", "art", "notiz"]
    for internal in reihenfolge:
        for cand in COLUMN_MAPPINGS.get(internal, []):
            hit = zuordnen(cand, teils=False)
            if hit:
                mapping[internal] = hit
                belegt.add(hit)
                break
    for internal in reihenfolge:
        if internal in mapping:
            continue
        for cand in COLUMN_MAPPINGS.get(internal, []):
            hit = zuordnen(cand, teils=True)
            if hit:
                mapping[internal] = hit
                belegt.add(hit)
                break
    return mapping


def parse_date(raw: str) -> str | None:
    """Parst ein Datum in ISO (YYYY-MM-DD) oder liefert None."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    text = text[:10] if len(text) >= 10 else text
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _detect_delimiter(sample: str) -> str:
    counts = {d: sample.count(d) for d in (";", ",", "\t", "|")}
    best = max(counts.items(), key=lambda kv: kv[1])
    return best[0] if best[1] > 0 else ";"


@dataclass
class ParsedRow:
    datum: str
    betrag: float
    beschreibung: str
    empfaenger: str = ""
    verwendungszweck: str = ""
    gegen_iban: str = ""
    art: str = ""
    konto: str = ""
    typ: str = ""            # "einnahme" / "ausgabe" / "" (aus Spalte "Typ", falls vorhanden)


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    eigene_iban: str = ""
    delimiter: str = ";"
    mapping: dict[str, str] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.rows)


def _norm(name: str) -> str:
    return name.strip().lower().lstrip("\ufeff")


def find_mapping(columns: Iterable[str]) -> dict[str, str]:
    """Ordnet die CSV-Spalten den internen Feldern zu – exakte Treffer vor Teiltreffern."""
    cols = [(c, _norm(c)) for c in columns]
    mapping: dict[str, str] = {}
    belegt: set[str] = set()
    # Runde 1: exakt (case-insensitiv)
    for internal, candidates in COLUMN_MAPPINGS.items():
        for cand in candidates:
            hit = next((orig for orig, low in cols if low == cand and orig not in belegt), None)
            if hit is not None:
                mapping[internal] = hit
                belegt.add(hit)
                break
    # Runde 2: Teiltreffer
    for internal, candidates in COLUMN_MAPPINGS.items():
        if internal in mapping:
            continue
        for cand in candidates:
            hit = next((orig for orig, low in cols if cand in low and orig not in belegt), None)
            if hit is not None:
                mapping[internal] = hit
                belegt.add(hit)
                break
    return mapping


def parse_csv_text(text: str, delimiter: str | None = None) -> ParseResult:
    """Parst CSV-Text (mit/ohne Header) in Buchungszeilen."""
    lines = text.splitlines()
    if not lines:
        return ParseResult()

    if delimiter is None:
        delimiter = _detect_delimiter("\n".join(lines[:10]))

    header_idx = 0
    best_score = 0
    for idx, line in enumerate(lines[:25]):
        score = sum(1 for kw in HEADER_KEYWORDS if kw in line.lower())
        if score > best_score:
            best_score, header_idx = score, idx
    if best_score < 2:
        header_idx = -1

    if header_idx >= 0:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)
        columns = rows[header_idx]
        data_rows = rows[header_idx + 1:]
    else:
        columns = []
        data_rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))

    mapping = find_mapping(columns) if columns else {}
    col_index = {col: idx for idx, col in enumerate(columns)}
    result = ParseResult(delimiter=delimiter, mapping=mapping)

    iban_re = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
    for line in lines[:20]:
        low = line.lower()
        if any(k in low for k in ("girokonto", "iban", "kontonummer", "account")):
            hit = iban_re.search(line.upper())
            if hit:
                result.eigene_iban = hit.group(0)
                break

    for raw in data_rows:
        if not any(c.strip() for c in raw):
            continue
        if not mapping:
            # Fallback: Spaltenreihenfolge Datum;Betrag;Beschreibung
            if len(raw) < 2:
                result.skipped.append(";".join(raw))
                continue
            datum = parse_date(raw[0])
            betrag = parse_amount(raw[1])
            beschreibung = raw[2] if len(raw) > 2 else ""
            if datum is None or betrag == 0.0:
                result.skipped.append(";".join(raw))
                continue
            result.rows.append(ParsedRow(datum=datum, betrag=betrag, beschreibung=beschreibung))
            continue

        def cell(name: str) -> str:
            col = mapping.get(name)
            if not col:
                return ""
            idx = col_index.get(col)
            if idx is None or idx >= len(raw):
                return ""
            return raw[idx].strip()

        datum = parse_date(cell("datum"))
        betrag = parse_amount(cell("betrag"))
        if datum is None or betrag == 0.0:
            result.skipped.append(";".join(raw))
            continue

        typ_spalte = cell("typ").strip()
        if typ_spalte:
            niedrig = typ_spalte.lower()
            if any(k in niedrig for k in ("einnahme", "income", "credit", "hab", "zu")):
                betrag = abs(betrag)
            elif any(k in niedrig for k in ("ausgabe", "expense", "debit", "soll", "ab")):
                betrag = -abs(betrag)

        empfaenger = cell("empfaenger")
        beschreibung = cell("beschreibung")
        notiz = cell("notiz")
        if not beschreibung:
            beschreibung = " ".join(p for p in (empfaenger, notiz) if p).strip()
        if not beschreibung:
            beschreibung = "Ohne Beschreibung"
        result.rows.append(
            ParsedRow(
                datum=datum,
                betrag=betrag,
                beschreibung=beschreibung,
                empfaenger=empfaenger,
                verwendungszweck=notiz,
                gegen_iban=cell("iban"),
                art=cell("art"),
                konto=cell("konto") or result.eigene_iban,
                typ="einnahme" if betrag > 0 else "ausgabe",
            )
        )
    return result