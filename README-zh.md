# Sparkling

> 本地优先的想法、任务与趋势工作台 — AI 自动语义关联、知识图谱与可安装 PWA

[English](./README.md)

## 功能

- **快速录入** — 零摩擦输入框，想法即写即存
- **AI 语义关联** — 自动发现想法之间的关联，支持自动确认 / 建议确认两档阈值
- **知识图谱** — AntV G6 交互式网状图，拖拽浏览想法之间的关联
- **语义搜索** — 自然语言搜索，基于向量相似度
- **任务管理** — 日历视图、待办列表与到期日跟踪
- **Trend 情报** — 汇集 GitHub、Hacker News 和自定义 RSS/Atom 信号，用 AI 评分、摘要、打标并沉淀有效内容
- **定时采集** — 可按本地时区定时运行 Trend，也可随时手动触发
- **单用户访问** — 首次启动注册，使用本地 Cookie session 登录
- **月度活跃热图** — 收件箱热度一览
- **深色 / 浅色 / 跟随系统** — 三种主题模式
- **中文 / 英文切换** — 界面国际化
- **PWA** — 可安装到桌面，离线读取已缓存数据

## 快速开始（Docker）

### 前置条件

- [Docker](https://docs.docker.com/get-docker/) 24+
- [Docker Compose](https://docs.docker.com/compose/install/) v2+

### 1. 克隆项目

```bash
git clone <repo-url> sparkling
cd sparkling
```

### 2. 启动服务

```bash
docker compose up -d
```

首次启动会自动完成：构建镜像 → 安装依赖 → 创建数据库 → 跑迁移 → 启动服务。打开应用后创建本地用户账号即可使用。

### 3. 打开浏览器

```
http://localhost:3721
```

### 4. 查看日志

```bash
docker compose logs -f
```

### 5. 停止服务

```bash
docker compose down
```

## 数据持久化

named volume `sparkling-data` 映射到容器内的 `/data`，其中保存两份 SQLite 数据库：

- `sparkling.db`：想法、任务、关联、向量、Trend 与业务设置
- `control.db`：当前数据库选择、本地用户与 session

```bash
# 查看 volume 位置（macOS 在 Docker Desktop 管理的虚拟磁盘内）
docker volume inspect sparkling-data
```

**升级 / 重建镜像不会丢失数据**——只要不手动删除 volume：

```bash
# 安全升级流程
docker compose down          # 停容器（volume 保留）
docker compose build --no-cache
docker compose up -d          # 启动，原有数据完好

# 如果想彻底清空数据
docker compose down -v        # ⚠️ 同时删除 volume，数据不可恢复
```

### 备份与恢复

```bash
# 同时备份两份数据库
docker cp sparkling:/data/sparkling.db ./sparkling-backup.db
docker cp sparkling:/data/control.db ./control-backup.db

# 恢复（先停止容器）
docker compose stop
docker cp ./sparkling-backup.db sparkling:/data/sparkling.db
docker cp ./control-backup.db sparkling:/data/control.db
docker compose start
```

## 环境变量

全部可选，默认值适用于本地 Docker 部署：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SPARKLING_PORT` | `3721` | 服务监听端口 |
| `SPARKLING_DB_PATH` | `/data/sparkling.db` | 默认 SQLite 文件路径，仅在 control DB 还没有数据库配置时使用 |
| `SPARKLING_CONTROL_DB_PATH` | `/data/control.db` | 固定本地 SQLite 文件，用于保存数据库选择、认证用户和 session |
| `SPARKLING_LOG_DIR` | `/data/logs` | 统一轮转日志目录，保存在 Docker volume 中；可在 Settings → Logs 查看 |
| `SPARKLING_LOG_MAX_FILE_MB` | `10` | 单个 active 或轮转日志文件的最大容量 |
| `SPARKLING_LOG_BACKUP_COUNT` | `9` | `sparkling.log` 和 `error.log` 各自最多保留的 backup 数量 |
| `SPARKLING_LOG_MAX_TOTAL_MB` | `200` | 日志目录总容量上限，超过时从最旧的受管 backup 开始删除 |
| `SPARKLING_HOST` | `0.0.0.0` | 监听地址（Docker 内需要 `0.0.0.0`） |
| `SPARKLING_DEV_ORIGIN` | (空) | 前端 dev server 的 CORS origin |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Uvicorn 信任的反向代理 IP/CIDR；Docker 部署应设置为 OpenResty 所在网段 |

生产环境启动后，在 **Settings → Network / Deployment** 填写浏览器实际访问的 Public URL。该配置保存在固定的 control SQLite 中并立即生效，不需要重启容器；页面会自动生成可复制到 Google Console 的 YouTube OAuth redirect URI。
反向代理不要长期缓存 SPA 入口文件，否则旧 `index.html` 可能引用已经删除的 hash asset。OpenResty/Nginx 建议让 `/index.html`、`/sw.js`、`/registerSW.js` 使用 `no-store`，仅对 `/assets/` 使用一年期 immutable 缓存；缺失 asset 必须返回 404，不能回退到 `index.html`。

应用文件日志默认最多占用 200 MB。Compose 还会将 Docker `json-file` 中的 stdout/stderr 按 10 MB、最多 3 个文件轮转，避免容器日志在 `/data/logs` 之外独立无限增长。

在 `docker-compose.yml` 中修改对应 `environment` 字段。数据库后端选择保存在固定 control SQLite 中；请在页面 **Settings → 数据库** 中切换 SQLite/PostgreSQL，PostgreSQL URL 也保存在那里，不再写入 `.env`。

## AI Provider 配置

Docker 部署后，在页面的 **Settings** 中配置 provider。设置存于当前业务数据库；API Key 读取时会在界面中脱敏显示。

**Embedding（向量嵌入）**
- Base URL — API 地址（如 `https://api.openai.com/v1`）
- API Key — 密钥（可空，本地模型无需）
- 模型名称 — 如 `text-embedding-3-small`
- 维度 — 选定后锁定，切换需重建

**Chat 与 Trend 情报**
- Chat 和 Trend 采集可分别使用独立的 Base URL / API Key / 模型
- 未配置专用 Trend provider 时，Trend 会回退使用 Chat provider
- 内置连通性测试；Trend 信息源支持 GitHub、Hacker News 与自定义 RSS/Atom
- 可设置评分阈值、结果数量与按浏览器时区计算的定时任务

### Trend 使用流程

1. 在 Brand Brain 中描述你关注的主题和信号。
2. 在 **Settings → Trends** 启用 GitHub、Hacker News 和/或自定义 RSS/Atom 信息源。
3. 在 **Trends** 页面手动执行采集，或启用定时运行。
4. Sparkling 会规划搜索 query、去重候选内容，使用配置的 LLM 评分并生成摘要，仅保存达到阈值的内容。

---

## 开发环境

```bash
# 后端（http://127.0.0.1:8000）
cd backend
cp .env.template .env    # 首次克隆后，按需修改
uv run python run.py

# 前端（http://localhost:5173，API/WS 代理到 8000）
cd frontend
pnpm dev

# 数据库迁移
cd backend
uv run alembic revision --autogenerate -m "<描述>"
uv run alembic upgrade head
```

详细说明见 [AGENTS.md](./AGENTS.md)。

## 项目结构

```
sparkling/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + 静态前端挂载
│   │   ├── config.py            # 环境变量配置
│   │   ├── db.py                # 数据库连接管理（SQLite / PostgreSQL）
│   │   ├── models.py            # ORM 模型
│   │   ├── vector_store.py       # sqlite-vec 向量存储
│   │   ├── migrations.py         # 自动迁移
│   │   ├── runtime.py            # 后台 worker 生命周期
│   │   ├── logger.py             # 统一日志（控制台 + 容量受限的轮转文件）
│   │   ├── routers/              # API 路由
│   │   │   ├── atoms.py         # 想法 CRUD + WebSocket 广播
│   │   │   ├── links.py         # 关联查询
│   │   │   ├── search.py        # 语义搜索
│   │   │   ├── graph.py         # 图谱数据
│   │   │   ├── tasks.py         # 任务管理
│   │   │   ├── settings.py      # AI / 数据库配置
│   │   │   ├── trends.py        # Trend 信息流与采集任务
│   │   │   ├── auth.py          # 本地用户与 session 接口
│   │   │   └── ws.py            # WebSocket 实时事件
│   │   ├── services/             # 业务逻辑
│   │   │   ├── ai/              # OpenAI 兼容 Chat 客户端
│   │   │   ├── memory/          # Embedding、关联与清理
│   │   │   ├── settings/        # 运行时数据库配置
│   │   │   ├── trend/           # Trend 采集、信息源与清理
│   │   │   ├── task_queue.py    # 异步任务队列（SQLite）
│   │   │   ├── ws_manager.py    # WebSocket 连接管理
│   │   └── workers/              # 后台任务 worker
│   └── logs/                     # 日志文件（sparkling.log + error.log）
├── frontend/
│   └── src/
│       ├── features/             # 按功能划分的 UI 模块
│       │   ├── memory/           # 收件箱、搜索与想法详情
│       │   ├── graph/            # 知识图谱画布
│       │   ├── tasks/            # 日历与任务列表
│       │   ├── trend/            # Trend 信息流与来源设置
│       │   ├── settings/         # AI、数据库、外观与 Trend 设置
│       │   └── auth/             # 注册、登录与用户资料
│       ├── components/           # 通用组件
│       ├── lib/                  # API / Store / i18n / 主题
│       └── layouts/              # 布局（AppShell + SideNav）
├── docker-compose.yml
├── Dockerfile
└── PLAN.md                       # 完整实施计划
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 / FastAPI / SQLAlchemy / sqlite-vec |
| 前端 | React 19 / Vite / Tailwind / AntV G6 |
| 图标 | lucide-react |
| AI | OpenAI SDK（兼容多家 provider，Embedding + Chat 独立配置） |
| 数据库 | SQLite + sqlite-vec（向量检索），可选 PostgreSQL + pgvector |
| 异步任务 | asyncio + SQLite 任务队列（无 Redis 依赖） |
| 部署 | Docker / Docker Compose |

## License

MIT
