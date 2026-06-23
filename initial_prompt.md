# Sparkling — 产品需求提示词

## 项目概述

构建一款名为 **Sparkling** 的本地优先（Local-first）碎片想法管理工具，支持快速录入、AI 自动关联、知识网状图可视化，以及局域网多设备同步。产品定位参考 Obsidian、Logseq，但强调 AI 驱动的自动关联而非手动整理。

---

## 核心功能需求

### 1. 碎片想法录入

- 打开即输入，零摩擦，无需预先分类或选择标签
- 支持输入类型：纯文字、语音转文字、图片/截图、URL 链接
- 所有新想法进入「Inbox」状态，不强迫用户立即整理
- 移动端优先考虑极速录入体验

### 2. AI 自动关联

- 每条想法录入后，后台异步生成语义向量（embedding）
- 基于向量相似度自动发现关联，附带置信度（0–1）
- 高置信度关联（> 0.8）自动建立连接；低置信度作为「建议」推送给用户确认
- 用户确认 / 忽略的反馈用于持续优化个人关联模型
- AI 定期对活跃想法进行主题聚类，生成「话题岛」摘要
- AI使用用户自己提供的AI供应商

### 3. 网状图可视化

- 所有想法以节点呈现，关联以边连接，构成可交互的知识图谱
- 节点大小编码连接数（枢纽想法更大）
- 实线 = 已确认关联；虚线 = AI 建议但未确认
- 支持三种视图模式：
  - **全图模式**：展示所有节点和关联
  - **聚焦模式**：点击节点展开一/二度关联
  - **主题模式**：按 AI 聚类结果分组展示

### 4. 多端支持

| 端           | 技术栈                                     | 侧重                 |
| ------------ | ------------------------------------------ | -------------------- |
| Web MVP      | Next.js 14 + Vite + React + TypeScript     | 快速验证核心功能     |
| macOS 桌面   | Tauri（Rust 壳）+ Python 后端 + React 前端 | 深度整理、系统集成   |
| Windows 桌面 | Tauri（Rust 壳）+ Python 后端 + React 前端 | 同上                 |
| iOS App      | Swift + SwiftUI（未来阶段）                | 极速录入、锁屏小组件 |

### 5. 局域网多设备同步

- 每台设备独立运行，本地 SQLite 存储，无需中心服务器
- 同一 Wi-Fi 下通过 **mDNS（Bonjour/Zeroconf）** 自动发现对端设备
- 每台设备运行 HTTP sync server（端口 8765），提供：
  - `GET /sync/changes?since=<timestamp>&device_id=<id>`
  - `POST /sync/push`
- 冲突策略：`content` 字段使用 last-write-wins（`updated_at` 较新者胜）；AI 关联边使用合并取并集
- 离线期间本地继续写入，重连后自动增量同步

---

## 数据模型

### 核心表：`thought_atom`

```sql
CREATE TABLE thought_atom (
    id           TEXT PRIMARY KEY,          -- UUID
    content      TEXT NOT NULL,             -- 想法文字内容
    content_type TEXT DEFAULT 'text',       -- text | voice | image | url | mixed
    media_urls   TEXT,                      -- JSON 数组，附件路径
    embedding    BLOB,                      -- 语义向量（float[]，1536 维）
    status       TEXT DEFAULT 'inbox',      -- inbox | active | archived | deleted
    source_device TEXT,                     -- 录入设备标识
    location     TEXT,                      -- 录入地点（可选）
    version      INTEGER DEFAULT 1,         -- 乐观锁版本号
    device_id    TEXT,                      -- 最后写入设备
    created_at   TIMESTAMP DEFAULT (datetime('now')),
    updated_at   TIMESTAMP DEFAULT (datetime('now')),
    deleted_at   TIMESTAMP                  -- 软删除
);
```

### 关联表：`thought_link`

```sql
CREATE TABLE thought_link (
    id           TEXT PRIMARY KEY,
    from_atom_id TEXT REFERENCES thought_atom(id),
    to_atom_id   TEXT REFERENCES thought_atom(id),
    link_type    TEXT,      -- semantic | temporal | manual | reference
    confidence   REAL,      -- 0.0–1.0，AI 生成时附带
    source       TEXT,      -- ai_auto | ai_suggested | user
    user_confirmed BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMP DEFAULT (datetime('now'))
);
```

### 同步日志表：`sync_log`

```sql
CREATE TABLE sync_log (
    id         TEXT PRIMARY KEY,
    device_id  TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    operation  TEXT NOT NULL,   -- upsert | delete
    payload    TEXT,            -- JSON，delete 时为 null
    synced     BOOLEAN DEFAULT FALSE
);
```

---

## 技术架构

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

**关键依赖：** `fastapi` · `uvicorn` · `sqlalchemy` · `alembic` · `openai` · `arq` · `redis` · `zeroconf` · `pyinstaller`（打包）

**数据库：**

- Web 版：PostgreSQL + pgvector
- 桌面版 / iOS：SQLite（路径：`~/.thoughtweb/thoughts.db`）

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

**关键依赖：** `react-flow` · `zustand` · `tailwindcss` · `vite`

### 桌面端（Tauri）

```
src-tauri/
├── src/main.rs              # 启动 Python 子进程，系统托盘，生命周期管理
└── tauri.conf.json          # 打包配置，resources 包含 Python 可执行文件
```

**打包流程：**

1. `npm run build`（前端静态产物）
2. `pyinstaller --onefile backend/run.py --name thoughtweb-server`
3. `npm run tauri build`（生成 .dmg / .msi / .deb）

---

## 非功能性要求

- **离线优先**：所有操作本地立即响应，同步在后台进行
- **数据主权**：用户数据仅存在本地设备，不经过第三方服务器
- **冲突透明**：AI 建议关联与用户确认关联有明显视觉区分
- **打包体积**：桌面安装包目标 < 30MB（Tauri 而非 Electron）
- **隐私**：Embedding 计算可配置使用本地模型（`nomic-embed`）作为 OpenAI 的替代

---

## 环境变量参考

```bash
# 后端
DATABASE_URL=postgresql://user:pass@localhost/thoughtweb   # Web 版
DATABASE_URL=sqlite:////~/.thoughtweb/thoughts.db          # 桌面版
OPENAI_API_KEY=sk-...
REDIS_URL=redis://localhost:6379
DEVICE_ID=auto                                             # 自动取 hostname

# 前端
VITE_API_URL=https://api.yourapp.com    # Web 版（不设则 fallback localhost:8000）
```

---

*文档生成自产品设计对话，版本日期：2026-06-23*
