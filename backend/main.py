from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

from .routers import dispatch, github_router, ollama_router, status, tasks  # noqa: E402

FRONTEND = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="JARVIS")
app.include_router(status.router, prefix="/api")
app.include_router(dispatch.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(github_router.router, prefix="/api")
app.include_router(ollama_router.router, prefix="/api")


@app.get("/healthz")
def healthz() -> dict:
    """Liveness probe — returns 200 OK when the server is up."""
    return {"status": "ok"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


def main() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=7000, reload=True)
