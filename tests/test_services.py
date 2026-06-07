"""Unit tests for individual service functions.

All tests run offline — httpx.AsyncClient is mocked at the class level so
no real network calls are made. asyncio.run() is used instead of a
pytest-asyncio plugin to keep the dev dependency surface minimal.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.services import context, github, heyclaude, todoist


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _response(status: int, json_data) -> httpx.Response:
    """Minimal fake httpx.Response with a dummy request so raise_for_status() works."""
    return httpx.Response(status, json=json_data, request=httpx.Request("GET", "http://test"))


@contextmanager
def _mock_client(method: str, return_value=None, side_effect=None):
    """Patch httpx.AsyncClient so `async with AsyncClient() as c: await c.<method>(...)` works."""
    mock_instance = AsyncMock()
    attr = getattr(mock_instance, method)
    if side_effect is not None:
        attr.side_effect = side_effect
    else:
        attr.return_value = return_value

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    target = f"backend.services.{{}}.httpx.AsyncClient"
    # caller must supply the service name via a keyword
    raise RuntimeError("use _mock_get / _mock_post helpers instead")


def _mock_get(service_module: str, return_value=None, side_effect=None):
    """Return a context manager that patches GET for the given service module."""
    mock_instance = AsyncMock()
    mock_instance.get = AsyncMock(return_value=return_value, side_effect=side_effect)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return patch(f"backend.services.{service_module}.httpx.AsyncClient", return_value=mock_cm)


def _mock_post(service_module: str, return_value=None, side_effect=None):
    """Return a context manager that patches POST for the given service module."""
    mock_instance = AsyncMock()
    mock_instance.post = AsyncMock(return_value=return_value, side_effect=side_effect)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return patch(f"backend.services.{service_module}.httpx.AsyncClient", return_value=mock_cm)


# ---------------------------------------------------------------------------
# todoist
# ---------------------------------------------------------------------------


class TestContextService:
    def test_gather_includes_timestamp(self, monkeypatch):
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        result = asyncio.run(context.gather())
        assert "[Context" in result
        assert "---" not in result  # no tasks section separator expected in augment

    def test_gather_with_tasks(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        tasks = [{"content": "Write tests"}, {"content": "Review PR"}]
        with _mock_get("todoist", return_value=_response(200, tasks)):
            result = asyncio.run(context.gather())
        assert "Write tests" in result
        assert "Review PR" in result
        assert "2" in result

    def test_gather_includes_github_activity(self, monkeypatch):
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        events = [
            {"type": "PushEvent", "repo": {"name": "u/JARVIS"}, "payload": {"commits": [{}]}}
        ]
        with _mock_get("github", return_value=_response(200, events)):
            result = asyncio.run(context.gather())
        assert "Recent GitHub" in result
        assert "JARVIS" in result

    def test_gather_caps_at_ten_tasks(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        tasks = [{"content": f"Task {i}"} for i in range(15)]
        with _mock_get("todoist", return_value=_response(200, tasks)):
            result = asyncio.run(context.gather())
        assert "+5 more" in result

    def test_augment_prepends_context(self):
        result = context.augment("What should I focus on?", "[Context · Mon]\nTask A")
        assert result.startswith("[Context")
        assert "---" in result
        assert "What should I focus on?" in result

    def test_augment_empty_context_returns_query_unchanged(self):
        assert context.augment("hello", "") == "hello"
        assert context.augment("hello", "   ") == "hello"

    def test_format_history_empty_returns_empty_string(self):
        assert context.format_history([]) == ""

    def test_format_history_labels_roles_correctly(self):
        history = [
            {"role": "user", "content": "What should I do?"},
            {"role": "assistant", "content": "Focus on Task A."},
        ]
        result = context.format_history(history)
        assert "[Prior conversation]" in result
        assert "You: What should I do?" in result
        assert "Claude: Focus on Task A." in result

    def test_format_history_preserves_order(self):
        history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]
        result = context.format_history(history)
        assert result.index("First") < result.index("Second") < result.index("Third")


class TestTodoistService:
    def test_tasks_no_token_returns_empty(self, monkeypatch):
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        result = asyncio.run(todoist.tasks())
        assert result == []

    def test_tasks_returns_list(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        items = [{"id": "1", "content": "Buy milk"}, {"id": "2", "content": "Ship it"}]
        with _mock_get("todoist", return_value=_response(200, items)):
            result = asyncio.run(todoist.tasks())
        assert len(result) == 2
        assert result[0]["content"] == "Buy milk"

    def test_tasks_error_returns_empty(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        with _mock_get("todoist", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(todoist.tasks())
        assert result == []

    def test_no_token_returns_idle(self, monkeypatch):
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        result = asyncio.run(todoist.check())
        assert result["label"] == "Todoist"
        assert result["state"] == "idle"

    def test_ok_response_counts_tasks(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")
        tasks = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        with _mock_get("todoist", return_value=_response(200, tasks)):
            result = asyncio.run(todoist.check())
        assert result["state"] == "ok"
        assert "3 tasks" in result["detail"]

    def test_singular_task(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")
        with _mock_get("todoist", return_value=_response(200, [{"id": "1"}])):
            result = asyncio.run(todoist.check())
        assert "1 task" in result["detail"]
        assert "1 tasks" not in result["detail"]

    def test_http_error_returns_warn(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")
        with _mock_get("todoist", return_value=_response(401, {"error": "Unauthorized"})):
            result = asyncio.run(todoist.check())
        assert result["state"] == "warn"
        assert "401" in result["detail"]

    def test_connection_error_returns_warn(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "test-token")
        with _mock_get("todoist", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(todoist.check())
        assert result["state"] == "warn"


# ---------------------------------------------------------------------------
# github
# ---------------------------------------------------------------------------


class TestTodoistCreateTask:
    def test_no_token_returns_error(self, monkeypatch):
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        result = asyncio.run(todoist.create_task("Buy milk"))
        assert result["error"] == "no_token"

    def test_successful_creation(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        task = {"id": "1", "content": "Buy milk"}
        with _mock_post("todoist", return_value=_response(200, task)):
            result = asyncio.run(todoist.create_task("Buy milk"))
        assert result["content"] == "Buy milk"

    def test_http_error_returns_error_dict(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        with _mock_post("todoist", return_value=_response(403, {"error": "Forbidden"})):
            result = asyncio.run(todoist.create_task("Buy milk"))
        assert result["error"] == "http_error"
        assert "403" in result["detail"]

    def test_connection_error_returns_error_dict(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        with _mock_post("todoist", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(todoist.create_task("Buy milk"))
        assert result["error"] == "request_failed"


class TestTodoistCloseTask:
    def test_no_token_returns_error(self, monkeypatch):
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        result = asyncio.run(todoist.close_task("123"))
        assert result["error"] == "no_token"

    def test_successful_close(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        # Todoist close returns 204 No Content — empty body
        with _mock_post("todoist", return_value=_response(204, {})):
            result = asyncio.run(todoist.close_task("123"))
        assert result["ok"] is True

    def test_http_error_returns_error_dict(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        with _mock_post("todoist", return_value=_response(404, {"error": "Not Found"})):
            result = asyncio.run(todoist.close_task("bad-id"))
        assert result["error"] == "http_error"
        assert "404" in result["detail"]


class TestGithubService:
    def test_ok_response_shows_repo_count(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        with _mock_get("github", return_value=_response(200, {"public_repos": 7})):
            result = asyncio.run(github.check())
        assert result["state"] == "ok"
        assert "7 public repos" in result["detail"]

    def test_http_error_returns_warn(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        with _mock_get("github", return_value=_response(404, {"message": "Not Found"})):
            result = asyncio.run(github.check())
        assert result["state"] == "warn"
        assert "404" in result["detail"]

    def test_connection_error_returns_warn(self):
        with _mock_get("github", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(github.check())
        assert result["state"] == "warn"

    def test_missing_public_repos_key(self):
        with _mock_get("github", return_value=_response(200, {})):
            result = asyncio.run(github.check())
        assert result["state"] == "ok"
        assert "?" in result["detail"]


class TestGithubRecentActivity:
    def test_push_event_formatted(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        events = [
            {
                "type": "PushEvent",
                "repo": {"name": "testuser/JARVIS"},
                "payload": {"commits": [{}, {}]},
            }
        ]
        with _mock_get("github", return_value=_response(200, events)):
            result = asyncio.run(github.recent_activity())
        assert len(result) == 1
        assert "2 commits" in result[0]
        assert "JARVIS" in result[0]

    def test_pull_request_event_formatted(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        events = [
            {
                "type": "PullRequestEvent",
                "repo": {"name": "testuser/repo"},
                "payload": {
                    "action": "opened",
                    "pull_request": {"title": "Add feature X"},
                },
            }
        ]
        with _mock_get("github", return_value=_response(200, events)):
            result = asyncio.run(github.recent_activity())
        assert len(result) == 1
        assert "PR opened" in result[0]
        assert "Add feature X" in result[0]

    def test_deduplicates_push_events_per_repo(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        events = [
            {"type": "PushEvent", "repo": {"name": "u/repo"}, "payload": {"commits": [{}]}},
            {"type": "PushEvent", "repo": {"name": "u/repo"}, "payload": {"commits": [{}]}},
        ]
        with _mock_get("github", return_value=_response(200, events)):
            result = asyncio.run(github.recent_activity())
        assert len(result) == 1

    def test_error_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        with _mock_get("github", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(github.recent_activity())
        assert result == []

    def test_limit_respected(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        events = [
            {"type": "PushEvent", "repo": {"name": f"u/repo{i}"}, "payload": {"commits": [{}]}}
            for i in range(10)
        ]
        with _mock_get("github", return_value=_response(200, events)):
            result = asyncio.run(github.recent_activity(limit=2))
        assert len(result) == 2


# ---------------------------------------------------------------------------
# heyclaude
# ---------------------------------------------------------------------------


class TestHeyclaudeService:
    def test_check_online(self, monkeypatch):
        monkeypatch.setenv("HEYCLAUDE_URL", "http://localhost:8000")
        with _mock_get("heyclaude", return_value=_response(200, {})):
            result = asyncio.run(heyclaude.check())
        assert result["state"] == "ok"
        assert "running" in result["detail"]

    def test_check_offline(self, monkeypatch):
        monkeypatch.setenv("HEYCLAUDE_URL", "http://localhost:8000")
        with _mock_get("heyclaude", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(heyclaude.check())
        assert result["state"] == "idle"

    def test_ask_forwards_mode(self, monkeypatch):
        monkeypatch.setenv("HEYCLAUDE_URL", "http://localhost:8000")
        resp = _response(200, {"reply": "Hello", "events": []})
        with _mock_post("heyclaude", return_value=resp) as mock_cls:
            result = asyncio.run(heyclaude.ask("hi", mode="researcher"))
        assert result["reply"] == "Hello"
        instance = mock_cls.return_value.__aenter__.return_value
        _, kwargs = instance.post.call_args
        assert kwargs["json"]["mode"] == "researcher"

    def test_ask_offline_returns_offline_message(self, monkeypatch):
        monkeypatch.setenv("HEYCLAUDE_URL", "http://localhost:8000")
        with _mock_post("heyclaude", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(heyclaude.ask("hello"))
        assert result["error"] == "heyclaude_offline"
        assert "offline" in result["reply"].lower()

    def test_ask_empty_query_returns_empty(self):
        result = asyncio.run(heyclaude.ask("   "))
        assert result["reply"] == ""

    def test_modes_returns_list(self, monkeypatch):
        monkeypatch.setenv("HEYCLAUDE_URL", "http://localhost:8000")
        fake = [{"name": "default", "label": "Voice", "icon": "◉", "description": "..."}]
        with _mock_get("heyclaude", return_value=_response(200, fake)):
            result = asyncio.run(heyclaude.modes())
        assert result == fake

    def test_modes_offline_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("HEYCLAUDE_URL", "http://localhost:8000")
        with _mock_get("heyclaude", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(heyclaude.modes())
        assert result == []
