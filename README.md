# JARVIS — Central Interface

[![CI](https://github.com/DruidaMarreco/JARVIS/actions/workflows/ci.yml/badge.svg)](https://github.com/DruidaMarreco/JARVIS/actions/workflows/ci.yml)

Personal ops deck and agentic assistant hub. One place to open every tool, with a live command bar powered by [Hey Claude](https://github.com/DruidaMarreco/hey-claude) and real-time status from connected services.

---

## What it does

- **Module launcher** — grouped tiles for every tool you use daily (Claude, Todoist, GitHub, Notion, Strava, …)
- **Live status** — status chips loaded from real APIs on every page load (Hey Claude ping, Todoist task count, GitHub repo count)
- **Command bar** — type a question, hit Enter, get a reply from Hey Claude without leaving the page
- **Mode selector** — switch Hey Claude's persona per query: Voice, Researcher, Coder, Creative, Productivity, Coach
- **Single-file frontend** — one `index.html`, no build step, no framework

---

## Architecture

```
Browser (localhost:7000)
        │
        ▼
┌───────────────────────────────────────────┐
│              JARVIS  :7000                │
│                                           │
│  GET  /                  → frontend/      │
│  GET  /api/status        → parallel fan-  │
│  GET  /api/modes         │  out to        │
│  POST /api/dispatch      │  downstream    │
│                          │  services      │
└──────────────────────────┼────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
   Hey Claude :8000   Todoist API     GitHub API
   GET /api/modes     /rest/v2/tasks  /users/:user
   POST /api/ask
```

JARVIS is a **thin proxy and launcher**. It holds no state and calls no AI directly — all intelligence lives in Hey Claude.

---

## Quick start

**Prerequisites:** Python 3.10+, [uv](https://docs.astral.sh/uv/getting-started/installation/), a running instance of [Hey Claude web](https://github.com/DruidaMarreco/hey-claude).

```bash
git clone https://github.com/DruidaMarreco/JARVIS.git
cd JARVIS

# 1. Install dependencies
uv sync

# 2. Configure secrets
cp .env.example .env
#    → edit .env and add TODOIST_API_TOKEN

# 3. Start Hey Claude (in a separate terminal)
cd ../Hey\ Claude && hey-claude-web   # → http://localhost:8000

# 4. Start JARVIS
make dev   # → http://localhost:7000
```

Open `http://localhost:7000`. Status chips load live, the mode selector populates from Hey Claude, and the command bar is ready.

---

## Configuration

All settings are read from the environment (`.env` file or shell exports).

| Variable | Default | Description |
|---|---|---|
| `TODOIST_API_TOKEN` | _(empty)_ | Personal API token from Todoist → Settings → Integrations → Developer. Without it the Todoist chip shows "idle". |
| `GITHUB_USERNAME` | `DruidaMarreco` | GitHub username for the public profile stats chip. No token required (public API). |
| `HEYCLAUDE_URL` | `http://localhost:8000` | Base URL of the running Hey Claude web server. Change if you run it on a different port or host. |

---

## Mode system

Hey Claude's persona is selected per query. Modes are defined in Hey Claude's [`modes.py`](https://github.com/DruidaMarreco/hey-claude) and exposed via `GET /api/modes`. JARVIS fetches them on load — add a new mode in Hey Claude and it appears in JARVIS automatically.

| Mode | Icon | Behaviour |
|---|---|---|
| Voice | ◉ | Default. Concise, natural, no markdown. |
| Researcher | ⊕ | Analytical, traces causes, uses structured output. Asks a follow-up if the query needs it. |
| Coder | ⌬ | Technical precision. Code blocks, before/after diffs, flags edge cases. |
| Creative | ◈ | Lateral thinking, vivid language, multiple variations on request. |
| Productivity | ✓ | GTD-style. Leads with concrete next steps as a bullet list. |
| Coach | ◆ | Socratic. Asks one focused question before advising. |

Modes switch per-request with no restart. The reply panel header shows which persona answered.

---

## API reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serves `frontend/index.html` |
| `GET` | `/api/status` | Returns live status chips for Hey Claude, Todoist, GitHub |
| `GET` | `/api/modes` | Proxies Hey Claude's mode registry |
| `POST` | `/api/dispatch` | Sends `{query, mode}` to Hey Claude; returns `{reply, events, cost}` |

### `/api/dispatch` request body

```json
{ "query": "Explain the CAP theorem", "mode": "researcher" }
```

### Status chip shape

```json
{ "label": "Todoist", "state": "ok", "detail": "5 tasks today" }
```

`state` is one of `"ok"` · `"warn"` · `"idle"`.

---

## Adding modules

Edit the `APPS` array in [`frontend/index.html`](frontend/index.html). Each entry is one tile:

```js
{ group: "Build", icon: "⌬", name: "My Tool", desc: "Short description", url: "https://..." }
```

Add a new `group` value and it gets its own section automatically. Order follows the `ORDER` array at the top of the script block.

---

## Development

```bash
make install   # uv sync
make dev       # uvicorn --reload on :7000
make lint      # ruff + black check
make fmt       # ruff fix + black format
make test      # pytest (offline, no API keys needed)
```

Tests use `fastapi.testclient.TestClient` (sync) and `unittest.mock` — no external services required. All 26 tests run in under 10 seconds.

---

## Project layout

```
JARVIS/
├── backend/
│   ├── main.py              # FastAPI app, mounts frontend at /
│   ├── routers/
│   │   ├── status.py        # GET /api/status — fan-out to services
│   │   └── dispatch.py      # GET /api/modes, POST /api/dispatch
│   └── services/
│       ├── todoist.py       # Todoist REST API check
│       ├── github.py        # GitHub public API check
│       └── heyclaude.py     # Hey Claude ping, ask, modes proxy
├── frontend/
│   └── index.html           # Single-file UI — clock, status, tiles, command bar
├── tests/
│   ├── test_services.py     # Unit tests for each service function
│   └── test_routes.py       # Route-level tests with mocked services
├── .github/workflows/
│   └── ci.yml               # lint → typecheck → compile → test
├── .env.example
├── Makefile
├── pyproject.toml
└── ruff.toml
```
