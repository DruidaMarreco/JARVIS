"""Ollama service — local, free LLM inference via the Ollama Python client.

Install Ollama from https://ollama.com, then pull a model:
    ollama pull llama3.2

Configure via env vars:
    OLLAMA_URL   (default: http://localhost:11434)
    OLLAMA_MODEL (default: llama3.2)
"""

from __future__ import annotations

import json
import logging
import os
from typing import AsyncIterator

from ollama import AsyncClient

_log = logging.getLogger(__name__)


def _host() -> str:
    return os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")


def _default_model() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3.2").strip()


async def check() -> dict:
    """Status chip — lists available local models."""
    try:
        client = AsyncClient(host=_host())
        result = await client.list()
        models = getattr(result, "models", None) or []
        count = len(models)
        noun = "model" if count == 1 else "models"
        return {"label": "Ollama", "state": "ok", "detail": f"{count} local {noun}"}
    except Exception as exc:
        _log.debug("ollama.check() failed: %s", exc)
        return {"label": "Ollama", "state": "warn", "detail": "offline"}


async def list_models() -> list[dict]:
    """Return names and sizes of every locally-pulled model."""
    try:
        client = AsyncClient(host=_host())
        result = await client.list()
        models = getattr(result, "models", None) or []
        out: list[dict] = []
        for m in models:
            name: str = getattr(m, "model", None) or "?"
            size: int = getattr(m, "size", None) or 0
            size_gb = round(size / 1_000_000_000, 1) if size else None
            out.append({"name": name, "size_gb": size_gb})
        return out
    except Exception as exc:
        _log.warning("ollama.list_models() failed: %s", exc)
        return []


def _build_messages(prompt: str, history: list[dict]) -> list[dict]:
    """Build a messages array for the Ollama chat API.

    ``history`` items are ``{role, content}`` dicts (same shape as OpenAI).
    The current user prompt is appended last.
    """
    msgs: list[dict] = []
    for h in history:
        role = h.get("role", "")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": prompt})
    return msgs


async def stream(
    prompt: str,
    model: str | None = None,
    history: list[dict] | None = None,
) -> AsyncIterator[str]:
    """Async generator yielding SSE-formatted strings for streaming Ollama responses.

    ``history`` is a list of ``{role, content}`` dicts representing prior turns.
    They are prepended to the messages array so Ollama can reference them.

    Emits:
      data: {"model": "<name>"}      — first, so the UI knows which model is running
      data: {"token": "<chunk>"}     — once per token as they arrive
      data: {"error": "<msg>"}       — on failure
      data: {"done": true}           — always last
    """
    chosen = model or _default_model()
    yield f"data: {json.dumps({'model': chosen})}\n\n"
    messages = _build_messages(prompt, history or [])
    try:
        client = AsyncClient(host=_host())
        async for chunk in await client.chat(
            model=chosen,
            messages=messages,
            stream=True,
        ):
            msg = getattr(chunk, "message", None)
            token: str = getattr(msg, "content", "") if msg is not None else ""
            if token:
                yield f"data: {json.dumps({'token': token})}\n\n"
    except Exception as exc:
        _log.warning("ollama.stream() failed (model=%s): %s", chosen, exc)
        yield f"data: {json.dumps({'error': str(exc)})}\n\n"
    yield f"data: {json.dumps({'done': True})}\n\n"


async def ask(prompt: str, model: str | None = None) -> dict:
    """Send a prompt to a local Ollama model and return {reply, events, model}."""
    chosen = model or _default_model()
    try:
        client = AsyncClient(host=_host())
        response = await client.chat(
            model=chosen,
            messages=[{"role": "user", "content": prompt}],
        )
        msg = getattr(response, "message", None)
        reply: str = getattr(msg, "content", str(response)) if msg is not None else str(response)
        return {"reply": reply, "events": [], "model": chosen}
    except Exception as exc:
        _log.warning("ollama.ask() failed (model=%s): %s", chosen, exc)
        return {"reply": f"Ollama error: {exc}", "error": "ollama_error", "model": chosen}
