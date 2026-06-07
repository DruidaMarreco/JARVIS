from __future__ import annotations

import os

import httpx

_OFFLINE_REPLY = "Hey Claude is offline. Start it with `hey-claude-web` in the Hey Claude project."


def _url() -> str:
    return os.getenv("HEYCLAUDE_URL", "http://localhost:8000").rstrip("/")


async def check() -> dict:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(_url())
            if r.status_code == 200:
                return {"label": "Hey Claude", "state": "ok", "detail": "running"}
    except Exception:
        pass
    return {"label": "Hey Claude", "state": "idle", "detail": "offline · run hey-claude-web"}


async def ask(query: str, mode: str = "default") -> dict:
    if not query.strip():
        return {"reply": ""}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{_url()}/api/ask", json={"query": query, "mode": mode})
            r.raise_for_status()
            return r.json()
    except Exception:
        return {"reply": _OFFLINE_REPLY, "error": "heyclaude_offline"}


async def modes() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{_url()}/api/modes")
            r.raise_for_status()
            return r.json()
    except Exception:
        return []
