#!/bin/bash
# Docker 入口脚本：初始化数据库 → 运行迁移 → 启动应用
set -e

echo "=== Sparkling Docker Entrypoint ==="

# 1. SQLite 首启时创建空文件（db.py 要求 mode=rw，文件必须预先存在）
if [ "${SPARKLING_DB_BACKEND:-sqlite}" = "sqlite" ]; then
    DATA_DIR="$(dirname "$SPARKLING_DB_PATH")"
    mkdir -p "$DATA_DIR"

    if [ ! -f "$SPARKLING_DB_PATH" ]; then
        echo "[entrypoint] 首次启动，创建数据库文件：$SPARKLING_DB_PATH"
        touch "$SPARKLING_DB_PATH"
    fi
else
    echo "[entrypoint] 使用 PostgreSQL"
fi

# 2. 运行 Alembic 数据库迁移
echo "[entrypoint] 执行数据库迁移..."
cd /app
uv run alembic upgrade head

# 3. 启动应用
echo "[entrypoint] 启动 Sparkling 服务..."
exec uv run uvicorn app.main:app \
    --host "${SPARKLING_HOST:-0.0.0.0}" \
    --port "${SPARKLING_PORT:-3721}" \
    --no-server-header
