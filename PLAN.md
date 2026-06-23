# Sparkling 实施计划 (MVP — Web 版 + PWA)

## 背景

Sparkling 是一款本地优先的碎片想法管理工具，核心差异化在于 **AI 自动语义关联** 与 **网状图可视化**。本计划聚焦 MVP：先做自托管单用户的 Web 版（含 PWA 移动安装与基础离线），验证「快速录入 → 自动关联 → 网状图浏览」核心闭环。桌面端（Tauri）与局域网同步延后到 Phase 2/3。

### 已对齐的关键决策
1. **数据库**：统一使用 SQLite + sqlite-vec（Web 与未来桌面端共用）
2. **AI Provider**：多供应商，通过 `openai` Python SDK 设置 `base_url` 适配（OpenAI / DeepSeek / 智谱 / Ollama 等）
3. **无 Redis**：异步任务用 asyncio + SQLite 队列
4. **冲突保护**：保留 `version` 字段做乐观锁
5. **前端栈**：Vite + React + React Router（弃用 Next.js）
6. **PWA**：MVP 仅做离线读取已缓存数据 + 应用安装，不做离线写入
7. **Embedding 维度**：用户选定 provider 后锁定维度；切换需一键重建
8. **部署形态**：自托管单用户，无 auth/JWT/多租户

---

## 技术栈

| 层 | 选型 | 用途 |
| - | - | - |
| 后端框架 | FastAPI + Uvicorn | API + WebSocket + 静态前端挂载 |
| ORM / 迁移 | SQLAlchemy 2.x + Alembic | 数据访问与 schema 演进 |
| 数据库 | SQLite + sqlite-vec | 业务数据 + 向量检索 |
| AI SDK | openai (Python) | 统一 LLM/Embedding 入口 |
| 异步任务 | asyncio + 自建 SQLite 任务表 | embedding 生成 / 关联发现 |
| 前端框架 | Vite + React 18 + TypeScript | SPA |
| 路由 | React Router v6 | 客户端路由 |
| 状态 | Zustand | 全局状态 |
| 样式 | Tailwind CSS | 原子化样式 |
| 网状图 | React Flow | 交互式图谱 |
| PWA | vite-plugin-pwa (Workbox) | Service Worker + Manifest |
| 包管理 | 后端 uv / 前端 pnpm | — |

---

## 数据模型（修订版）

```sql
-- 想法主表
CREATE TABLE thought_atom (
  id            TEXT PRIMARY KEY,         -- UUID
  content       TEXT NOT NULL,
  content_type  TEXT DEFAULT 'text',      -- text|voice|image|url|mixed
  media_urls    TEXT,                     -- JSON 数组
  status        TEXT DEFAULT 'inbox',     -- inbox|active|archived|deleted
  source_device TEXT,
  version       INTEGER DEFAULT 1,        -- 乐观锁
  device_id     TEXT,
  created_at    TIMESTAMP,
  updated_at    TIMESTAMP,
  deleted_at    TIMESTAMP
);

-- Embedding 元数据（向量数据在 vec_atoms 虚表）
CREATE TABLE atom_embedding (
  atom_id     TEXT PRIMARY KEY REFERENCES thought_atom(id) ON DELETE CASCADE,
  model_name  TEXT NOT NULL,
  dim         INTEGER NOT NULL,
  created_at  TIMESTAMP
);

-- sqlite-vec 虚表（维度由 settings 锁定后动态创建）
CREATE VIRTUAL TABLE vec_atoms USING vec0(
  atom_id TEXT PRIMARY KEY,
  embedding float[<dim>]
);

-- 关联
CREATE TABLE thought_link (
  id             TEXT PRIMARY KEY,
  from_atom_id   TEXT NOT NULL REFERENCES thought_atom(id) ON DELETE CASCADE,
  to_atom_id     TEXT NOT NULL REFERENCES thought_atom(id) ON DELETE CASCADE,
  link_type      TEXT,                   -- semantic|temporal|manual|reference
  confidence     REAL,                   -- 0..1
  source         TEXT,                   -- ai_auto|ai_suggested|user
  user_confirmed BOOLEAN DEFAULT 0,
  user_ignored   BOOLEAN DEFAULT 0,
  created_at     TIMESTAMP,
  UNIQUE(from_atom_id, to_atom_id, link_type)
);

-- 异步任务队列（替代 Redis/ARQ）
CREATE TABLE task_queue (
  id          TEXT PRIMARY KEY,
  task_type   TEXT NOT NULL,             -- embed|link_discover|recluster
  payload     TEXT,                      -- JSON
  status      TEXT DEFAULT 'pending',    -- pending|running|done|failed
  attempts    INTEGER DEFAULT 0,
  last_error  TEXT,
  created_at  TIMESTAMP,
  updated_at  TIMESTAMP
);

-- 配置（单行）
CREATE TABLE settings (
  id              INTEGER PRIMARY KEY CHECK (id = 1),
  ai_base_url     TEXT,
  ai_api_key      TEXT,
  embed_model     TEXT,
  embed_dim       INTEGER,               -- 锁定维度
  chat_model      TEXT,
  link_threshold_auto    REAL DEFAULT 0.85,
  link_threshold_suggest REAL DEFAULT 0.70
);
```

