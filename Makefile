.PHONY: install dev lint fmt

install:
	uv sync

dev:
	uv run uvicorn backend.main:app --reload --port 7000

lint:
	uv run ruff check backend
	uv run ty check backend

fmt:
	uv run black backend
	uv run ruff check --fix backend
