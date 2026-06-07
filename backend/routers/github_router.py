from __future__ import annotations

from fastapi import APIRouter

from ..services import github

router = APIRouter()


@router.get("/prs")
async def get_open_prs() -> dict:
    """Return open PRs authored by the configured GitHub user."""
    prs = await github.open_prs()
    return {"prs": prs, "count": len(prs)}
