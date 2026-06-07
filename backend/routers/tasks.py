from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from ..services import todoist

router = APIRouter()

_MAX_CONTENT = 500  # Todoist's own limit is ~500 chars


class TaskRequest(BaseModel):
    content: str
    due_string: str = "today"

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content must not be empty or whitespace")
        if len(v) > _MAX_CONTENT:
            raise ValueError(f"content too long (max {_MAX_CONTENT} characters)")
        return v


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
