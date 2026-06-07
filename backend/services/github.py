from __future__ import annotations

import logging
import os

import httpx

_API = "https://api.github.com"
_HEADERS = {"Accept": "application/vnd.github.v3+json"}
_log = logging.getLogger(__name__)


def _username() -> str:
    return os.getenv("GITHUB_USERNAME", "DruidaMarreco").strip()


async def check() -> dict:
    """Status chip — shows open PR count (more actionable than public repo count)."""
    username = _username()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_API}/search/issues",
                headers=_HEADERS,
                params={"q": f"is:pr is:open author:{username}"},
            )
            r.raise_for_status()
            count = r.json().get("total_count", "?")
            noun = "PR" if count == 1 else "PRs"
            return {"label": "GitHub", "state": "ok", "detail": f"{count} open {noun}"}
    except httpx.HTTPStatusError as exc:
        return {"label": "GitHub", "state": "warn", "detail": f"HTTP {exc.response.status_code}"}
    except Exception as exc:
        _log.warning("github.check() failed: %s", exc)
        return {"label": "GitHub", "state": "warn", "detail": str(exc)[:60]}


async def open_prs(limit: int = 10) -> list[dict]:
    """Return open PRs authored by the configured user, most recently updated first.

    Each item: {number, title, repo, url, updated_at}.
    Returns an empty list on any failure.
    """
    username = _username()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_API}/search/issues",
                headers=_HEADERS,
                params={
                    "q": f"is:pr is:open author:{username}",
                    "per_page": min(limit, 30),
                    "sort": "updated",
                    "order": "desc",
                },
            )
            r.raise_for_status()
            items = r.json().get("items", [])
            result = []
            for item in items[:limit]:
                repo_url = item.get("repository_url", "")
                repo = repo_url.rsplit("/", 1)[-1] if repo_url else "?"
                result.append({
                    "number": item.get("number"),
                    "title": item.get("title", ""),
                    "repo": repo,
                    "url": item.get("html_url", ""),
                    "updated_at": (item.get("updated_at") or "")[:10],
                })
            return result
    except Exception as exc:
        _log.warning("github.open_prs() failed: %s", exc)
        return []


async def recent_activity(limit: int = 3) -> list[str]:
    """Return a compact list of recent GitHub activity strings (push/PR events).

    Uses the public events API — no token required. Returns an empty list on any
    failure so callers can include it unconditionally.
    """
    username = _username()
    if not username:
        return []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_API}/users/{username}/events/public",
                headers=_HEADERS,
            )
            r.raise_for_status()
            items: list[str] = []
            seen_repos: set[str] = set()
            for ev in r.json():
                ev_type = ev.get("type", "")
                repo = ev.get("repo", {}).get("name", "").split("/", 1)[-1]
                payload = ev.get("payload", {})

                if ev_type == "PushEvent" and repo not in seen_repos:
                    n = len(payload.get("commits", []))
                    noun = "commit" if n == 1 else "commits"
                    items.append(f"{n} {noun} → {repo}")
                    seen_repos.add(repo)

                elif ev_type == "PullRequestEvent":
                    action = payload.get("action", "")
                    title = payload.get("pull_request", {}).get("title", "")
                    if action in ("opened", "closed", "merged") and title:
                        short = title[:40] + ("…" if len(title) > 40 else "")
                        items.append(f"PR {action}: {short}")

                if len(items) >= limit:
                    break
            return items
    except Exception:
        return []
