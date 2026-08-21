#!/bin/bash
# Docker 入口脚本：初始化数据库 → 运行迁移 → 启动应用
set -e

echo "=== Sparkling Docker Entrypoint ==="

# 1. 首次启动时创建默认 SQLite 文件。
# 实际业务数据库配置从 control DB 读取；PostgreSQL 通过 Settings 页面写入 control DB。
DATA_DIR="$(dirname "$SPARKLING_DB_PATH")"
mkdir -p "$DATA_DIR"

if [ ! -f "$SPARKLING_DB_PATH" ]; then
    echo "[entrypoint] 首次启动，创建默认 SQLite 数据库文件：$SPARKLING_DB_PATH"
    touch "$SPARKLING_DB_PATH"
fi

# 2. 运行 Alembic 数据库迁移
echo "[entrypoint] 执行数据库迁移..."
cd /app
uv run python -m app.migrate

# 3. 启动应用
echo "[entrypoint] 启动 Sparkling 服务..."
exec uv run uvicorn app.main:app \
    --host "${SPARKLING_HOST:-0.0.0.0}" \
    --port "${SPARKLING_PORT:-3721}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
    --no-server-header
