# Sparkling

> 本地优先的碎片想法管理工具 — AI 自动语义关联 + 网状图可视化 + PWA 移动端

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
| `SPARKLING_DB_BACKEND` | `sqlite` | 数据库后端：`sqlite` 或 `postgresql` |
| `SPARKLING_DB_PATH` | `/data/sparkling.db` | SQLite 文件路径 |
| `SPARKLING_POSTGRESQL_URL` | (空) | PostgreSQL 连接串，例如 `postgresql://user:pass@host:5432/sparkling` |
| `SPARKLING_HOST` | `0.0.0.0` | 监听地址（Docker 内需要 `0.0.0.0`） |
| `SPARKLING_DEV_ORIGIN` | (空) | 前端 dev server 的 CORS origin |

在 `docker-compose.yml` 中修改对应 `environment` 字段。也可以在页面 **Settings → 数据库** 中切换 SQLite/PostgreSQL；保存后需要重启后端服务才会生效。

## AI Provider 配置

Docker 部署后，在页面的 **Settings** 中填写：

- **Base URL**：API 地址（如 `https://api.openai.com/v1`）
- **API Key**：你的密钥
- **模型名称**：用于 embedding 的模型（如 `text-embedding-3-small`）

这些配置存储在 SQLite 的 `settings` 表中，随 volume 持久化。

---

## 开发环境

```bash
# 后端（http://127.0.0.1:3721）
cd backend
cp .env.template .env    # 首次克隆后
uv run python run.py

# 前端（http://localhost:5173，API/WS 代理到 3721）
cd frontend
pnpm dev

# 数据库迁移
cd backend
uv run alembic revision --autogenerate -m "<描述>"
uv run alembic upgrade head
```

详细说明见 [AGENTS.md](./AGENTS.md)。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 / FastAPI / SQLAlchemy / sqlite-vec |
| 前端 | React 19 / Vite / Tailwind / React Flow |
| AI | OpenAI SDK（兼容多家 provider） |
| 数据库 | SQLite + sqlite-vec（向量检索） |
| 部署 | Docker / Docker Compose |

## License

MIT
