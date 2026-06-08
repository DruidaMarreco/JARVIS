from __future__ import annotations

from fastapi import APIRouter

from ..services import ollama

router = APIRouter()


@router.get("/ollama/models")
async def get_ollama_models() -> dict:
    """Return locally available Ollama models with name and size."""
    models = await ollama.list_models()
    return {"models": models, "count": len(models)}
