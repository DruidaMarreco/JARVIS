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


@router.get("/github/repos")
async def get_my_repos(
    limit: int = Query(default=8, ge=1, le=20),
) -> dict:
    """Return the configured user's own GitHub repositories."""
    repos = await github.my_repos(limit=limit)
    return {"repos": repos, "count": len(repos)}


@router.get("/github/issues")
async def search_github_issues(
    q: str = Query(description="GitHub issue search query"),
    limit: int = Query(default=8, ge=1, le=20),
) -> dict:
    """Search GitHub issues matching the given query string."""
    issues = await github.search_issues(q, limit=limit)
    return {"issues": issues, "query": q, "count": len(issues)}


@router.get("/github/search")
async def search_github(
    q: str = Query(description="GitHub repository search query"),
    limit: int = Query(default=6, ge=1, le=20),
) -> dict:
    """Search GitHub repositories matching the given query string."""
    repos = await github.search_repos(q, limit=limit)
    return {"repos": repos, "query": q, "count": len(repos)}
