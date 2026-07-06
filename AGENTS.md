# Sparkling — Claude Code 项目说明

本地优先的碎片想法管理工具。AI 自动语义关联 + 网状图可视化 + PWA 移动端。

## 当前阶段

**MVP — Web 版（自托管单用户）+ PWA**。桌面端（Tauri）与局域网 mDNS 同步延后到 Phase 2/3。完整方案见 [PLAN.md](./PLAN.md)。

## 仓库结构

### 后端（Python）

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口，挂载静态前端
│   ├── routers/
│   │   ├── atoms.py         # 想法 CRUD + WebSocket 广播
│   │   ├── links.py         # 关联查询
│   │   ├── search.py        # 语义搜索（pgvector / SQLite VSS）
│   │   ├── auth.py          # JWT 认证（Web 版）
│   │   └── sync.py          # 局域网同步端点
│   ├── services/
│   │   ├── embedding.py     # OpenAI text-embedding-3-small 调用
│   │   ├── linker.py        # 关联发现算法
│   │   └── merger.py        # 冲突合并逻辑
│   ├── worker/
│   │   ├── tasks.py         # ARQ 异步任务
│   │   └── worker.py        # Worker 启动入口
│   └── sync/
│       ├── discovery.py     # mDNS 广播与发现（zeroconf）
│       ├── server.py        # HTTP sync server
│       └── client.py        # 主动推送给对端
├── alembic/                 # 数据库迁移
└── run.py                   # 启动入口，打印局域网地址
```

### 前端（React）

```
frontend/
├── app/
│   ├── inbox/               # 收件箱主页（快速录入 + 卡片列表）
│   ├── graph/               # 网状图（React Flow）
│   ├── atom/[id]/           # 想法详情 + AI 关联面板
│   ├── search/              # 语义搜索
│   └── (auth)/              # 登录 / 注册（Web 版）
├── components/
│   ├── quick-input.tsx      # 零摩擦输入框（支持语音）
│   ├── atom-card.tsx        # 想法卡片（含 AI 关联角标）
│   ├── graph-canvas.tsx     # React Flow 画布
│   └── link-suggest.tsx     # AI 关联建议确认卡片
└── lib/
    ├── api.ts               # baseURL 读环境变量，fallback localhost:8000
    ├── store.ts             # Zustand 全局状态
    └── useSync.ts           # WebSocket 实时同步 Hook
```

### 桌面端（Tauri）

```
src-tauri/
├── src/main.rs              # 启动 Python 子进程，系统托盘，生命周期管理
└── tauri.conf.json          # 打包配置，resources 包含 Python 可执行文件
```

## 启动 / 开发

```bash
# 后端（http://127.0.0.1:8000）
cd backend
uv run python run.py

# 数据库迁移
cd backend
uv run alembic revision --autogenerate -m "<desc>"
uv run alembic upgrade head

