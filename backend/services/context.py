"""Personal context gatherer — the RAG retrieval step.

Assembles a compact context block from live personal data sources and
returns it as a string to prepend to the user's query. Hey Claude then
sees the full context before generating its reply.

Currently sources:
  - Current timestamp and day of week
  - Today's Todoist tasks (requires TODOIST_API_TOKEN)

Add a new source by appending an async call here. The block format is
intentionally terse so it doesn't eat into the model's reply budget.
"""

from __future__ import annotations

from datetime import datetime

from . import todoist


async def gather() -> str:
    """Return a context block to prepend to the user's query.

    Returns an empty string when no context can be gathered (e.g. no
    Todoist token), so callers can safely include it unconditionally.
    """
    now = datetime.now()
    lines: list[str] = [
        f"[Context · {now.strftime('%A %d %b %Y · %H:%M')}]",
    ]

    task_list = await todoist.tasks()
    if task_list:
        names = [t.get("content", "untitled") for t in task_list]
        # Cap at 10 so we don't flood the context window
        shown = names[:10]
        suffix = f" (+{len(names) - 10} more)" if len(names) > 10 else ""
        lines.append(f"Today's tasks ({len(names)}): {' · '.join(shown)}{suffix}")
    else:
        lines.append("No Todoist tasks available.")

    return "\n".join(lines)


def augment(query: str, context: str) -> str:
    """Prepend the context block to the query with a clear separator."""
    if not context.strip():
        return query
    return f"{context}\n---\n{query}"
