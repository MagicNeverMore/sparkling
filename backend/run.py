"""开发启动入口：uv run python run.py"""
from __future__ import annotations

import uvicorn

from app.config import config


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
