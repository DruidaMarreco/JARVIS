from __future__ import annotations

from fastapi import APIRouter, Query

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


@router.get("/github/search")
async def search_github(
    q: str = Query(description="GitHub repository search query"),
    limit: int = Query(default=6, ge=1, le=20),
) -> dict:
    """Search GitHub repositories matching the given query string."""
    repos = await github.search_repos(q, limit=limit)
    return {"repos": repos, "query": q, "count": len(repos)}
