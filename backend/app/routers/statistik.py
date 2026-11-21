"""Dashboard- und Analyse-Endpunkte."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..services import stats

router = APIRouter(prefix="/api", tags=["statistik"])


@router.get("/dashboard")
def dashboard(year: int | None = Query(None), month: int | None = Query(None)):
    return stats.dashboard(year=year, month=month)


@router.get("/analyse")
def analyse(
    year: int = Query(...),
    compare_year: int | None = Query(None),
    month: int | None = Query(None),
):
    return stats.analyse(year=year, compare_year=compare_year, month=month)


@router.get("/meta")
def meta():
    return {
        "jahre": stats.available_years(),
        "monate": stats.available_months(),
        "version": "1.0.0",
    }