from __future__ import annotations

import json
import os

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..services import context, heyclaude, ollama, weather

router = APIRouter()


class DispatchRequest(BaseModel):
    query: str
    mode: str = "default"
    use_context: bool = True
    history: list[dict] = []
    provider: str = "auto"  # "heyclaude" | "ollama" | "auto"


def _ollama_model(req: DispatchRequest) -> str | None:
    """Extract the Ollama model from the request mode field.

    When the frontend sends provider=ollama it puts the chosen model name in
    `mode`.  Return None (use env-var default) when mode is the generic
    'default' sentinel or an empty string.
    """
    return req.mode if req.mode not in ("default", "", None) else None


@router.get("/context")
async def get_context() -> dict:
    """Return the current context block so the UI can preview what Hey Claude will see."""
    ctx = await context.gather()
    return {"context": ctx}


@router.get("/weather")
async def get_weather(
    lat: str | None = Query(default=None, description="Latitude override (e.g. 38.71)"),
    lon: str | None = Query(default=None, description="Longitude override (e.g. -9.14)"),
) -> dict:
    """Return the current weather string from open-meteo.

    Optional ``lat``/``lon`` query params let the frontend pass a user-configured
    location instead of the server-side env-var defaults.
    """
    w = await weather.current(lat=lat, lon=lon)
    return {"weather": w}


@router.get("/modes")
async def get_modes() -> list[dict]:
    return await heyclaude.modes()


@router.post("/dispatch")
async def dispatch(req: DispatchRequest) -> dict:
    # Gather task/timestamp context (respects use_context toggle)
    ctx = await context.gather() if req.use_context else ""

    # History is always threaded in for conversational continuity.
    hist_str = context.format_history(req.history)

    parts = [p for p in [ctx, hist_str] if p]
    full_ctx = "\n\n".join(parts)
    augmented = context.augment(req.query, full_ctx)

    # Route to the requested provider
    if req.provider == "ollama":
        result = await ollama.ask(augmented, model=_ollama_model(req))
    elif req.provider == "heyclaude":
        result = await heyclaude.ask(augmented, mode=req.mode)
    else:
        # auto: try Hey Claude; fall back to Ollama when offline and configured
        result = await heyclaude.ask(augmented, mode=req.mode)
        if result.get("error") == "heyclaude_offline" and os.getenv("OLLAMA_URL"):
            result = await ollama.ask(augmented)

    return {**result, "context": ctx}


@router.post("/stream")
async def stream_dispatch(req: DispatchRequest):
    """Server-Sent Events endpoint for streaming Ollama responses token-by-token."""
    ctx = await context.gather() if req.use_context else ""
    hist_str = context.format_history(req.history)
    parts = [p for p in [ctx, hist_str] if p]
    augmented = context.augment(req.query, "\n\n".join(parts))

    async def generate():
        # Send the context block first so the UI can display it immediately
        yield f"data: {json.dumps({'context': ctx})}\n\n"
        async for chunk in ollama.stream(augmented, model=_ollama_model(req), history=req.history):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