---

## 关键模块设计

### 1. AI Provider 抽象 (`backend/app/services/ai_provider.py`)
- 单一 `AsyncOpenAI` 客户端，从 `settings` 表读取 `base_url` + `api_key`
- 暴露：`embed(texts: list[str]) -> list[list[float]]`、`chat(prompt: str) -> str`
- 切换 provider = 改 settings + 一键 rebuild

### 2. 异步任务队列 (`services/task_queue.py` + `workers/runner.py`)
- 入队：插入 `task_queue` 行 → 通过 `asyncio.Event` 唤醒 worker
- worker loop：拉取 pending → 处理 → 标记 done/failed（失败重试上限 3）
- 与 FastAPI 同进程启动（`lifespan` hook 中 `create_task`）
- 任务类型：
  - `embed`：调用 provider → 写 `atom_embedding` 与 `vec_atoms` → 入队 `link_discover`
  - `link_discover`：取该 atom 的 embedding → sqlite-vec KNN top-K → 按阈值分流写 `thought_link`
  - `recluster`（Phase 2）

### 3. 关联发现 (`services/linker.py`)
- KNN：`SELECT atom_id, distance FROM vec_atoms WHERE embedding MATCH ? ORDER BY distance LIMIT K`
- 相似度 = `1 - distance`（cosine）
- ≥ `link_threshold_auto` → `source=ai_auto, user_confirmed=1`
- `[suggest, auto)` → `source=ai_suggested, user_confirmed=0`
- 通过 WebSocket 广播 → 前端实时更新

### 4. WebSocket 广播 (`routers/ws.py`)
- 单 channel `/ws`，事件：`atom.created` / `atom.updated` / `link.created` / `link.suggested` / `link.confirmed`
- 前端 `useSync` hook 订阅 → 更新 Zustand store

### 5. PWA (MVP)
- `vite-plugin-pwa` autoUpdate 模式
- 缓存策略：
  - App Shell → precache
  - `GET /api/atoms`、`GET /api/graph` → StaleWhileRevalidate
  - POST/PUT/DELETE → NetworkOnly（离线时前端提示"需联网"）

### 6. 网状图 (`pages/Graph.tsx` + `components/GraphCanvas.tsx`)
- React Flow 自定义节点：圆形，半径按 degree 缩放
- 边样式：`user_confirmed=1` 实线；否则虚线
- 视图模式：全图 / 聚焦（一/二度）；主题模式延后到 Phase 2

---

## API 端点（MVP）

| Method | Path | 说明 |
| - | - | - |
| GET | `/api/atoms` | 列表（分页 + status 过滤） |
| POST | `/api/atoms` | 创建（立即返回，embedding 异步） |
| GET | `/api/atoms/:id` | 详情 + 已确认/建议关联 |
| PATCH | `/api/atoms/:id` | 更新（带 version 乐观锁） |
| DELETE | `/api/atoms/:id` | 软删除 |
| GET | `/api/links/suggestions` | 待确认的 AI 建议 |
| POST | `/api/links/:id/confirm` | 确认 |
| POST | `/api/links/:id/ignore` | 忽略 |
| POST | `/api/links` | 用户手动建立关联 |
| GET | `/api/search?q=...` | 语义搜索（query embedding + KNN） |
| GET | `/api/graph` | 全图数据 |
| GET | `/api/graph/focus/:id` | 聚焦子图 |
| GET | `/api/settings` | 读配置 |
| PUT | `/api/settings` | 写配置 |
| POST | `/api/settings/rebuild-embeddings` | 切换 provider 后重建 |
| WS | `/ws` | 实时事件 |

