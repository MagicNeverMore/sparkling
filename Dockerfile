# Sparkling — 多阶段 Docker 构建
# Stage 1: 构建前端 (Node + pnpm + Vite)
# Stage 2: Python 后端 + 挂载前端产物

# ============================================================
# Stage 1 — Frontend build
# ============================================================
FROM node:22-alpine AS frontend-builder
WORKDIR /src/frontend

ENV CI=true

RUN corepack enable

# 利用 Docker 层缓存：先装依赖，再拷源码
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build
# 构建产物在 ../backend/app/frontend/ （vite.config.ts outDir）

# ============================================================
# Stage 2 — Python backend
# ============================================================
FROM python:3.12-slim
WORKDIR /app

# 系统依赖（sqlite-vec 的 manylinux wheel 已内置所需 .so）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv（快速 Python 依赖管理）
RUN pip install --no-cache-dir uv

# 先拷依赖描述文件，利用层缓存
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# 拷贝后端源码
COPY backend/ ./

# 将前端构建产物放入 backend 预期路径
COPY --from=frontend-builder /src/backend/app/frontend ./app/frontend

# 数据库持久化目录
RUN mkdir -p /data

ENV SPARKLING_DB_PATH=/data/sparkling.db \
    SPARKLING_CONTROL_DB_PATH=/data/control.db \
    SPARKLING_HOST=0.0.0.0 \
    SPARKLING_PORT=3721 \
    SPARKLING_DEV_ORIGIN= \
    FORWARDED_ALLOW_IPS=127.0.0.1

EXPOSE 3721

# 入口：初始化数据库 → 迁移 → 启动
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
