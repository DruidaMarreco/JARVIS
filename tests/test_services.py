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

from backend.services import github, heyclaude, todoist


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


class TestTodoistService:
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
