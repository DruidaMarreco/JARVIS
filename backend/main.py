from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse

load_dotenv()

from .routers import dispatch, status  # noqa: E402

FRONTEND = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="JARVIS")
app.include_router(status.router, prefix="/api")
app.include_router(dispatch.router, prefix="/api")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


def main() -> None:
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=7000, reload=True)
