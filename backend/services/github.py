from __future__ import annotations

import os

import httpx

_API = "https://api.github.com"


async def check() -> dict:
    username = os.getenv("GITHUB_USERNAME", "DruidaMarreco").strip()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(
                f"{_API}/users/{username}",
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            r.raise_for_status()
            data = r.json()
            repos = data.get("public_repos", "?")
            return {"label": "GitHub", "state": "ok", "detail": f"{repos} public repos"}
    except httpx.HTTPStatusError as exc:
        return {"label": "GitHub", "state": "warn", "detail": f"HTTP {exc.response.status_code}"}
    except Exception as exc:
        return {"label": "GitHub", "state": "warn", "detail": str(exc)[:60]}
