from __future__ import annotations

from fastapi import APIRouter

from ..services import github

router = APIRouter()


@router.get("/prs")
async def get_open_prs() -> dict:
    """Return open PRs authored by the configured GitHub user."""
    prs = await github.open_prs()
    return {"prs": prs, "count": len(prs)}


@router.get("/events")
async def get_recent_events() -> dict:
    """Return recent public GitHub activity for the configured user."""
    events = await github.recent_events()
    return {"events": events, "count": len(events)}
