.PHONY: install dev test lint fmt

install:
	uv sync

dev:
	uv run uvicorn backend.main:app --reload --port 7000

test:
	uv run pytest tests/ -q

lint:
	uv run ruff check backend tests
	uv run black --check backend tests
	uv run ty check backend --error all

fmt:
	uv run black backend tests
	uv run ruff check --fix backend tests
