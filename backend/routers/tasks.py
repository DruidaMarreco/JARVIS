from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import todoist

router = APIRouter()


class TaskRequest(BaseModel):
    content: str
    due_string: str = "today"


@router.post("/tasks")
async def create_task(req: TaskRequest) -> dict:
    """Create a Todoist task directly from JARVIS without routing through Hey Claude."""
    return await todoist.create_task(req.content, req.due_string)
