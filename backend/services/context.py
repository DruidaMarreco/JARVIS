"""Personal context gatherer — the RAG retrieval step.

Assembles a compact context block from live personal data sources and
returns it as a string to prepend to the user's query. Hey Claude then
sees the full context before generating its reply.

Currently sources:
  - Current timestamp and day of week
  - Today's Todoist tasks (requires TODOIST_API_TOKEN)

Conversation history is handled separately by format_history() so that
the caller can decide whether to include it independently of the
use_context toggle.
"""

from __future__ import annotations

from datetime import datetime

from . import todoist


async def gather() -> str:
    """Return a context block (timestamp + tasks) to prepend to the query."""
    now = datetime.now()
    lines: list[str] = [
        f"[Context · {now.strftime('%A %d %b %Y · %H:%M')}]",
    ]

    task_list = await todoist.tasks()
    if task_list:
        names = [t.get("content", "untitled") for t in task_list]
        shown = names[:10]
        suffix = f" (+{len(names) - 10} more)" if len(names) > 10 else ""
        lines.append(f"Today's tasks ({len(names)}): {' · '.join(shown)}{suffix}")
    else:
        lines.append("No Todoist tasks available.")

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
