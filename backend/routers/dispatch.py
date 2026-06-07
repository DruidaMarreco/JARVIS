from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import context, heyclaude

router = APIRouter()


class DispatchRequest(BaseModel):
    query: str
    mode: str = "default"
    use_context: bool = True
    history: list[dict] = []


@router.get("/modes")
async def get_modes() -> list[dict]:
    return await heyclaude.modes()


@router.post("/dispatch")
async def dispatch(req: DispatchRequest) -> dict:
    # Gather task/timestamp context (respects use_context toggle)
    ctx = await context.gather() if req.use_context else ""

    # History is always threaded in for conversational continuity — it's not
    # the same as the "context" toggle (which gates Todoist tasks + timestamp).
    hist_str = context.format_history(req.history)

    # Combine into a single block; each non-empty part separated by a blank line
    parts = [p for p in [ctx, hist_str] if p]
    full_ctx = "\n\n".join(parts)

    augmented = context.augment(req.query, full_ctx)
    result = await heyclaude.ask(augmented, mode=req.mode)

    # Return only the gather context (not history) for the UI context block —
    # the user can already see the history in the conversation thread.
    return {**result, "context": ctx}
