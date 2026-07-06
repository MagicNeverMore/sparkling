"""Chat 服务：LLM 调用（Phase 2 摘要/聚类/建议）。当前仅提供连通性测试。"""
from __future__ import annotations

import time

from openai import AsyncOpenAI

from ..models import Settings
from .openai_compat import normalize_base_url
from .settings_snapshot import ChatSettingsSnapshot

ChatSettings = Settings | ChatSettingsSnapshot


def _get_chat_client(settings: ChatSettings) -> AsyncOpenAI:
    """根据 Settings 构造 Chat 专用的 OpenAI 兼容客户端。"""
    return AsyncOpenAI(
        api_key=settings.chat_api_key or "not-set",
        base_url=normalize_base_url(settings.chat_base_url),
    )


async def test_chat_provider(settings: ChatSettings) -> tuple[bool, float, str | None]:
    """测试 Chat provider 连通性，返回 (ok, latency_ms, error_msg)。"""
    start = time.monotonic()
    try:
        client = _get_chat_client(settings)
        await client.chat.completions.create(
            model=settings.chat_model or "gpt-4.1-mini",
            messages=[{"role": "user", "content": "say hello in one word"}],
            max_tokens=10,
        )
        latency = (time.monotonic() - start) * 1000
        return True, round(latency, 1), None
    except Exception as exc:
        latency = (time.monotonic() - start) * 1000
        return False, round(latency, 1), str(exc)
