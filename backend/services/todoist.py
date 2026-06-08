from __future__ import annotations

import logging
import os

import httpx

_BASE = "https://api.todoist.com/rest/v2"
_FILTER = "today | overdue"  # shared filter used by tasks() and check()
_log = logging.getLogger(__name__)


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
                params={"filter": _FILTER},
            )
            r.raise_for_status()
            return r.json()
    except Exception:
        _log.warning("todoist.tasks() failed", exc_info=True)
        return []


async def projects() -> dict[str, str]:
    """Return a mapping of project_id → project_name.

    Used to annotate task lists with human-readable project names.
    Returns an empty dict on any failure so callers can always call it safely.
    """
    token = _token()
    if not token:
        return {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_BASE}/projects",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            return {p["id"]: p.get("name", "?") for p in r.json()}
    except Exception:
        _log.debug("todoist.projects() failed", exc_info=True)
        return {}


async def create_task(content: str, due_string: str = "today") -> dict:
    """Create a task in Todoist.

    Pass ``due_string=""`` to create an inbox task with no due date.
    Returns the created task dict on success, or a dict with an ``error`` key
    on failure so callers never have to handle exceptions.
    """
    token = _token()
    if not token:
        return {"error": "no_token", "detail": "TODOIST_API_TOKEN is not set"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            payload: dict = {"content": content}
            if due_string:  # omit entirely for inbox tasks (no due date)
                payload["due_string"] = due_string
            r = await client.post(
                f"{_BASE}/tasks",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as exc:
        _log.warning("todoist.create_task() HTTP %d", exc.response.status_code)
        return {"error": "http_error", "detail": f"HTTP {exc.response.status_code}"}
    except Exception as exc:
        _log.warning("todoist.create_task() failed: %s", exc)
        return {"error": "request_failed", "detail": str(exc)[:80]}


async def close_task(task_id: str) -> dict:
    """Mark a task as complete.

    Returns ``{"ok": True}`` on success or a dict with an ``error`` key.
    """
    token = _token()
    if not token:
        return {"error": "no_token", "detail": "TODOIST_API_TOKEN is not set"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{_BASE}/tasks/{task_id}/close",
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            return {"ok": True}
    except httpx.HTTPStatusError as exc:
        _log.warning("todoist.close_task(%s) HTTP %d", task_id, exc.response.status_code)
        return {"error": "http_error", "detail": f"HTTP {exc.response.status_code}"}
    except Exception as exc:
        _log.warning("todoist.close_task(%s) failed: %s", task_id, exc)
        return {"error": "request_failed", "detail": str(exc)[:80]}


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
                params={"filter": _FILTER},
            )
            r.raise_for_status()
            count = len(r.json())
            noun = "task" if count == 1 else "tasks"
            return {"label": "Todoist", "state": "ok", "detail": f"{count} {noun} today"}
    except httpx.HTTPStatusError as exc:
        return {"label": "Todoist", "state": "warn", "detail": f"HTTP {exc.response.status_code}"}
    except Exception as exc:
        return {"label": "Todoist", "state": "warn", "detail": str(exc)[:60]}
