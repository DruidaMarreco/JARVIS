from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import heyclaude

router = APIRouter()


class DispatchRequest(BaseModel):
    query: str
    mode: str = "default"


@router.get("/modes")
async def get_modes() -> list[dict]:
    return await heyclaude.modes()


@router.post("/dispatch")
async def dispatch(req: DispatchRequest) -> dict:
    return await heyclaude.ask(req.query, mode=req.mode)
