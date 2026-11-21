"""Startskript für systemd: legt DB an und startet uvicorn."""
from app.main import app
from app.config import HOST, PORT

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")