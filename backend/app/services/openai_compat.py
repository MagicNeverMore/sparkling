"""OpenAI-compatible provider helpers."""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def normalize_base_url(base_url: str | None) -> str | None:
    """兼容用户只填写裸 host 的 OpenAI-compatible 服务。

    OpenAI SDK 会把 endpoint 拼到 base_url 后面。Ollama 的 OpenAI-compatible
    API 挂在 /v1 下，因此裸 host 需要补 /v1；如果用户已填写路径则保持原样。
    """
    if not base_url:
        return None
    value = base_url.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc and parsed.path in {"", "/"}:
        return urlunsplit((parsed.scheme, parsed.netloc, "/v1", parsed.query, parsed.fragment))
    return value
