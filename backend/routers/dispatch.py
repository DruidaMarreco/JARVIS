from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import context, heyclaude

router = APIRouter()


class DispatchRequest(BaseModel):
    query: str
    mode: str = "default"
    use_context: bool = True


@router.get("/modes")
async def get_modes() -> list[dict]:
    return await heyclaude.modes()


@router.post("/dispatch")
async def dispatch(req: DispatchRequest) -> dict:
    ctx = ""
    if req.use_context:
        ctx = await context.gather()

    augmented = context.augment(req.query, ctx)
    result = await heyclaude.ask(augmented, mode=req.mode)

    # Return the gathered context so the frontend can show what was injected
    return {**result, "context": ctx}
