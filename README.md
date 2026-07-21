# Sparkling

> A local-first workspace for thoughts, tasks, and curated trends — AI-powered semantic linking, knowledge graphs, and an installable PWA.

[中文说明](./README-zh.md)

## Features

- **Quick capture** — Zero-friction input, jot down thoughts instantly
- **AI semantic linking** — Auto-discover connections between thoughts with auto-confirm / suggest two-tier thresholds
- **Knowledge graph** — AntV G6 interactive network graph, drag to explore thought relationships
- **Semantic search** — Natural language search powered by vector similarity
- **Task management** — Calendar view, todo list, and due-date tracking
- **Trend intelligence** — Collect GitHub, Hacker News, and custom RSS/Atom signals; use AI to score, summarize, tag, and retain the useful items
- **Scheduled trend runs** — Run collection on a local-time schedule, or trigger it on demand
- **Single-user access** — First-run registration and cookie-based local sessions
- **Monthly activity heatmap** — Inbox activity at a glance
- **Dark / Light / System** — Three theme modes
- **Chinese / English** — UI internationalization
- **PWA** — Installable to desktop, offline reading of cached data

## Quick Start (Docker)

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 24+
- [Docker Compose](https://docs.docker.com/compose/install/) v2+

### 1. Clone

```bash
git clone <repo-url> sparkling
cd sparkling
```

### 2. Start

```bash
docker compose up -d
```

On first start, Sparkling builds the image, installs dependencies, creates its databases, runs migrations, and starts the service. Open the app and create the local user account.

### 3. Open

```
http://localhost:3721
```

### 4. View logs

```bash
docker compose logs -f
```

### 5. Stop

```bash
docker compose down
```

## Data Persistence

The named volume `sparkling-data` is mounted at `/data`. It stores both SQLite files:

- `sparkling.db` — thoughts, tasks, links, vectors, trends, and application settings
- `control.db` — selected database configuration, the local user, and sessions

```bash
# View volume location (macOS: inside Docker Desktop's managed virtual disk)
docker volume inspect sparkling-data
```

**Upgrading or rebuilding the image will not lose data** — as long as you don't manually delete the volume:

```bash
# Safe upgrade workflow
docker compose down          # stop containers (volume preserved)
docker compose build --no-cache
docker compose up -d          # start with existing data intact

# To wipe all data
docker compose down -v        # ⚠️ also deletes volume, data unrecoverable
```

### Backup & Restore

```bash
# Backup both databases
docker cp sparkling:/data/sparkling.db ./sparkling-backup.db
docker cp sparkling:/data/control.db ./control-backup.db

# Restore (with the container stopped)
docker compose stop
docker cp ./sparkling-backup.db sparkling:/data/sparkling.db
docker cp ./control-backup.db sparkling:/data/control.db
docker compose start
```

## Environment Variables

All optional, defaults suitable for local Docker deployment:

| Variable | Default | Description |
|---|---|---|
| `SPARKLING_PORT` | `3721` | Server listen port |
| `SPARKLING_DB_PATH` | `/data/sparkling.db` | Default SQLite file path used only when control DB has no database config yet |
| `SPARKLING_CONTROL_DB_PATH` | `/data/control.db` | Fixed local SQLite file for database selection, auth user, and sessions |
| `SPARKLING_HOST` | `0.0.0.0` | Listen address (`0.0.0.0` required inside Docker) |
| `SPARKLING_DEV_ORIGIN` | (empty) | CORS origin for frontend dev server |

Modify the corresponding `environment` fields in `docker-compose.yml`. Database backend selection is stored in the fixed control SQLite database. Switch between SQLite/PostgreSQL on the **Settings → Database** page; PostgreSQL URLs are saved there, not in `.env`.

## AI Provider Configuration

After deployment, configure providers on the **Settings** page. Values are stored in the active business database; secrets are masked when they are read back by the UI.

**Embedding**
- Base URL — API endpoint (e.g. `https://api.openai.com/v1`)
- API Key — your key (can be empty for local models)
- Model — e.g. `text-embedding-3-small`
- Dimension — locked once set; switching requires a rebuild

**Chat and Trend intelligence**
- Chat and Trend collection may use independent Base URL / API Key / Model settings
- Trend collection falls back to the Chat provider when no dedicated Trend provider is configured
- Built-in connectivity tests; Trend sources can include GitHub, Hacker News, and custom RSS/Atom feeds
- Configure a score threshold, result limit, and a browser-timezone-aware schedule

### Trend workflow

1. Write a Brand Brain prompt describing the topics and signals you care about.
2. Enable GitHub, Hacker News, and/or custom RSS/Atom sources in **Settings → Trends**.
3. Run collection from the **Trends** page or enable a schedule.
4. Sparkling plans source queries, deduplicates candidates, uses the configured LLM to score and summarize them, and saves items meeting the configured threshold.

---

## Development

```bash
# Backend (http://127.0.0.1:8000)
cd backend
cp .env.template .env    # after first clone, edit as needed
uv run python run.py

# Frontend (http://localhost:5173, API/WS proxied to 8000)
cd frontend
pnpm dev

# Database migrations
cd backend
uv run alembic revision --autogenerate -m "<description>"
uv run alembic upgrade head
```

See [AGENTS.md](./AGENTS.md) for detailed development guide.

## Project Structure

```
sparkling/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point + static frontend serving
│   │   ├── config.py            # Environment variable configuration
│   │   ├── db.py                # DB connection management (SQLite / PostgreSQL)
│   │   ├── models.py            # ORM models
│   │   ├── vector_store.py       # sqlite-vec vector store
│   │   ├── migrations.py         # Auto-migration runner
│   │   ├── runtime.py            # Background worker lifecycle
│   │   ├── logger.py             # Unified logging (console + daily rotated files)
│   │   ├── routers/              # API routes
│   │   │   ├── atoms.py         # Thought CRUD + WebSocket broadcast
│   │   │   ├── links.py         # Link queries
│   │   │   ├── search.py        # Semantic search
│   │   │   ├── graph.py         # Graph data
│   │   │   ├── tasks.py         # Task management
│   │   │   ├── settings.py      # AI / DB configuration
│   │   │   ├── trends.py        # Trend feed and collection runs
│   │   │   ├── auth.py          # Local user and session endpoints
│   │   │   └── ws.py            # WebSocket real-time events
│   │   ├── services/             # Business logic
│   │   │   ├── ai/              # OpenAI-compatible chat client
│   │   │   ├── memory/          # Embeddings, links, and cleanup
│   │   │   ├── settings/        # Runtime database configuration
│   │   │   ├── trend/           # Trend collection, sources, and cleanup
│   │   │   ├── task_queue.py    # Async task queue (SQLite)
│   │   │   ├── ws_manager.py    # WebSocket connection manager
│   │   └── workers/              # Background task workers
│   └── logs/                     # Log files (sparkling.log + error.log)
├── frontend/
│   └── src/
│       ├── features/             # Feature-oriented UI modules
│       │   ├── memory/           # Inbox, search, and thought details
│       │   ├── graph/            # Knowledge graph canvas
│       │   ├── tasks/            # Calendar and task list
│       │   ├── trend/            # Trend feed and source settings
│       │   ├── settings/         # AI, database, appearance, and trend settings
│       │   └── auth/             # Registration, login, and user profile
│       ├── components/           # Shared components
│       ├── lib/                  # API / Store / i18n / Theme
│       └── layouts/              # Layout (AppShell + SideNav)
├── docker-compose.yml
├── Dockerfile
└── PLAN.md                       # Full implementation plan
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 / FastAPI / SQLAlchemy / sqlite-vec |
| Frontend | React 19 / Vite / Tailwind / AntV G6 |
| Icons | lucide-react |
| AI | OpenAI SDK (multi-provider compatible, Embedding + Chat independent config) |
| Database | SQLite + sqlite-vec (vector search), optional PostgreSQL + pgvector |
| Async tasks | asyncio + SQLite task queue (no Redis dependency) |
| Deployment | Docker / Docker Compose |

## License

MIT
