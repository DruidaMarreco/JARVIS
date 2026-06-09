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

from backend.services import context, github, heyclaude, ollama, todoist, weather

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _collect_stream(gen) -> list[str]:
    """Drain an async generator into a list of strings."""
    chunks = []
    async for chunk in gen:
        chunks.append(chunk)
    return chunks


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

    def test_gather_includes_weather_in_header(self, monkeypatch):
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_USERNAME", "")
        payload = {"current": {"temperature_2m": 21.0, "weathercode": 1, "windspeed_10m": 5.0}}
        with _mock_get("weather", return_value=_response(200, payload)):
            result = asyncio.run(context.gather())
        assert "21°C" in result
        assert "[Context" in result

    def test_gather_includes_github_activity(self, monkeypatch):
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        events = [{"type": "PushEvent", "repo": {"name": "u/JARVIS"}, "payload": {"commits": [{}]}}]
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


class TestWeatherService:
    def test_returns_temperature_and_description(self, monkeypatch):
        monkeypatch.setenv("WEATHER_LAT", "38.71")
        monkeypatch.setenv("WEATHER_LON", "-9.14")
        payload = {"current": {"temperature_2m": 22.4, "weathercode": 2, "windspeed_10m": 8.0}}
        with _mock_get("weather", return_value=_response(200, payload)):
            result = asyncio.run(weather.current())
        assert "22°C" in result
        assert "partly cloudy" in result

    def test_includes_wind_when_above_threshold(self, monkeypatch):
        payload = {"current": {"temperature_2m": 18.0, "weathercode": 1, "windspeed_10m": 25.0}}
        with _mock_get("weather", return_value=_response(200, payload)):
            result = asyncio.run(weather.current())
        assert "25 km/h wind" in result

    def test_omits_wind_when_calm(self, monkeypatch):
        payload = {"current": {"temperature_2m": 20.0, "weathercode": 0, "windspeed_10m": 5.0}}
        with _mock_get("weather", return_value=_response(200, payload)):
            result = asyncio.run(weather.current())
        assert "wind" not in result

    def test_returns_empty_on_api_failure(self, monkeypatch):
        with _mock_get("weather", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(weather.current())
        assert result == ""

    def test_returns_empty_when_temp_missing(self, monkeypatch):
        payload = {"current": {"weathercode": 0}}
        with _mock_get("weather", return_value=_response(200, payload)):
            result = asyncio.run(weather.current())
        assert result == ""

    def test_custom_lat_lon_overrides_env(self, monkeypatch):
        """Passing lat/lon args should take priority over env vars."""
        monkeypatch.setenv("WEATHER_LAT", "38.71")
        monkeypatch.setenv("WEATHER_LON", "-9.14")
        payload = {"current": {"temperature_2m": 10.0, "weathercode": 0, "windspeed_10m": 0.0}}
        captured: list[str] = []

        async def _get(url, params=None, **kw):  # noqa: ARG001
            if params:
                captured.append(f"{params.get('latitude')},{params.get('longitude')}")
            return _response(200, payload)

        with _mock_get("weather", side_effect=_get):
            asyncio.run(weather.current(lat="51.5", lon="-0.12"))
        assert captured and captured[0] == "51.5,-0.12"


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


class TestTodoistSearch:
    def test_no_token_returns_empty(self, monkeypatch):
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        result = asyncio.run(todoist.search("meeting"))
        assert result == []

    def test_empty_query_returns_empty(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        result = asyncio.run(todoist.search("   "))
        assert result == []

    def test_returns_matching_tasks(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        items = [{"id": "1", "content": "Plan the meeting"}]
        with _mock_get("todoist", return_value=_response(200, items)):
            result = asyncio.run(todoist.search("meeting"))
        assert len(result) == 1
        assert result[0]["content"] == "Plan the meeting"

    def test_error_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        with _mock_get("todoist", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(todoist.search("anything"))
        assert result == []

    def test_limit_respected(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        items = [{"id": str(i), "content": f"Task {i}"} for i in range(10)]
        with _mock_get("todoist", return_value=_response(200, items)):
            result = asyncio.run(todoist.search("task", limit=3))
        assert len(result) == 3


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
    def test_ok_response_shows_open_pr_count(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        with _mock_get("github", return_value=_response(200, {"total_count": 3, "items": []})):
            result = asyncio.run(github.check())
        assert result["state"] == "ok"
        assert "3 open PRs" in result["detail"]

    def test_singular_pr(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        with _mock_get("github", return_value=_response(200, {"total_count": 1, "items": []})):
            result = asyncio.run(github.check())
        assert "1 open PR" in result["detail"]
        assert "1 open PRs" not in result["detail"]

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

    def test_missing_total_count_key(self):
        with _mock_get("github", return_value=_response(200, {"items": []})):
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

    def test_two_pushes_to_same_repo_both_returned(self, monkeypatch):
        """recent_activity delegates to recent_events which shows all events."""
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        events = [
            {
                "type": "PushEvent",
                "repo": {"name": "u/repo"},
                "payload": {"commits": [{}]},
                "created_at": "2026-06-08T10:00:00Z",
            },
            {
                "type": "PushEvent",
                "repo": {"name": "u/repo"},
                "payload": {"commits": [{}]},
                "created_at": "2026-06-08T11:00:00Z",
            },
        ]
        with _mock_get("github", return_value=_response(200, events)):
            result = asyncio.run(github.recent_activity(limit=3))
        assert len(result) == 2

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


class TestOpenPRsService:
    def test_returns_list_of_prs(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        items = [
            {
                "number": 42,
                "title": "Add dark mode",
                "repository_url": "https://api.github.com/repos/testuser/JARVIS",
                "html_url": "https://github.com/testuser/JARVIS/pull/42",
                "updated_at": "2026-06-07T10:00:00Z",
            }
        ]
        with _mock_get("github", return_value=_response(200, {"items": items})):
            result = asyncio.run(github.open_prs())
        assert len(result) == 1
        assert result[0]["number"] == 42
        assert result[0]["title"] == "Add dark mode"
        assert result[0]["repo"] == "JARVIS"
        assert result[0]["url"] == "https://github.com/testuser/JARVIS/pull/42"
        assert result[0]["updated_at"] == "2026-06-07"

    def test_empty_items_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        with _mock_get("github", return_value=_response(200, {"items": []})):
            result = asyncio.run(github.open_prs())
        assert result == []

    def test_limit_respected(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        items = [
            {
                "number": i,
                "title": f"PR {i}",
                "repository_url": "https://api.github.com/repos/u/r",
                "html_url": f"https://github.com/u/r/pull/{i}",
                "updated_at": "2026-06-01T00:00:00Z",
            }
            for i in range(5)
        ]
        with _mock_get("github", return_value=_response(200, {"items": items})):
            result = asyncio.run(github.open_prs(limit=3))
        assert len(result) == 3

    def test_error_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        with _mock_get("github", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(github.open_prs())
        assert result == []

    def test_missing_repository_url_uses_question_mark(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        items = [
            {
                "number": 1,
                "title": "Fix bug",
                "repository_url": "",
                "html_url": "https://github.com/u/r/pull/1",
                "updated_at": "2026-06-01T00:00:00Z",
            }
        ]
        with _mock_get("github", return_value=_response(200, {"items": items})):
            result = asyncio.run(github.open_prs())
        assert result[0]["repo"] == "?"


class TestTodoistProjects:
    def test_no_token_returns_empty_dict(self, monkeypatch):
        monkeypatch.delenv("TODOIST_API_TOKEN", raising=False)
        result = asyncio.run(todoist.projects())
        assert result == {}

    def test_returns_id_name_map(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        data = [{"id": "abc", "name": "Work"}, {"id": "xyz", "name": "Personal"}]
        with _mock_get("todoist", return_value=_response(200, data)):
            result = asyncio.run(todoist.projects())
        assert result == {"abc": "Work", "xyz": "Personal"}

    def test_api_error_returns_empty_dict(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        with _mock_get("todoist", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(todoist.projects())
        assert result == {}


class TestTodoistCreateTaskInbox:
    """create_task with empty due_string should not include due_string in the payload."""

    def test_inbox_task_omits_due_string(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        task = {"id": "1", "content": "Buy milk"}
        captured: list[dict] = []

        async def _post(url, headers=None, json=None, **kw):  # noqa: ARG001
            if json:
                captured.append(json)
            return _response(200, task)

        with _mock_post("todoist", side_effect=_post):
            asyncio.run(todoist.create_task("Buy milk", due_string=""))
        assert captured
        assert "due_string" not in captured[0]
        assert captured[0]["content"] == "Buy milk"

    def test_task_with_due_includes_due_string(self, monkeypatch):
        monkeypatch.setenv("TODOIST_API_TOKEN", "tok")
        task = {"id": "1", "content": "Meeting"}
        captured: list[dict] = []

        async def _post(url, headers=None, json=None, **kw):  # noqa: ARG001
            if json:
                captured.append(json)
            return _response(200, task)

        with _mock_post("todoist", side_effect=_post):
            asyncio.run(todoist.create_task("Meeting", due_string="tomorrow"))
        assert captured[0].get("due_string") == "tomorrow"


class TestGithubRecentEvents:
    def test_push_event_returns_structured_dict(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        events = [
            {
                "type": "PushEvent",
                "repo": {"name": "testuser/JARVIS"},
                "payload": {"commits": [{}, {}], "ref": "refs/heads/main"},
                "created_at": "2026-06-08T10:00:00Z",
            }
        ]
        with _mock_get("github", return_value=_response(200, events)):
            result = asyncio.run(github.recent_events())
        assert len(result) == 1
        ev = result[0]
        assert ev["type"] == "push"
        assert ev["repo"] == "JARVIS"
        assert "2 commits" in ev["summary"]
        assert ev["date"] == "2026-06-08"

    def test_pr_opened_returns_pr_opened_type(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        events = [
            {
                "type": "PullRequestEvent",
                "repo": {"name": "testuser/repo"},
                "payload": {
                    "action": "opened",
                    "pull_request": {
                        "title": "Add feature X",
                        "html_url": "https://github.com/testuser/repo/pull/1",
                        "merged": False,
                    },
                },
                "created_at": "2026-06-08T09:00:00Z",
            }
        ]
        with _mock_get("github", return_value=_response(200, events)):
            result = asyncio.run(github.recent_events())
        assert result[0]["type"] == "pr_opened"
        assert "Add feature X" in result[0]["summary"]

    def test_error_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        with _mock_get("github", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(github.recent_events())
        assert result == []


# ---------------------------------------------------------------------------
# github — search_repos
# ---------------------------------------------------------------------------


class TestGithubSearchRepos:
    def test_returns_repo_list(self, monkeypatch):
        monkeypatch.setenv("GITHUB_USERNAME", "testuser")
        payload = {
            "items": [
                {
                    "name": "JARVIS",
                    "full_name": "testuser/JARVIS",
                    "description": "Personal ops deck",
                    "html_url": "https://github.com/testuser/JARVIS",
                    "stargazers_count": 7,
                    "updated_at": "2026-06-08T10:00:00Z",
                    "language": "Python",
                    "private": False,
                }
            ]
        }
        with _mock_get("github", return_value=_response(200, payload)):
            result = asyncio.run(github.search_repos("JARVIS"))
        assert len(result) == 1
        assert result[0]["name"] == "JARVIS"
        assert result[0]["stars"] == 7
        assert result[0]["language"] == "Python"
        assert result[0]["updated"] == "2026-06-08"

    def test_empty_query_returns_empty_list(self):
        result = asyncio.run(github.search_repos("   "))
        assert result == []

    def test_api_error_returns_empty_list(self):
        with _mock_get("github", return_value=_response(422, {"message": "Validation Failed"})):
            result = asyncio.run(github.search_repos("foo"))
        assert result == []

    def test_connection_error_returns_empty_list(self):
        with _mock_get("github", side_effect=httpx.ConnectError("refused")):
            result = asyncio.run(github.search_repos("test"))
        assert result == []

    def test_respects_limit(self, monkeypatch):
        items = [
            {
                "name": f"repo{i}",
                "full_name": f"u/repo{i}",
                "description": "",
                "html_url": f"https://github.com/u/repo{i}",
                "stargazers_count": 0,
                "updated_at": "2026-01-01T00:00:00Z",
                "language": None,
                "private": False,
            }
            for i in range(10)
        ]
        with _mock_get("github", return_value=_response(200, {"items": items})):
            result = asyncio.run(github.search_repos("repo", limit=3))
        assert len(result) == 3


# ---------------------------------------------------------------------------
# ollama
# ---------------------------------------------------------------------------


def _mock_ollama(method: str, return_value=None, side_effect=None):
    """Patch ollama.AsyncClient so instantiation returns a mock with async methods."""
    mock_instance = AsyncMock()
    attr = getattr(mock_instance, method)
    if side_effect is not None:
        attr.side_effect = side_effect
    else:
        attr.return_value = return_value
    return patch("backend.services.ollama.AsyncClient", return_value=mock_instance)


def _fake_chat_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    resp = MagicMock()
    resp.message = msg
    return resp


def _fake_list_response(models: list[tuple[str, int]]) -> MagicMock:
    """models: list of (name, size_bytes)."""
    resp = MagicMock()
    resp.models = [MagicMock(**{"model": name, "size": size}) for name, size in models]
    return resp


class TestOllamaService:
    def test_ask_returns_reply(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
        monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
        fake = _fake_chat_response("Hello from Ollama!")
        with _mock_ollama("chat", return_value=fake):
            result = asyncio.run(ollama.ask("hi"))
        assert result["reply"] == "Hello from Ollama!"
        assert result["events"] == []
        assert result["model"] == "llama3.2"

    def test_ask_uses_env_model(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODEL", "mistral")
        fake = _fake_chat_response("Mistral reply")
        with _mock_ollama("chat", return_value=fake) as mock_cls:
            asyncio.run(ollama.ask("hello"))
        instance = mock_cls.return_value
        call_kwargs = instance.chat.call_args.kwargs
        assert call_kwargs.get("model") == "mistral"

    def test_ask_overrides_model(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
        fake = _fake_chat_response("Gemma reply")
        with _mock_ollama("chat", return_value=fake) as mock_cls:
            asyncio.run(ollama.ask("hi", model="gemma3"))
        instance = mock_cls.return_value
        assert instance.chat.call_args.kwargs.get("model") == "gemma3"

    def test_ask_error_returns_error_dict(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
        with _mock_ollama("chat", side_effect=ConnectionRefusedError("refused")):
            result = asyncio.run(ollama.ask("hi"))
        assert result["error"] == "ollama_error"
        assert "reply" in result

    def test_check_ok_shows_model_count(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
        fake = _fake_list_response(
            [("llama3.2:latest", 2_000_000_000), ("mistral:latest", 4_000_000_000)]
        )
        with _mock_ollama("list", return_value=fake):
            result = asyncio.run(ollama.check())
        assert result["state"] == "ok"
        assert "2 local models" in result["detail"]

    def test_check_singular_model(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
        fake = _fake_list_response([("llama3.2:latest", 2_000_000_000)])
        with _mock_ollama("list", return_value=fake):
            result = asyncio.run(ollama.check())
        assert "1 local model" in result["detail"]
        assert "1 local models" not in result["detail"]

    def test_check_offline_returns_warn(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
        with _mock_ollama("list", side_effect=ConnectionRefusedError("refused")):
            result = asyncio.run(ollama.check())
        assert result["state"] == "warn"

    def test_list_models_returns_names_and_sizes(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
        fake = _fake_list_response([("llama3.2:latest", 2_000_000_000)])
        with _mock_ollama("list", return_value=fake):
            result = asyncio.run(ollama.list_models())
        assert len(result) == 1
        assert result[0]["name"] == "llama3.2:latest"
        assert result[0]["size_gb"] == 2.0

    def test_list_models_error_returns_empty(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
        with _mock_ollama("list", side_effect=ConnectionRefusedError("refused")):
            result = asyncio.run(ollama.list_models())
        assert result == []

    def test_stream_yields_model_then_tokens_then_done(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")

        async def fake_chat_stream(*args, **kwargs):
            for word in ["Hello", " world"]:
                msg = MagicMock()
                msg.content = word
                chunk = MagicMock()
                chunk.message = msg
                yield chunk

        with _mock_ollama("chat", return_value=fake_chat_stream()):
            chunks = asyncio.run(_collect_stream(ollama.stream("hi")))

        import json as _json

        events = [_json.loads(c[6:]) for c in chunks if c.startswith("data: ")]
        assert events[0].get("model") == "llama3.2"
        tokens = [e["token"] for e in events if "token" in e]
        assert "Hello" in tokens
        assert events[-1].get("done") is True

    def test_stream_yields_error_event_on_failure(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
        with _mock_ollama("chat", side_effect=ConnectionRefusedError("refused")):
            chunks = asyncio.run(_collect_stream(ollama.stream("hi")))

        import json as _json

        events = [_json.loads(c[6:]) for c in chunks if c.startswith("data: ")]
        assert any("error" in e for e in events)
        assert events[-1].get("done") is True

    def test_stream_includes_history_in_messages(self, monkeypatch):
        """History turns must appear as structured messages before the user prompt."""
        monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
        captured_calls: list[dict] = []

        async def fake_chat(**kwargs):
            captured_calls.append(kwargs)

            async def _empty():
                return
                yield  # pragma: no cover

            return _empty()

        mock_instance = AsyncMock()
        mock_instance.chat.side_effect = fake_chat
        with patch("backend.services.ollama.AsyncClient", return_value=mock_instance):
            history = [
                {"role": "user", "content": "What is Python?"},
                {"role": "assistant", "content": "A programming language."},
            ]
            asyncio.run(_collect_stream(ollama.stream("Tell me more", history=history)))

        assert captured_calls, "chat() was never called"
        messages = captured_calls[0]["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant", "user"]
        assert messages[-1]["content"] == "Tell me more"

    def test_build_messages_filters_invalid_roles(self):
        """_build_messages should only include user/assistant roles."""
        from backend.services.ollama import _build_messages

        history = [
            {"role": "system", "content": "Be helpful"},  # filtered out
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        msgs = _build_messages("Follow-up", history)
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        assert msgs[-1] == {"role": "user", "content": "Follow-up"}
        assert len(msgs) == 3  # system entry dropped

    def test_build_messages_prepends_system_prompt(self):
        """When system_prompt is set it must be the first message."""
        from backend.services.ollama import _build_messages

        msgs = _build_messages("Hello", [], system_prompt="Be concise.")
        assert msgs[0] == {"role": "system", "content": "Be concise."}
        assert msgs[-1] == {"role": "user", "content": "Hello"}

    def test_build_messages_empty_system_prompt_not_added(self):
        """Empty or whitespace-only system_prompt must not add a system message."""
        from backend.services.ollama import _build_messages

        msgs = _build_messages("Hello", [], system_prompt="   ")
        assert all(m["role"] != "system" for m in msgs)

    def test_stream_passes_system_prompt_to_build_messages(self, monkeypatch):
        """system_prompt forwarded through stream() must appear in messages."""
        monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
        captured: list[dict] = []

        async def fake_chat(**kwargs):
            captured.append(kwargs)

            async def _empty():
                return
                yield  # pragma: no cover

            return _empty()

        mock_instance = AsyncMock()
        mock_instance.chat.side_effect = fake_chat
        with patch("backend.services.ollama.AsyncClient", return_value=mock_instance):
            asyncio.run(_collect_stream(ollama.stream("hi", system_prompt="Be brief.")))

        assert captured
        messages = captured[0]["messages"]
        assert messages[0] == {"role": "system", "content": "Be brief."}


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
