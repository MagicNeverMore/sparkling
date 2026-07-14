# Sparkling

> Local-first fragmented thought manager — AI-powered semantic linking + knowledge graph visualization + PWA mobile

[中文说明](./README-zh.md)

## Features

- **Quick capture** — Zero-friction input, jot down thoughts instantly
- **AI semantic linking** — Auto-discover connections between thoughts with auto-confirm / suggest two-tier thresholds
- **Knowledge graph** — AntV G6 interactive network graph, drag to explore thought relationships
- **Semantic search** — Natural language search powered by vector similarity
- **Task management** — Calendar view + todo list with due-date reminders
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

First start will automatically: build image → install dependencies → create database → run migrations → start services.

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

The SQLite database file is stored in the **named volume** `sparkling-data`, mounted at `/data/sparkling.db` inside the container.

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
# Backup
docker compose exec sparkling cp /data/sparkling.db /data/sparkling.db.bak
docker cp sparkling:/data/sparkling.db ./sparkling-backup.db

# Restore (after stopping the container)
docker cp ./sparkling-backup.db sparkling:/data/sparkling.db
docker compose restart
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

After Docker deployment, configure Embedding and Chat providers separately on the **Settings** page:

**Embedding**
- Base URL — API endpoint (e.g. `https://api.openai.com/v1`)
- API Key — your key (can be empty for local models)
- Model — e.g. `text-embedding-3-small`
- Dimension — locked once set; switching requires a rebuild

**Chat (reserved)**
- Independent Base URL / API Key / Model
- Built-in connectivity test button

These settings are stored in the `settings` table in SQLite and persist with the volume.

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
│   │   │   └── ws.py            # WebSocket real-time events
│   │   ├── services/             # Business logic
│   │   │   ├── embedding.py     # Embedding calls + dimension locking
│   │   │   ├── linker.py        # Link discovery (KNN + threshold routing)
│   │   │   ├── chat.py          # Chat provider
│   │   │   ├── task_queue.py    # Async task queue (SQLite)
│   │   │   ├── ws_manager.py    # WebSocket connection manager
│   │   │   ├── cleanup.py       # Soft-delete cleanup
│   │   │   └── runtime_config.py # Runtime DB configuration
│   │   └── workers/              # Background task workers
│   └── logs/                     # Log files (sparkling.log + error.log)
├── frontend/
│   └── src/
│       ├── pages/                # Pages
│       │   ├── Inbox.tsx         # Inbox (quick input + card stream + heatmap)
│       │   ├── Graph.tsx         # Knowledge graph
│       │   ├── Search.tsx        # Semantic search
│       │   ├── Tasks.tsx         # Task management (calendar + list)
│       │   ├── Settings.tsx      # Settings (AI / DB / appearance)
│       │   └── AtomDetail.tsx    # Thought detail + AI link suggestions
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