# 前端（http://localhost:5173，API/WS 自动代理到 8000）
cd frontend
pnpm dev
```

## 关键设计约定

- **数据库**：SQLite + sqlite-vec。业务表走 SQLAlchemy；向量虚表 `vec_atoms` 在 Settings 写入 `embed_dim` 后由 `services/embedding.py` 动态 CREATE，**SQLAlchemy 不管它**。
- **AI Provider**：统一使用 `openai` Python SDK，通过 `base_url` 适配多家（OpenAI / DeepSeek / 智谱 / Ollama 等）。配置存 `settings` 表，运行时从数据库读。
- **Embedding 维度锁定**：用户选定 provider 后维度写入 `settings.embed_dim` 并锁定。切换 provider 走 `POST /api/settings/rebuild-embeddings` 重建（drop + recreate vec_atoms + 重新 embed 全部 atom）。
- **异步任务**：用 `task_queue` SQLite 表 + asyncio worker（lifespan 内 `create_task`），**不引入 Redis**。任务类型：`embed`、`link_discover`、`recluster`。
- **关联阈值**：`>= link_threshold_auto` 自动确认；`[link_threshold_suggest, link_threshold_auto)` 作为建议；低于 suggest 丢弃。
- **乐观锁**：`thought_atom.version` 字段，PATCH 时校验，冲突返回 409。
- **WebSocket**：单 channel `/ws`，事件 `atom.created` / `atom.updated` / `link.created` / `link.suggested` / `link.confirmed`。
- **PWA (MVP)**：仅离线读取 `/api/atoms`、`/api/graph`（StaleWhileRevalidate）；写操作离线时前端提示「需联网」。**不做离线写入**。
- **部署形态**：自托管单用户，默认监听 127.0.0.1。**无 auth/JWT/多租户**。

## 编码约定

- 后端：函数式优先，业务逻辑用 `Result`/异常分层（HTTPException 仅在 router 层抛出）。中文注释关键逻辑。
- 前端：组件函数式，状态用 Zustand。命名 camelCase。样式 Tailwind 原子类，避免 `App.css` 等全局样式残留。
- **不提交** `console.log` / `debugger` / 调试代码。
- 提交前手动执行：后端 `uv run ruff check`（如已配置）；前端 `pnpm exec tsc --noEmit && pnpm build`。

## 目录分组约定

1. 同一功能模块达到 2 个或以上文件时，应放入对应子目录，避免继续堆在根层。
2. 后端 `backend/app/services/` 按功能分组，例如 `memory/`、`ai/`、`settings/`、`trend/`；只有单文件模块可以暂留在 `services/` 根层。
3. 前端业务页面和强业务组件优先放入 `frontend/src/features/<module>/`；跨功能复用 UI 才放在 `frontend/src/components/`，跨功能基础设施放在 `frontend/src/lib/`。
4. 移动文件时必须同步更新所有 import，不保留临时兼容 re-export 层；完成后运行后端 compile/ruff 和前端 tsc/build。

## 不在 MVP 范围内

- 局域网 mDNS 同步 / 多设备 sync_log（Phase 3）
- Tauri 桌面打包（Phase 3）
- 语音 / 图片 / URL 想法类型，主题聚类（Phase 2）
- 多用户登录，PWA 离线写入（不做）

## 环境变量（可选）

```bash
SPARKLING_DB_PATH=~/.sparkling/sparkling.db   # SQLite 路径
SPARKLING_HOST=127.0.0.1
SPARKLING_PORT=8000
SPARKLING_DEV_ORIGIN=http://localhost:5173    # 前端 dev server CORS
```

AI Provider 的 `base_url` / `api_key` / 模型 / 维度由用户在前端 Settings 页面录入，**不走环境变量**，便于换号。

尽量使用已有的组件库，不要重复造轮子

## 数据库设计

1. 本地sqlite数据库始终存在，用于基础数据（例如数据库地址设置/AI provider设置）持久化
2. 数据库支持热切换

## 时间管理

1. 数据库中的 `datetime` 一律按 UTC 存储；SQLite 读出的 naive datetime 也必须按 UTC 解释。
2. API 返回用户可见时间时必须使用带时区的 ISO 字符串，例如 `2026-07-03T02:00:00Z`，统一通过 `backend/app/time_utils.py` 序列化。
3. 前端展示时间一律使用浏览器本地时区，例如 `new Date(iso)` + `Intl.DateTimeFormat`；不要用 `toISOString().slice(0, 10)` 做本地日期展示或统计。
4. 用户输入的“每天几点 / 每周几点”属于用户本地时间；前端提交浏览器 IANA timezone（例如 `Asia/Shanghai`），后端按该 timezone 计算后转换为 UTC 存库。
5. 全天日期字段（例如 task `start_date` / `due_date`）是日期语义，不参与时区转换。

## AI设计

* embedding相关功能使用设置的embedding模型：
* 对话和其他功能使用设置好的Chat模型：
