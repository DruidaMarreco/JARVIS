from __future__ import annotations

import asyncio

from fastapi import APIRouter

from ..services import github, heyclaude, todoist

router = APIRouter()


@router.get("/status")
async def get_status() -> list[dict]:
    results = await asyncio.gather(
        heyclaude.check(),
        todoist.check(),
        github.check(),
    )
    return list(results)
