"""Personal context gatherer — the RAG retrieval step.

Assembles a compact context block from live personal data sources and
returns it as a string to prepend to the user's query. Hey Claude then
sees the full context before generating its reply.

Current sources (all fetched in parallel):
  - Current timestamp, day of week, and weather
  - Today's Todoist tasks (requires TODOIST_API_TOKEN)
  - Recent GitHub activity (public events API, no token needed)

Conversation history is handled separately by format_history() so that
the caller can decide whether to include it independently of the
use_context toggle.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from . import github, todoist, weather


async def gather() -> str:
    """Return a context block to prepend to the user's query.

    All remote calls are fanned out in parallel — gather() latency equals
    the slowest single source, not the sum.
    """
    now = datetime.now()

    task_list, gh_activity, weather_str = await asyncio.gather(
        todoist.tasks(),
        github.recent_activity(),
        weather.current(),
    )

    # Header line — timestamp + weather when available
    header = f"[Context · {now.strftime('%A %d %b %Y · %H:%M')}"
    if weather_str:
        header += f" · {weather_str}"
    header += "]"

    lines: list[str] = [header]

    if task_list:
        names = [t.get("content", "untitled") for t in task_list]
        shown = names[:10]
        suffix = f" (+{len(names) - 10} more)" if len(names) > 10 else ""
        lines.append(f"Today's tasks ({len(names)}): {' · '.join(shown)}{suffix}")
    else:
        lines.append("No Todoist tasks available.")

    if gh_activity:
        lines.append(f"Recent GitHub: {' · '.join(gh_activity)}")

    return "\n".join(lines)


def format_history(history: list[dict]) -> str:
    """Serialise conversation history to a plain-text block.

    history — list of {role, content} dicts (user/assistant turns).
    Returns an empty string when history is empty so callers can gate on it.
    """
    if not history:
        return ""
    lines = ["[Prior conversation]"]
    for turn in history:
        role = "You" if turn.get("role") == "user" else "Claude"
        lines.append(f"{role}: {turn.get('content', '')}")
    return "\n".join(lines)


def augment(query: str, context: str) -> str:
    """Prepend the context block to the query with a clear separator."""
    if not context.strip():
        return query
    return f"{context}\n---\n{query}"
