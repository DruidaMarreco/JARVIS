from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import todoist

router = APIRouter()


class TaskRequest(BaseModel):
    content: str
    due_string: str = "today"


@router.get("/tasks")
async def list_tasks() -> dict:
    """Return today's + overdue Todoist tasks formatted for the UI."""
    task_list = await todoist.tasks()
    return {
        "tasks": [
            {
                "id": t.get("id", ""),
                "content": t.get("content", "untitled"),
                "priority": t.get("priority", 1),
                "due": t.get("due"),
            }
            for t in task_list
        ],
        "count": len(task_list),
    }


@router.post("/tasks")
async def create_task(req: TaskRequest) -> dict:
    """Create a Todoist task directly from JARVIS without routing through Hey Claude."""
    return await todoist.create_task(req.content, req.due_string)


@router.post("/tasks/{task_id}/close")
async def close_task(task_id: str) -> dict:
    """Mark a Todoist task as complete."""
    return await todoist.close_task(task_id)
