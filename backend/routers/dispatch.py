from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import context, heyclaude, ollama

router = APIRouter()


class DispatchRequest(BaseModel):
    query: str
    mode: str = "default"
    use_context: bool = True
    history: list[dict] = []
    provider: str = "auto"  # "heyclaude" | "ollama" | "auto"


@router.get("/context")
async def get_context() -> dict:
    """Return the current context block so the UI can preview what Hey Claude will see."""
    ctx = await context.gather()
    return {"context": ctx}


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
        result = await ollama.ask(augmented)
    elif req.provider == "heyclaude":
        result = await heyclaude.ask(augmented, mode=req.mode)
    else:
        # auto: try Hey Claude; fall back to Ollama when offline and configured
        result = await heyclaude.ask(augmented, mode=req.mode)
        if result.get("error") == "heyclaude_offline" and os.getenv("OLLAMA_URL"):
            result = await ollama.ask(augmented)

    return {**result, "context": ctx}
