"""Verwaltung: Konten, Kategorien, Schlüsselwörter, Import/Export."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from ..services import importexport, stats

router = APIRouter(prefix="/api", tags=["verwaltung"])


# --------------------------------------------------------------------------- #
# Konten
# --------------------------------------------------------------------------- #
@router.get("/konten")
def konten():
    return stats.list_konten()


@router.post("/konten")
def konto_anlegen(payload: dict[str, Any]):
    if not (payload.get("name") or "").strip():
        raise HTTPException(422, "Name ist erforderlich")
    kid = stats.save_konto(payload)
    return {"id": kid, "konten": stats.list_konten()}


@router.put("/konten/{konto_id}")
def konto_aendern(konto_id: int, payload: dict[str, Any]):
    payload["id"] = konto_id
    stats.save_konto(payload)
    return {"id": konto_id, "konten": stats.list_konten()}


@router.delete("/konten/{konto_id}")
def konto_loeschen(konto_id: int):
    stats.delete_konto(konto_id)
    return {"ok": True, "konten": stats.list_konten()}


# --------------------------------------------------------------------------- #
# Kategorien
# --------------------------------------------------------------------------- #
@router.get("/kategorien")
def kategorien(art: str | None = None):
    return stats.list_kategorien(art=art)


@router.post("/kategorien")
def kategorie_anlegen(payload: dict[str, Any]):
    if not (payload.get("name") or "").strip():
        raise HTTPException(422, "Name ist erforderlich")
    kid = stats.save_kategorie(payload)
    return {"id": kid, "kategorien": stats.list_kategorien()}


@router.put("/kategorien/{kategorie_id}")
def kategorie_aendern(kategorie_id: int, payload: dict[str, Any]):
    payload["id"] = kategorie_id
    stats.save_kategorie(payload)
    return {"id": kategorie_id, "kategorien": stats.list_kategorien()}


@router.delete("/kategorien/{kategorie_id}")
def kategorie_loeschen(kategorie_id: int):
    stats.delete_kategorie(kategorie_id)
    return {"ok": True, "kategorien": stats.list_kategorien()}


@router.get("/kategorien/{kategorie_id}/vorschlaege")
def kategorie_vorschlaege(kategorie_id: int):
    return {"vorschlaege": stats.zuordnung_vorschlaege(kategorie_id)}


# --------------------------------------------------------------------------- #
# Schlüsselwort-Regeln
# --------------------------------------------------------------------------- #
@router.get("/keywords")
def keywords():
    return stats.list_keywords()


@router.post("/keywords")
def keyword_anlegen(payload: dict[str, Any]):
    wort = (payload.get("schluesselwort") or "").strip()
    kat = payload.get("kategorie_id")
    if not wort or not kat:
        raise HTTPException(422, "schluesselwort und kategorie_id sind erforderlich")
    stats.save_keyword(wort, int(kat), payload.get("id"))
    return {"keywords": stats.list_keywords()}


@router.delete("/keywords/{mapping_id}")
def keyword_loeschen(mapping_id: int):
    stats.delete_keyword(mapping_id)
    return {"ok": True, "keywords": stats.list_keywords()}


# --------------------------------------------------------------------------- #
# Import / Export
# --------------------------------------------------------------------------- #
@router.post("/import")
async def import_csv(
    datei: UploadFile = File(...),
    konto_id: int | None = None,
):
    if not datei.filename or not datei.filename.lower().endswith(".csv"):
        raise HTTPException(422, "Nur .csv-Dateien erlaubt")
    raw = await datei.read()
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="ignore")
    return importexport.import_text(text, konto_id=konto_id)


@router.get("/export")
def export(year: int | None = None, month: int | None = None, konto_id: int | None = None):
    csv_text = importexport.export_csv(year=year, month=month, konto_id=konto_id)
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="haushaltsbuch_{year or "alle"}.csv"'
        },
    )


@router.get("/duplikate")
def duplikate():
    return {"duplikate": importexport.duplicates_check()}


@router.post("/demo")
def demo():
    return {"angelegt": stats.seed_demo()}


@router.post("/zuruecksetzen")
def zuruecksetzen(payload: dict[str, Any] | None = None):
    if not (payload or {}).get("bestätigt"):
        raise HTTPException(400, "Bestätigung erforderlich: {'bestätigt': true}")
    stats.reset_demodaten()
    return {"ok": True}