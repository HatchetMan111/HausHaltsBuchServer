"""Buchungs-Endpunkte (CRUD)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from ..services import importexport, stats

router = APIRouter(prefix="/api/buchungen", tags=["buchungen"])


def _opt_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    return int(value)


@router.get("")
def list_buchungen(
    year: int | None = Query(None),
    month: int | None = Query(None),
    konto_id: int | None = Query(None),
    kategorie_id: int | None = Query(None),
    typ: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    export: bool = Query(False),
):
    if export:
        csv_text = importexport.export_csv(year, month, konto_id)
        fname = f"haushaltsbuch_{year or 'alle'}_{month or 'monate'}.csv"
        return Response(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    buchungen = stats.list_buchungen(
        year=year, month=month, konto_id=konto_id, kategorie_id=kategorie_id,
        typ=typ, suche=q, limit=limit, offset=offset,
    )
    return {
        "buchungen": buchungen,
        "gesamt": stats.count_buchungen(year=year, month=month, typ=typ),
        "limit": limit,
        "offset": offset,
    }


@router.post("")
def create(payload: dict[str, Any]):
    try:
        new_id = stats.create_buchung(payload)
    except KeyError as exc:
        raise HTTPException(422, f"Pflichtfeld fehlt: {exc}") from exc
    return {"id": new_id, "buchung": stats.get_buchung(new_id)}


@router.get("/{buchung_id}")
def detail(buchung_id: int):
    buchung = stats.get_buchung(buchung_id)
    if not buchung:
        raise HTTPException(404, "Buchung nicht gefunden")
    return buchung


@router.put("/{buchung_id}")
def update(buchung_id: int, payload: dict[str, Any]):
    if not stats.get_buchung(buchung_id):
        raise HTTPException(404, "Buchung nicht gefunden")
    stats.update_buchung(buchung_id, payload)
    return {"id": buchung_id, "buchung": stats.get_buchung(buchung_id)}


@router.delete("/{buchung_id}")
def delete(buchung_id: int):
    if not stats.get_buchung(buchung_id):
        raise HTTPException(404, "Buchung nicht gefunden")
    stats.delete_buchung(buchung_id)
    return {"ok": True, "id": buchung_id}


@router.post("/bulk-kategorie")
def bulk_kategorie(payload: dict[str, Any]):
    kat = _opt_int(payload.get("kategorie_id"))
    begriff = (payload.get("suchbegriff") or "").strip()
    if not kat or not begriff:
        raise HTTPException(422, "kategorie_id und suchbegriff sind erforderlich")
    n = stats.bulk_kategorisieren(kat, begriff)
    return {"aktualisiert": n}