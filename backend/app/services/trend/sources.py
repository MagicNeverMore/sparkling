"""Trend 信息源适配器。

这些适配器只负责发现候选 URL；页面内容抓取和事实校验在 collector 中完成。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import feedparser
import httpx

from ...logger import get_logger

logger = get_logger(__name__)

USER_AGENT = "SparklingTrendBot/0.1 (+https://localhost)"
DEFAULT_SOURCE_CONFIG: dict[str, dict[str, Any]] = {
    "github": {"enabled": True, "limit": 8, "token": None},
    "hackernews": {"enabled": True, "limit": 8},
    "google": {"enabled": False, "limit": 8},
}
MAX_CANDIDATE_TITLE_CHARS = 500
MAX_CANDIDATE_URL_CHARS = 2_000
MAX_CANDIDATE_SUMMARY_CHARS = 2_000
MAX_CANDIDATE_METADATA_ITEMS = 20
MAX_CANDIDATE_METADATA_TEXT_CHARS = 500


@dataclass(frozen=True)
class TrendCandidate:
    source: str
    title: str
    url: str
    summary: str | None = None
    published_at: str | None = None
    score_hint: float | None = None
    metadata: dict[str, Any] | None = None

    def to_llm_dict(self) -> dict[str, Any]:
        return {
            "source": _truncate_text(self.source, 80),
            "title": _truncate_text(self.title, MAX_CANDIDATE_TITLE_CHARS),
            "url": _truncate_text(self.url, MAX_CANDIDATE_URL_CHARS),
            "summary": _truncate_text(self.summary, MAX_CANDIDATE_SUMMARY_CHARS),
            "published_at": _truncate_text(self.published_at, 120),
            "score_hint": self.score_hint,
            "metadata": _safe_metadata(self.metadata),
        }


@dataclass(frozen=True)
class RssSourceConfig:
    id: str
    name: str
    url: str
    limit: int


def _truncate_text(value: Any, max_chars: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:max_chars] if text else None


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    safe: dict[str, Any] = {}
    for index, (key, value) in enumerate(metadata.items()):
        if index >= MAX_CANDIDATE_METADATA_ITEMS:
            break
        safe_key = str(key)[:80]
        if isinstance(value, (int, float, bool)) or value is None:
            safe[safe_key] = value
        elif isinstance(value, list):
            safe[safe_key] = [
                _truncate_text(item, MAX_CANDIDATE_METADATA_TEXT_CHARS)
                for item in value[:10]
            ]
        elif isinstance(value, dict):
            safe[safe_key] = {
                str(child_key)[:80]: _truncate_text(child_value, MAX_CANDIDATE_METADATA_TEXT_CHARS)
                for child_key, child_value in list(value.items())[:10]
            }
        else:
            safe[safe_key] = _truncate_text(value, MAX_CANDIDATE_METADATA_TEXT_CHARS)
    return safe


def normalize_source_config(config: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """合并 source 默认配置，并修正类型。"""
    merged: dict[str, dict[str, Any]] = {
        key: value.copy()
        for key, value in DEFAULT_SOURCE_CONFIG.items()
    }
    if isinstance(config, dict):
        for key, value in config.items():
            if key not in merged or not isinstance(value, dict):
                continue
            merged[key].update(value)

    for source, value in merged.items():
        value["enabled"] = bool(value.get("enabled"))
        try:
            value["limit"] = max(1, min(int(value.get("limit") or 8), 50))
        except (TypeError, ValueError):
            value["limit"] = 8
        if source == "github" and not value.get("token"):
            value["token"] = None
    return merged


def canonical_url(url: str) -> str:
    """用于候选去重的轻量 URL 归一化。"""
    value = (url or "").strip()
    if not value:
        return value
    parsed = urlsplit(value)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    query_parts = []
    for item in parsed.query.split("&"):
        if not item:
            continue
        key = item.split("=", 1)[0].lower()
        if key.startswith("utm_") or key in {"ref", "fbclid", "gclid"}:
            continue
        query_parts.append(item)
    return urlunsplit((scheme, netloc, path, "&".join(query_parts), ""))


def _short_query(query: str) -> str:
    return " ".join(query.split())[:180] or "AI software creator trends"


async def discover_candidates(
    query: str,
    source_config: dict[str, Any] | None,
    *,
    limit_override: int | None = None,
) -> list[TrendCandidate]:
    """从所有启用 source 发现候选内容。

    单个 source 失败不会中断整次 Trend 运行。
    """
    config = normalize_source_config(source_config)
    search_query = _short_query(query)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(12.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    ) as client:
        results: list[TrendCandidate] = []
        source_calls = [
            ("github", _fetch_github),
            ("hackernews", _fetch_hackernews),
        ]
        for source, fetcher in source_calls:
            source_cfg = config[source]
            if not source_cfg.get("enabled"):
                logger.debug("Trend source 已禁用 source=%s", source)
                continue
            limit = limit_override or int(source_cfg.get("limit") or 8)
            try:
                source_results = await fetcher(client, search_query, source_cfg, limit)
                results.extend(source_results)
                logger.info("Trend source 获取完成 source=%s count=%d limit=%d", source, len(source_results), limit)
            except Exception as exc:
                logger.warning("Trend source %s 获取失败: %s", source, exc)
        # v1 保留 google 配置位，但不直接抓搜索页。
        unique = _dedupe_candidates(results)
        logger.info("Trend 候选去重完成 raw=%d unique=%d", len(results), len(unique))
        return unique


async def discover_rss_candidates(sources: list[RssSourceConfig]) -> list[TrendCandidate]:
    """抓取启用的 RSS/Atom source；单个 feed 失败不影响其他 feed。"""
    if not sources:
        return []
    async with _create_rss_client() as client:
        results: list[TrendCandidate] = []
        for source in sources:
            try:
                source_results = await _fetch_rss(client, source)
                results.extend(source_results)
                logger.info(
                    "Trend RSS source 获取完成 source_id=%s name=%s count=%d limit=%d",
                    source.id,
                    source.name,
                    len(source_results),
                    source.limit,
                )
            except Exception as exc:
                logger.warning(
                    "Trend RSS source 获取失败 source_id=%s name=%s error=%s",
                    source.id,
                    source.name,
                    exc,
                )
        return _dedupe_candidates(results)


async def fetch_rss_source(source: RssSourceConfig) -> list[TrendCandidate]:
    """读取单个 RSS/Atom source，并保留请求或解析错误供调用方展示。"""
    async with _create_rss_client() as client:
        return await _fetch_rss(client, source)


def _create_rss_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(12.0),
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.5",
        },
    )


async def _fetch_rss(client: httpx.AsyncClient, source: RssSourceConfig) -> list[TrendCandidate]:
    response = await client.get(source.url)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    entries = list(parsed.get("entries") or [])
    if not entries and parsed.get("bozo"):
        raise ValueError(f"RSS 解析失败: {parsed.get('bozo_exception')}")

    candidates: list[TrendCandidate] = []
    for entry in entries[: max(1, min(source.limit, 50))]:
        title = str(entry.get("title") or "").strip()
        url = _rss_entry_url(entry)
        if not title or not url:
            continue
        tags = [
            str(tag.get("term"))
            for tag in (entry.get("tags") or [])[:10]
            if isinstance(tag, dict) and tag.get("term")
        ]
        candidates.append(
            TrendCandidate(
                source=f"rss:{source.name}",
                title=title,
                url=url,
                summary=entry.get("summary") or entry.get("description") or None,
                published_at=entry.get("published") or entry.get("updated") or None,
                metadata={
                    "rss_source_id": source.id,
                    "rss_source_name": source.name,
                    "feed_url": source.url,
                    "author": entry.get("author"),
                    "tags": tags,
                },
            )
        )
    return candidates


def _rss_entry_url(entry: dict[str, Any]) -> str | None:
    direct = str(entry.get("link") or "").strip()
    if direct:
        return direct
    for link in entry.get("links") or []:
        if not isinstance(link, dict):
            continue
        href = str(link.get("href") or "").strip()
        if href and link.get("rel", "alternate") == "alternate":
            return href
    return None


async def _fetch_github(
    client: httpx.AsyncClient,
    query: str,
    config: dict[str, Any],
    limit: int,
) -> list[TrendCandidate]:
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    token = config.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    res = await client.get(
        "https://api.github.com/search/repositories",
        params={
            "q": f"{query} in:name,description,readme",
            "sort": "updated",
            "order": "desc",
            "per_page": limit,
        },
        headers=headers,
    )
    res.raise_for_status()
    items = res.json().get("items", [])
    candidates: list[TrendCandidate] = []
    for item in items:
        title = item.get("full_name") or item.get("name")
        url = item.get("html_url")
        if not title or not url:
            continue
        candidates.append(
            TrendCandidate(
                source="github",
                title=title,
                url=url,
                summary=item.get("description") or None,
                published_at=item.get("updated_at"),
                score_hint=float(item.get("stargazers_count") or 0),
                metadata={
                    "language": item.get("language"),
                    "stars": item.get("stargazers_count"),
                    "forks": item.get("forks_count"),
                    "open_issues": item.get("open_issues_count"),
                },
            )
        )
    return candidates


async def _fetch_hackernews(
    client: httpx.AsyncClient,
    query: str,
    _config: dict[str, Any],
    limit: int,
) -> list[TrendCandidate]:
    res = await client.get(
        "https://hn.algolia.com/api/v1/search_by_date",
        params={"query": query, "tags": "story", "hitsPerPage": limit},
    )
    res.raise_for_status()
    hits = res.json().get("hits", [])
    candidates: list[TrendCandidate] = []
    for hit in hits:
        object_id = hit.get("objectID")
        url = hit.get("url") or (f"https://news.ycombinator.com/item?id={object_id}" if object_id else None)
        title = hit.get("title") or hit.get("story_title")
        if not title or not url:
            continue
        candidates.append(
            TrendCandidate(
                source="hackernews",
                title=title,
                url=url,
                summary=hit.get("story_text") or None,
                published_at=hit.get("created_at"),
                score_hint=float(hit.get("points") or 0),
                metadata={
                    "hn_id": object_id,
                    "comments": hit.get("num_comments"),
                    "hn_url": f"https://news.ycombinator.com/item?id={object_id}" if object_id else None,
                },
            )
        )
    return candidates


def _dedupe_candidates(candidates: list[TrendCandidate]) -> list[TrendCandidate]:
    seen: set[str] = set()
    unique: list[TrendCandidate] = []
    for candidate in candidates:
        key = canonical_url(candidate.url)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique
