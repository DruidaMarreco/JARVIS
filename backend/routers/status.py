from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter

from ..services import github, heyclaude, ollama, todoist

router = APIRouter()


@router.get("/status")
async def get_status() -> list[dict]:
    checks = [heyclaude.check(), todoist.check(), github.check()]
    # Only probe Ollama when explicitly configured; avoids hitting localhost:11434
    # on machines that don't have it installed.
    if os.getenv("OLLAMA_URL"):
        checks.append(ollama.check())
    results = await asyncio.gather(*checks)
    return list(results)
