from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import heyclaude

router = APIRouter()


class DispatchRequest(BaseModel):
    query: str


@router.post("/dispatch")
async def dispatch(req: DispatchRequest) -> dict:
    return await heyclaude.ask(req.query)
