"""System-Endpunkte (Version, Log, Health)."""
from __future__ import annotations

import os
import platform
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from .. import __version__
from ..config import DB_PATH

router = APIRouter(prefix="/api", tags=["system"])

START = time.time()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "version": __version__,
        "uptime_sekunden": round(time.time() - START, 1),
        "db": str(DB_PATH),
        "db_vorhanden": Path(DB_PATH).exists(),
    }


@router.get("/system")
def system():
    return {
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "hostname": os.uname().nodename,
        "db_groesse_kb": round(Path(DB_PATH).stat().st_size / 1024, 1) if Path(DB_PATH).exists() else 0,
        "log_pfad": "/var/log/haushaltsbuch.log",
    }


@router.get("/log", response_class=PlainTextResponse)
def log(zeilen: int = 80):
    p = Path("/var/log/haushaltsbuch.log")
    if not p.exists():
        return PlainTextResponse("Keine Logdatei vorhanden.\n")
    lines = p.read_text(errors="ignore").splitlines()
    return PlainTextResponse("\n".join(lines[-max(1, min(zeilen, 500)):]) + "\n")