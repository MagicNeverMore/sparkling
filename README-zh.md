# Sparkling

> 本地优先的碎片想法管理工具 — AI 自动语义关联 + 知识图谱可视化 + PWA 移动端

[English](./README.md)

## 功能

- **快速录入** — 零摩擦输入框，想法即写即存
- **AI 语义关联** — 自动发现想法之间的关联，支持自动确认 / 建议确认两档阈值
- **知识图谱** — AntV G6 交互式网状图，拖拽浏览想法之间的关联
- **语义搜索** — 自然语言搜索，基于向量相似度
- **任务管理** — 日历视图 + 待办列表，支持到期提醒
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

首次启动会自动完成：构建镜像 → 安装依赖 → 创建数据库 → 跑迁移 → 启动服务。

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

SQLite 数据库文件存放在 **named volume** `sparkling-data` 中，映射到容器内的 `/data/sparkling.db`。

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
# 备份
docker compose exec sparkling cp /data/sparkling.db /data/sparkling.db.bak
docker cp sparkling:/data/sparkling.db ./sparkling-backup.db

# 恢复（停掉容器后）
docker cp ./sparkling-backup.db sparkling:/data/sparkling.db
docker compose restart
```

## 环境变量

全部可选，默认值适用于本地 Docker 部署：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `SPARKLING_PORT` | `3721` | 服务监听端口 |
| `SPARKLING_DB_PATH` | `/data/sparkling.db` | 默认 SQLite 文件路径，仅在 control DB 还没有数据库配置时使用 |
| `SPARKLING_CONTROL_DB_PATH` | `/data/control.db` | 固定本地 SQLite 文件，用于保存数据库选择、认证用户和 session |
| `SPARKLING_HOST` | `0.0.0.0` | 监听地址（Docker 内需要 `0.0.0.0`） |
| `SPARKLING_DEV_ORIGIN` | (空) | 前端 dev server 的 CORS origin |

在 `docker-compose.yml` 中修改对应 `environment` 字段。数据库后端选择保存在固定 control SQLite 中；请在页面 **Settings → 数据库** 中切换 SQLite/PostgreSQL，PostgreSQL URL 也保存在那里，不再写入 `.env`。

## AI Provider 配置

Docker 部署后，在页面的 **Settings** 中分别配置 Embedding 和 Chat 两个 provider：

**Embedding（向量嵌入）**
- Base URL — API 地址（如 `https://api.openai.com/v1`）
- API Key — 密钥（可空，本地模型无需）
- 模型名称 — 如 `text-embedding-3-small`
- 维度 — 选定后锁定，切换需重建

**Chat（对话补全，预留）**
- 独立的 Base URL / API Key / 模型
- 内置连通性测试按钮

这些配置存储在 SQLite 的 `settings` 表中，随 volume 持久化。

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
│   │   ├── logger.py             # 统一日志（控制台 + 按日轮转文件）
│   │   ├── routers/              # API 路由
│   │   │   ├── atoms.py         # 想法 CRUD + WebSocket 广播
│   │   │   ├── links.py         # 关联查询
│   │   │   ├── search.py        # 语义搜索
│   │   │   ├── graph.py         # 图谱数据
│   │   │   ├── tasks.py         # 任务管理
│   │   │   ├── settings.py      # AI / 数据库配置
│   │   │   └── ws.py            # WebSocket 实时事件
│   │   ├── services/             # 业务逻辑
│   │   │   ├── embedding.py     # Embedding 调用 + 维度锁定
│   │   │   ├── linker.py        # 关联发现（KNN + 阈值分流）
│   │   │   ├── chat.py          # Chat provider
│   │   │   ├── task_queue.py    # 异步任务队列（SQLite）
│   │   │   ├── ws_manager.py    # WebSocket 连接管理
│   │   │   ├── cleanup.py       # 软删除清理
│   │   │   └── runtime_config.py # 运行时数据库配置
│   │   └── workers/              # 后台任务 worker
│   └── logs/                     # 日志文件（sparkling.log + error.log）
├── frontend/
│   └── src/
│       ├── pages/                # 页面
│       │   ├── Inbox.tsx         # 收件箱（快速录入 + 卡片流 + 热图）
│       │   ├── Graph.tsx         # 知识图谱
│       │   ├── Search.tsx        # 语义搜索
│       │   ├── Tasks.tsx         # 任务管理（日历 + 列表）
│       │   ├── Settings.tsx      # 设置（AI / 数据库 / 外观）
│       │   └── AtomDetail.tsx    # 想法详情 + AI 关联面板
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
