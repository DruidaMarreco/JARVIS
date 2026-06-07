"""Route-level tests using FastAPI's TestClient (synchronous, offline).

Services are mocked so no real network calls are made. These tests verify
that the routing layer correctly wires requests to services and serialises
responses.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
            r = client.post("/api/dispatch", json={"query": "Hello"})
        assert r.status_code == 200
        assert r.json()["reply"] == "Hello from Claude"
        mock_ask.assert_called_once_with("Hello", mode="default")

    def test_forwards_mode_to_heyclaude(self):
        reply = {"reply": "Deep analysis", "events": []}
        with patch("backend.services.heyclaude.ask", new_callable=AsyncMock, return_value=reply) as mock_ask:
            r = client.post("/api/dispatch", json={"query": "Explain entropy", "mode": "researcher"})
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


# ---------------------------------------------------------------------------
# GET /  (frontend)
# ---------------------------------------------------------------------------


class TestFrontend:
    def test_root_serves_html(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "JARVIS" in r.text
