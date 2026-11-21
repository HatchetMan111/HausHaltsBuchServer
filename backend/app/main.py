"""FastAPI-Einstiegspunkt: API + ausgeliefertes React-Frontend (falls gebaut)."""
from __future__ import annotations

import logging
import os


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import HOST, PORT, STATIC_DIR, ensure_dirs
from .db import init_db
from .routers import buchungen, statistik, system, verwaltung

LOG_FILE = "/var/log/haushaltsbuch.log"


def _setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        handlers.append(logging.FileHandler(LOG_FILE))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def _startup() -> None:
    """Einmalige Initialisierung: Logging, Verzeichnisse, Schema, Seed."""
    _setup_logging()
    ensure_dirs()
    init_db()
    logging.getLogger("haushaltsbuch").info(
        "Haushaltsbuch %s gestartet (Datenbank: %s)", __version__, os.environ.get("HAUSHALTSBUCH_DB")
    )


def _shutdown() -> None:
    logging.getLogger("haushaltsbuch").info("Haushaltsbuch fährt herunter.")


app = FastAPI(
    title="Haushaltsbuch",
    version=__version__,
    description="Lokales Haushaltsbuch – CSV-Import, Kategorien, Auswertung. Läuft vollständig offline im LXC.",
    on_startup=[_startup],
    on_shutdown=[_shutdown],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router)
app.include_router(buchungen.router)
app.include_router(statistik.router)
app.include_router(verwaltung.router)


@app.get("/api")
def api_root():
    return {"app": "Haushaltsbuch", "version": __version__, "api": "/api", "docs": "/docs"}


# --------------------------------------------------------------------------- #
# React-Build ausliefern (SPA), sofern vorhanden
# --------------------------------------------------------------------------- #
if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file() and ".." not in full_path:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
else:  # Entwicklungsmodus ohne Build
    @app.get("/")
    def dev_root():
        return JSONResponse({
            "hinweis": "React-Frontend ist nicht gebaut. Entwicklung: cd frontend && npm run dev",
            "api": "/api",
            "version": __version__,
        })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)