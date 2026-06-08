"""Route-level tests using FastAPI's TestClient (synchronous, offline).

Services are mocked so no real network calls are made. These tests verify
that the routing layer correctly wires requests to services and serialises
responses.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------


class TestStatusRoute:
    def test_returns_list_of_three_chips(self):
        chips = [
            {"label": "Hey Claude", "state": "ok", "detail": "running"},
            {"label": "Todoist", "state": "idle", "detail": "no token set"},
            {"label": "GitHub", "state": "ok", "detail": "5 public repos"},
        ]
        with (
            patch("backend.services.heyclaude.check", new_callable=AsyncMock, return_value=chips[0]),
            patch("backend.services.todoist.check", new_callable=AsyncMock, return_value=chips[1]),
            patch("backend.services.github.check", new_callable=AsyncMock, return_value=chips[2]),
        ):
            r = client.get("/api/status")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 3

    def test_chip_shape(self):
        chip = {"label": "GitHub", "state": "ok", "detail": "3 repos"}
        with (
            patch("backend.services.heyclaude.check", new_callable=AsyncMock, return_value=chip),
            patch("backend.services.todoist.check", new_callable=AsyncMock, return_value=chip),
            patch("backend.services.github.check", new_callable=AsyncMock, return_value=chip),
        ):
            r = client.get("/api/status")
        for item in r.json():
            assert {"label", "state", "detail"} <= item.keys()


# ---------------------------------------------------------------------------
# GET /api/modes
# ---------------------------------------------------------------------------


class TestModesRoute:
    def test_returns_modes_from_heyclaude(self):
        fake = [{"name": "default", "label": "Voice", "icon": "◉", "description": "..."}]
        with patch("backend.services.heyclaude.modes", new_callable=AsyncMock, return_value=fake):
            r = client.get("/api/modes")
        assert r.status_code == 200
        assert r.json() == fake

    def test_returns_empty_list_when_heyclaude_offline(self):
        with patch("backend.services.heyclaude.modes", new_callable=AsyncMock, return_value=[]):
            r = client.get("/api/modes")
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# POST /api/dispatch
# ---------------------------------------------------------------------------


class TestDispatchRoute:
    def test_forwards_query_to_heyclaude(self):
        reply = {"reply": "Hello from Claude", "events": []}
        with patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=reply) as mock_ask:
            r = client.post("/api/dispatch", json={"query": "Hello", "use_context": False})
        assert r.status_code == 200
        assert r.json()["reply"] == "Hello from Claude"
        mock_ask.assert_called_once_with("Hello", mode="default")

    def test_forwards_mode_to_heyclaude(self):
        reply = {"reply": "Deep analysis", "events": []}
        with patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=reply) as mock_ask:
            r = client.post("/api/dispatch", json={"query": "Explain entropy", "mode": "researcher", "use_context": False})
        assert r.status_code == 200
        mock_ask.assert_called_once_with("Explain entropy", mode="researcher")

    def test_default_mode_when_omitted(self):
        reply = {"reply": "ok", "events": []}
        with patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=reply) as mock_ask:
            r = client.post("/api/dispatch", json={"query": "hi"})
        assert r.status_code == 200
        _, kwargs = mock_ask.call_args
        assert kwargs.get("mode", "default") == "default"

    def test_missing_query_returns_422(self):
        r = client.post("/api/dispatch", json={})
        assert r.status_code == 422

    def test_offline_reply_propagates(self):
        offline = {"reply": "Hey Claude is offline.", "error": "heyclaude_offline"}
        with patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=offline):
            r = client.post("/api/dispatch", json={"query": "hi"})
        assert r.status_code == 200
        assert r.json()["error"] == "heyclaude_offline"

    def test_context_included_in_response(self):
        reply = {"reply": "Focus on the PR first.", "events": []}
        ctx = "[Context · Saturday 07 Jun 2026 · 14:00]\nToday's tasks (1): Review PR"
        with (
            patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=reply),
            patch("backend.services.context.gather", new_callable=AsyncMock, return_value=ctx),
        ):
            r = client.post("/api/dispatch", json={"query": "What to do?", "use_context": True})
        assert r.status_code == 200
        data = r.json()
        assert data["context"] == ctx
        assert data["reply"] == "Focus on the PR first."

    def test_context_skipped_when_disabled(self):
        reply = {"reply": "Sure.", "events": []}
        with (
            patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=reply) as mock_ask,
            patch("backend.services.context.gather", new_callable=AsyncMock, return_value="ctx") as mock_ctx,
        ):
            r = client.post("/api/dispatch", json={"query": "hi", "use_context": False})
        assert r.status_code == 200
        mock_ctx.assert_not_called()
        # Query sent to Hey Claude should not be augmented
        sent_query = mock_ask.call_args.args[0]
        assert "Context" not in sent_query

    def test_context_augments_query_sent_to_heyclaude(self):
        reply = {"reply": "Done.", "events": []}
        ctx = "[Context · Saturday]\nTask A"
        with (
            patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=reply) as mock_ask,
            patch("backend.services.context.gather", new_callable=AsyncMock, return_value=ctx),
        ):
            r = client.post("/api/dispatch", json={"query": "What now?", "use_context": True})
        sent_query = mock_ask.call_args.args[0]
        assert "[Context" in sent_query
        assert "What now?" in sent_query

    def test_history_threaded_into_augmented_query(self):
        reply = {"reply": "Done.", "events": []}
        history = [
            {"role": "user", "content": "What should I do?"},
            {"role": "assistant", "content": "Focus on Task A."},
        ]
        with (
            patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=reply) as mock_ask,
            patch("backend.services.context.gather", new_callable=AsyncMock, return_value=""),
        ):
            r = client.post("/api/dispatch", json={"query": "What's next?", "use_context": False, "history": history})
        assert r.status_code == 200
        sent_query = mock_ask.call_args.args[0]
        assert "[Prior conversation]" in sent_query
        assert "What should I do?" in sent_query
        assert "Focus on Task A." in sent_query
        assert "What's next?" in sent_query

    def test_history_not_required(self):
        reply = {"reply": "ok", "events": []}
        with patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=reply):
            r = client.post("/api/dispatch", json={"query": "hi", "use_context": False})
        assert r.status_code == 200

    def test_history_not_returned_in_context_field(self):
        """History is threaded into the query but not echoed back in 'context' (visible in thread)."""
        reply = {"reply": "Sure.", "events": []}
        history = [{"role": "user", "content": "Earlier message"}]
        ctx = "[Context · Sun]\nTask A"
        with (
            patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=reply),
            patch("backend.services.context.gather", new_callable=AsyncMock, return_value=ctx),
        ):
            r = client.post("/api/dispatch", json={"query": "hi", "use_context": True, "history": history})
        assert r.status_code == 200
        data = r.json()
        # context field should only contain the gather output, not the history block
        assert "Earlier message" not in data["context"]
        assert "[Context" in data["context"]


# ---------------------------------------------------------------------------
# POST /api/tasks
# ---------------------------------------------------------------------------


class TestTasksRoute:
    def test_creates_task_via_todoist_service(self):
        created = {"id": "42", "content": "Buy milk"}
        with patch("backend.services.todoist.create_task", new_callable=AsyncMock, return_value=created) as mock:
            r = client.post("/api/tasks", json={"content": "Buy milk"})
        assert r.status_code == 200
        assert r.json()["content"] == "Buy milk"
        mock.assert_called_once_with("Buy milk", "today")

    def test_custom_due_string_forwarded(self):
        created = {"id": "1", "content": "Meeting prep"}
        with patch("backend.services.todoist.create_task", new_callable=AsyncMock, return_value=created) as mock:
            r = client.post("/api/tasks", json={"content": "Meeting prep", "due_string": "tomorrow"})
        assert r.status_code == 200
        mock.assert_called_once_with("Meeting prep", "tomorrow")

    def test_missing_content_returns_422(self):
        r = client.post("/api/tasks", json={})
        assert r.status_code == 422

    def test_empty_content_returns_422(self):
        r = client.post("/api/tasks", json={"content": "   "})
        assert r.status_code == 422

    def test_content_too_long_returns_422(self):
        r = client.post("/api/tasks", json={"content": "x" * 501})
        assert r.status_code == 422

    def test_error_from_service_propagates(self):
        err = {"error": "no_token", "detail": "TODOIST_API_TOKEN is not set"}
        with patch("backend.services.todoist.create_task", new_callable=AsyncMock, return_value=err):
            r = client.post("/api/tasks", json={"content": "x"})
        assert r.status_code == 200
        assert r.json()["error"] == "no_token"


class TestListTasksRoute:
    def test_returns_tasks_with_count(self):
        raw = [
            {"id": "1", "content": "Review PR", "priority": 2, "due": {"string": "today"}},
            {"id": "2", "content": "Write tests", "priority": 1, "due": None},
        ]
        with patch("backend.services.todoist.tasks", new_callable=AsyncMock, return_value=raw):
            r = client.get("/api/tasks")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2
        assert data["tasks"][0]["content"] == "Review PR"
        assert data["tasks"][0]["priority"] == 2

    def test_empty_list_when_no_tasks(self):
        with patch("backend.services.todoist.tasks", new_callable=AsyncMock, return_value=[]):
            r = client.get("/api/tasks")
        assert r.status_code == 200
        assert r.json() == {"tasks": [], "count": 0}


class TestCloseTaskRoute:
    def test_close_task_returns_ok(self):
        with patch("backend.services.todoist.close_task", new_callable=AsyncMock, return_value={"ok": True}) as mock:
            r = client.post("/api/tasks/42/close")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        mock.assert_called_once_with("42")

    def test_close_task_error_propagates(self):
        err = {"error": "http_error", "detail": "HTTP 404"}
        with patch("backend.services.todoist.close_task", new_callable=AsyncMock, return_value=err):
            r = client.post("/api/tasks/bad-id/close")
        assert r.status_code == 200
        assert r.json()["error"] == "http_error"


# ---------------------------------------------------------------------------
# GET /healthz
# ---------------------------------------------------------------------------


class TestOllamaModelsRoute:
    def test_returns_models_list(self):
        models = [{"name": "llama3.2:latest", "size_gb": 2.0}]
        with patch("backend.services.ollama.list_models", new_callable=AsyncMock, return_value=models):
            r = client.get("/api/ollama/models")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["models"][0]["name"] == "llama3.2:latest"

    def test_empty_when_offline(self):
        with patch("backend.services.ollama.list_models", new_callable=AsyncMock, return_value=[]):
            r = client.get("/api/ollama/models")
        assert r.status_code == 200
        assert r.json() == {"models": [], "count": 0}


class TestDispatchOllamaProvider:
    def test_ollama_provider_routes_to_ollama(self):
        reply = {"reply": "Local reply", "events": [], "model": "llama3.2"}
        with patch("backend.services.ollama.ask", new_callable=AsyncMock, return_value=reply) as mock_ollama:
            r = client.post("/api/dispatch", json={"query": "hi", "use_context": False, "provider": "ollama"})
        assert r.status_code == 200
        assert r.json()["reply"] == "Local reply"
        mock_ollama.assert_called_once()

    def test_heyclaude_provider_skips_ollama(self):
        reply = {"reply": "HC reply", "events": []}
        with (
            patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=reply) as mock_hc,
            patch("backend.services.ollama.ask", new_callable=AsyncMock) as mock_ollama,
        ):
            r = client.post("/api/dispatch", json={"query": "hi", "use_context": False, "provider": "heyclaude"})
        assert r.status_code == 200
        mock_hc.assert_called_once()
        mock_ollama.assert_not_called()

    def test_auto_provider_falls_back_to_ollama_when_hc_offline(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
        hc_reply = {"reply": "offline", "error": "heyclaude_offline"}
        ol_reply = {"reply": "Ollama fallback", "events": [], "model": "llama3.2"}
        with (
            patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=hc_reply),
            patch("backend.services.ollama.ask", new_callable=AsyncMock, return_value=ol_reply) as mock_ollama,
            patch("backend.services.context.gather", new_callable=AsyncMock, return_value=""),
        ):
            r = client.post("/api/dispatch", json={"query": "hi", "use_context": False, "provider": "auto"})
        assert r.status_code == 200
        mock_ollama.assert_called_once()
        assert r.json()["reply"] == "Ollama fallback"

    def test_auto_provider_does_not_fall_back_without_ollama_url(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_URL", raising=False)
        hc_reply = {"reply": "offline", "error": "heyclaude_offline"}
        with (
            patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=hc_reply),
            patch("backend.services.ollama.ask", new_callable=AsyncMock) as mock_ollama,
            patch("backend.services.context.gather", new_callable=AsyncMock, return_value=""),
        ):
            r = client.post("/api/dispatch", json={"query": "hi", "use_context": False, "provider": "auto"})
        assert r.status_code == 200
        mock_ollama.assert_not_called()


class TestWeatherRoute:
    def test_returns_weather_string(self):
        with patch("backend.services.weather.current", new_callable=AsyncMock, return_value="22°C, sunny"):
            r = client.get("/api/weather")
        assert r.status_code == 200
        assert r.json()["weather"] == "22°C, sunny"

    def test_returns_empty_string_when_offline(self):
        with patch("backend.services.weather.current", new_callable=AsyncMock, return_value=""):
            r = client.get("/api/weather")
        assert r.status_code == 200
        assert r.json() == {"weather": ""}

    def test_passes_lat_lon_query_params(self):
        """lat/lon query params are forwarded to weather.current()."""
        mock = AsyncMock(return_value="15°C, rain")
        with patch("backend.services.weather.current", mock):
            r = client.get("/api/weather?lat=51.5&lon=-0.12")
        assert r.status_code == 200
        assert r.json()["weather"] == "15°C, rain"
        mock.assert_awaited_once_with(lat="51.5", lon="-0.12")

    def test_omits_lat_lon_when_not_provided(self):
        """Without query params, weather.current() receives None for lat/lon."""
        mock = AsyncMock(return_value="10°C, cloudy")
        with patch("backend.services.weather.current", mock):
            r = client.get("/api/weather")
        assert r.status_code == 200
        mock.assert_awaited_once_with(lat=None, lon=None)


class TestStreamRoute:
    def test_stream_returns_event_stream(self):
        async def fake_stream(prompt, model=None):
            yield 'data: {"model": "llama3.2"}\n\n'
            yield 'data: {"token": "Hello"}\n\n'
            yield 'data: {"done": true}\n\n'

        with (
            patch("backend.services.ollama.stream", return_value=fake_stream("hi")),
            patch("backend.services.context.gather", new_callable=AsyncMock, return_value=""),
        ):
            r = client.post("/api/stream", json={"query": "hi", "use_context": False, "provider": "ollama"})
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        assert "token" in r.text

    def test_stream_includes_context_event(self):
        ctx = "[Context · Mon · 20°C]"

        async def fake_stream(prompt, model=None):
            yield 'data: {"done": true}\n\n'

        with (
            patch("backend.services.ollama.stream", return_value=fake_stream("hi")),
            patch("backend.services.context.gather", new_callable=AsyncMock, return_value=ctx),
        ):
            r = client.post("/api/stream", json={"query": "hi", "use_context": True, "provider": "ollama"})
        import json as _json
        events = [
            _json.loads(line[6:])
            for line in r.text.splitlines()
            if line.startswith("data: ")
        ]
        ctx_event = next((e for e in events if "context" in e), None)
        assert ctx_event is not None
        assert ctx_event["context"] == ctx


class TestPRsRoute:
    def test_returns_prs_list_and_count(self):
        prs = [
            {"number": 1, "title": "Add feature", "repo": "JARVIS", "url": "https://github.com/u/r/pull/1", "updated_at": "2026-06-07"},
        ]
        with patch("backend.services.github.open_prs", new_callable=AsyncMock, return_value=prs):
            r = client.get("/api/prs")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["prs"][0]["title"] == "Add feature"

    def test_empty_when_no_prs(self):
        with patch("backend.services.github.open_prs", new_callable=AsyncMock, return_value=[]):
            r = client.get("/api/prs")
        assert r.status_code == 200
        assert r.json() == {"prs": [], "count": 0}

    def test_pr_shape(self):
        prs = [{"number": 7, "title": "Fix bug", "repo": "repo", "url": "https://x", "updated_at": "2026-01-01"}]
        with patch("backend.services.github.open_prs", new_callable=AsyncMock, return_value=prs):
            r = client.get("/api/prs")
        item = r.json()["prs"][0]
        assert {"number", "title", "repo", "url", "updated_at"} <= item.keys()


class TestContextRoute:
    def test_returns_context_string(self):
        ctx = "[Context · Sunday · 22°C, partly cloudy]\nNo Todoist tasks available."
        with patch("backend.services.context.gather", new_callable=AsyncMock, return_value=ctx):
            r = client.get("/api/context")
        assert r.status_code == 200
        assert r.json()["context"] == ctx

    def test_context_key_always_present(self):
        with patch("backend.services.context.gather", new_callable=AsyncMock, return_value=""):
            r = client.get("/api/context")
        assert r.status_code == 200
        assert "context" in r.json()


class TestHealthz:
    def test_returns_ok(self):
        r = client.get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /  (frontend)
# ---------------------------------------------------------------------------


class TestFrontend:
    def test_root_serves_html(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "JARVIS" in r.text
