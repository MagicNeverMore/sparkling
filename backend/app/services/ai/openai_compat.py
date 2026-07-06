"""OpenAI-compatible provider helpers."""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _with_default_scheme(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value
    # urlsplit("localhost:11434") treats "localhost" as a scheme, so handle
    # non-http schemes as a missing scheme for local OpenAI-compatible services.
    if not parsed.netloc:
        host_port = value.split("/", 1)[0].strip("[]")
        host = host_port.rsplit(":", 1)[0]
        scheme = "http" if host in LOCAL_HOSTS or host_port.endswith(":11434") else "https"
        return f"{scheme}://{value.lstrip('/')}"
    return value


def _should_append_v1(base_url: str) -> bool:
    parsed = urlsplit(base_url)
    return parsed.path in {"", "/"}


def normalize_base_url(base_url: str | None) -> str | None:
    """兼容用户只填写裸 host 的 OpenAI-compatible 服务。

    OpenAI SDK 会把 endpoint 拼到 base_url 后面。Ollama 的 OpenAI-compatible
    API 挂在 /v1 下，因此裸 host 需要补 /v1；如果用户已填写路径则保持原样。
    """
    if not base_url:
        return None
    value = _with_default_scheme(base_url.strip().rstrip("/"))
    parsed = urlsplit(value)
    if parsed.scheme and parsed.netloc and _should_append_v1(value):
        return urlunsplit((parsed.scheme, parsed.netloc, "/v1", parsed.query, parsed.fragment))
    return value