---

## 实施进度

### ✅ 已完成
- **Step 1 — 后端骨架**：uv 项目，FastAPI/SQLAlchemy/sqlite-vec/openai 依赖，app 包结构与占位 routers
- **Step 2 — 前端骨架**：Vite + React + TS，pnpm 管理，已装 react-router/zustand/reactflow/tailwind/vite-plugin-pwa，路由骨架与 dev proxy 配好；`pnpm build` 通过
- **Step 3 — 数据库迁移**：5 张表的 ORM 模型 + Alembic 初始迁移已 apply，sqlite-vec 扩展加载验证通过

### ⏳ 待实施

- **Step 4 — 配置与 AI Provider**
  1. `/api/settings` 读写 + 前端 Settings 页面
  2. `ai_provider.py` 统一封装
  3. 提交 settings 时动态 `CREATE VIRTUAL TABLE vec_atoms USING vec0(... float[<dim>])`

- **Step 5 — 想法 CRUD + 异步 embedding**
  1. atoms 路由 + 乐观锁
  2. `task_queue` 服务 + `workers/runner.py` 真实任务循环
  3. 创建 atom → 入队 `embed` → worker 调 provider → 写 vec_atoms → 入队 `link_discover`

- **Step 6 — 关联发现**
  1. `link_discover` 任务：KNN + 阈值分流
  2. links 路由（list / confirm / ignore / manual）
  3. WS 广播 link.created / link.suggested

- **Step 7 — 前端核心页面**
  1. Inbox（QuickInput + 卡片流 + WS 实时更新）
  2. AtomDetail（含 LinkSuggest 卡片）
  3. Search（语义搜索）

- **Step 8 — 网状图**
  1. `/api/graph` 与 `/api/graph/focus/:id`
  2. GraphCanvas（React Flow + 自定义节点/边样式）
  3. 全图与聚焦两种模式切换

- **Step 9 — PWA 打磨**
  1. 补图标
  2. 离线 fallback 页面 / 网络状态提示

- **Step 10 — 端到端冒烟测试 + 部署文档**

---

## 关键风险与缓解

| 风险 | 缓解 |
| - | - |
| sqlite-vec 虚表维度固定 | settings 锁定，切换时整表重建（按钮 + 进度） |
| 多 provider embedding 不可混用 | 同上；rebuild 期间禁用写入或排队 |
| 同进程 worker 阻塞 API | 任务全程 async；CPU 密集步骤极少（embedding 走网络） |
| WebSocket 在 PWA 离线时失效 | MVP 不要求离线写；前端检测连接状态降级为轮询 |
| 单用户假设下的安全 | 默认监听 127.0.0.1；如需局域网访问，文档提示加反向代理 + Basic Auth |

---

## 端到端验证步骤

1. `cd backend && uv run python run.py` 启动后端（127.0.0.1:8000）
2. `cd frontend && pnpm dev` 启动前端（5173 代理到 8000）
3. 打开 Settings 页面，填入 OpenAI 或本地 Ollama 的 base_url + key + 模型 + 维度 → 保存
4. Inbox 录入 5 条相关想法（如都关于"晨跑"）+ 5 条无关想法
5. 等待 ~10s，刷新 → 应看到相关想法之间出现实线或虚线关联
6. 打开 Graph 页面 → 节点可拖动；相关想法成簇
7. AtomDetail 确认/忽略一条建议 → 边样式从虚线变实线 / 消失
8. Search 输入 "运动" → 返回与晨跑相关的想法
9. 切换 provider（换 Ollama）→ 触发 rebuild → 关联重新生成
10. 手机浏览器打开 → "添加到主屏幕" → 离线时能打开 App Shell 并看到缓存的列表

---

## 不在 MVP 范围内（延后）

- 局域网 mDNS 同步（Phase 3）
- Tauri 桌面端打包（Phase 3）
- 语音输入 / 图片 / URL 想法类型（Phase 2）
- 主题聚类 / 话题岛（Phase 2）
- 多用户 / Auth（不做）
- PWA 离线写入（不做）
