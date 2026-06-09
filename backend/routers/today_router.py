from __future__ import annotations

import asyncio
from datetime import date

from fastapi import APIRouter, Query

from ..services import github, todoist
from ..services import weather as weather_svc

router = APIRouter()


@router.get("/today")
async def today_snapshot(
    lat: str | None = Query(default=None),
    lon: str | None = Query(default=None),
) -> dict:
    """Return today's key data in a single aggregated response.

    Fetches tasks, weather, open PRs and recent GitHub events concurrently.
    Any individual service failure returns an empty/default value so the
    endpoint always responds with 200.
    """
    (task_list, project_map), weather_str, prs, events = await asyncio.gather(
        asyncio.gather(todoist.tasks(), todoist.projects()),
        weather_svc.current(lat=lat, lon=lon),
        github.open_prs(limit=5),
        github.recent_events(limit=3),
    )

    today_str = date.today().isoformat()
    overdue = [t for t in task_list if (t.get("due") or {}).get("date", today_str) < today_str]

    return {
        "tasks": [
            {
                "id": t.get("id", ""),
                "content": t.get("content", "untitled"),
                "priority": t.get("priority", 1),
                "due": t.get("due"),
                "project": project_map.get(t.get("project_id", ""), ""),
            }
            for t in task_list
        ],
        "task_count": len(task_list),
        "overdue_count": len(overdue),
        "weather": weather_str,
        "prs": prs,
        "pr_count": len(prs),
        "events": events,
    }
