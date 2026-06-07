# JARVIS — Claude Code notes

## What this is

JARVIS is the central interface for Simão's personal toolchain. It is a FastAPI
backend (`:7000`) that serves a single-file frontend dashboard, proxies live
status from connected services, and routes command bar queries to Hey Claude
(`:8000`).

This repo deliberately stays thin: no database, no auth, no AI calls of its own.
All intelligence goes through Hey Claude.

## Run / test

```
make dev       # uvicorn --reload on localhost:7000
make test      # pytest tests/ (all offline, ~7 s)
make lint      # ruff + black check
make fmt       # ruff fix + black format
```

Hey Claude must be running on `:8000` for the command bar and mode selector to
work. Start it with `hey-claude-web` in the Hey Claude project. JARVIS degrades
gracefully when Hey Claude is offline (status chip shows "idle", mode row hides).

## Architecture rules

- **No state.** JARVIS holds nothing in memory between requests. Every call fans
  out to a downstream service and returns.
- **Services are the boundary.** All external I/O lives in `backend/services/`.
  Routers call services; services call httpx. Tests mock at the service level.
- **Frontend is a single file.** `frontend/index.html` has no build step. Keep
  it that way unless the complexity genuinely demands a bundler.
- **Modes live in Hey Claude.** `GET /api/modes` proxies from Hey Claude — do
  not duplicate the mode registry here.

## Key files

| File | Role |
|---|---|
| `backend/main.py` | App factory, loads `.env`, mounts routers |
| `backend/routers/status.py` | `asyncio.gather` fan-out to all services |
| `backend/routers/dispatch.py` | Modes proxy + Hey Claude dispatch |
| `backend/services/heyclaude.py` | Ping, ask (with mode), modes list |
| `backend/services/todoist.py` | Today's task count via Todoist REST v2 |
| `backend/services/github.py` | Public repo count via GitHub API |
| `frontend/index.html` | Clock, greeting, status chips, mode pills, tile grid, reply panel |

## Conventions

- Line length: **100** (black + ruff, matches the rest of this toolchain)
- Type checker: **ty** (`uv run ty check backend --error all`)
- No `# type: ignore` without a comment explaining why
- Async all the way down in services; `TestClient` (sync) in tests

## Adding a service status chip

1. Create `backend/services/myservice.py` with `async def check() -> dict`.
   Return `{"label": "…", "state": "ok"|"warn"|"idle", "detail": "…"}`.
2. Import it in `backend/routers/status.py` and add it to the `asyncio.gather`
   call.
3. Add the env var(s) to `.env.example` and `README.md`.
4. Write unit tests in `tests/test_services.py`.

## Adding a tile / module

Edit the `APPS` array in `frontend/index.html`. Each entry is:
```js
{ group: "Build", icon: "⌬", name: "My Tool", desc: "…", url: "https://…" }
```
New groups are auto-rendered in the order they appear in the `ORDER` array.

## CI

GitHub Actions runs on push to `main`/`dev` and on all PRs:
1. **lint** — ruff + black (fail fast)
2. **typecheck** — ty with `--error all`
3. **compile** — byte-compile on py 3.10, 3.11, 3.12
4. **test** — pytest (needs lint + typecheck to pass first)
