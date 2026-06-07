from __future__ import annotations

import os

import httpx

_BASE = "https://api.todoist.com/rest/v2"


def _token() -> str:
    return os.getenv("TODOIST_API_TOKEN", "").strip()


async def tasks() -> list[dict]:
    """Return today's + overdue tasks as raw dicts. Empty list on any failure."""
    token = _token()
    if not token:
        return []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_BASE}/tasks",
                headers={"Authorization": f"Bearer {token}"},
                params={"filter": "today | overdue"},
            )
            r.raise_for_status()
            return r.json()
    except Exception:
        return []


async def check() -> dict:
    """Status chip — raises HTTP/connection errors as warn so they surface in the UI."""
    token = _token()
    if not token:
        return {"label": "Todoist", "state": "idle", "detail": "no token set"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_BASE}/tasks",
                headers={"Authorization": f"Bearer {token}"},
                params={"filter": "today | overdue"},
            )
            r.raise_for_status()
            count = len(r.json())
            noun = "task" if count == 1 else "tasks"
            return {"label": "Todoist", "state": "ok", "detail": f"{count} {noun} today"}
    except httpx.HTTPStatusError as exc:
        return {"label": "Todoist", "state": "warn", "detail": f"HTTP {exc.response.status_code}"}
    except Exception as exc:
        return {"label": "Todoist", "state": "warn", "detail": str(exc)[:60]}
