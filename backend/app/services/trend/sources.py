"""Trend 信息源适配器。

这些适配器只负责发现候选 URL；页面内容抓取和事实校验在 collector 中完成。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
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

# GitHub 的 Repository Search 只能提供总 star 数，无法说明项目是否在近期被关注。
# 因此先用规模与活跃度过滤候选，再用 GraphQL 的 starredAt 做增量验证。
GITHUB_RECENT_PUSH_DAYS = 14
GITHUB_NEW_REPOSITORY_DAYS = 30
GITHUB_NEW_MIN_STARS = 200
GITHUB_NEW_MIN_FORKS = 10
GITHUB_MATURE_MIN_STARS = 500
GITHUB_MATURE_MIN_FORKS = 25
GITHUB_FALLBACK_NEW_MIN_STARS = 500
GITHUB_FALLBACK_NEW_MIN_FORKS = 25
GITHUB_FALLBACK_MATURE_MIN_STARS = 1_000
GITHUB_FALLBACK_MATURE_MIN_FORKS = 50
GITHUB_MIN_STARS_LAST_7_DAYS = 50
GITHUB_MIN_STARS_LAST_30_DAYS = 150
GITHUB_NEW_MIN_STARS_LAST_7_DAYS = 80
GITHUB_STAR_PAGE_SIZE = 100
GITHUB_CANDIDATE_POOL_MULTIPLIER = 3


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


@dataclass(frozen=True)
class GithubStarActivity:
    stars_last_7d: int
    stars_last_30d: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    now = _utc_now()
    pushed_since = (now - timedelta(days=GITHUB_RECENT_PUSH_DAYS)).date().isoformat()
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
    candidate_pool_size = min(max(limit * GITHUB_CANDIDATE_POOL_MULTIPLIER, 12), 50)
    res = await client.get(
        "https://api.github.com/search/repositories",
        params={
            "q": (
                f"{query} in:name,description,readme "
                f"pushed:>={pushed_since} "
                f"stars:>={GITHUB_NEW_MIN_STARS} forks:>={GITHUB_NEW_MIN_FORKS} "
                "fork:false archived:false"
            ),
            "sort": "stars",
            "order": "desc",
            "per_page": candidate_pool_size,
        },
        headers=headers,
    )
    res.raise_for_status()
    payload = res.json()
    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        raise ValueError("GitHub Repository Search 返回 items 字段格式不正确")

    rejected: Counter[str] = Counter()
    baseline_items: list[tuple[dict[str, Any], str]] = []
    for item in items:
        if not isinstance(item, dict):
            rejected["invalid_item"] += 1
            continue
        tier, reason = _github_candidate_tier(item, now)
        if reason:
            rejected[reason] += 1
            continue
        baseline_items.append((item, tier))

    logger.info(
        "Trend GitHub 基础热度筛选 query_hash=%s raw=%d eligible=%d rejected=%s pushed_since=%s",
        query_hash,
        len(items),
        len(baseline_items),
        dict(rejected),
        pushed_since,
    )
    if not baseline_items:
        return []

    if not token:
        return _conservative_github_candidates(baseline_items, limit, query_hash)

    try:
        star_activity = await _github_star_activity(client, str(token), baseline_items, now)
    except Exception as exc:
        # 没有可信的近期增量就不能把项目标记为热点；不要退回到普通搜索结果。
        logger.warning(
            "Trend GitHub star 增量验证失败，已丢弃本次 GitHub 候选 query_hash=%s candidate_count=%d error=%s",
            query_hash,
            len(baseline_items),
            exc,
        )
        return []

    candidates: list[TrendCandidate] = []
    hotness_rejected: Counter[str] = Counter()
    for index, (item, tier) in enumerate(baseline_items):
        activity = star_activity.get(index)
        if activity is None:
            hotness_rejected["missing_star_activity"] += 1
            continue
        if not _passes_github_star_velocity(tier, activity):
            hotness_rejected["insufficient_recent_stars"] += 1
            continue
        candidates.append(_github_candidate_from_item(item, tier, activity, verification="star_velocity"))

    candidates.sort(
        key=lambda candidate: (
            int((candidate.metadata or {}).get("stars_last_7d") or 0),
            int((candidate.metadata or {}).get("stars_last_30d") or 0),
            int((candidate.metadata or {}).get("stars") or 0),
            int((candidate.metadata or {}).get("forks") or 0),
        ),
        reverse=True,
    )
    logger.info(
        "Trend GitHub 近期热度验证完成 query_hash=%s eligible=%d verified=%d rejected=%s",
        query_hash,
        len(baseline_items),
        len(candidates),
        dict(hotness_rejected),
    )
    return candidates[:limit]


def _github_candidate_tier(item: dict[str, Any], now: datetime) -> tuple[str, str | None]:
    """返回 GitHub 候选的层级，或不满足基础门槛的原因。"""
    if item.get("fork"):
        return "", "fork"
    if item.get("archived") or item.get("disabled"):
        return "", "inactive_repository"
    owner = item.get("owner")
    if (
        not item.get("full_name")
        or not item.get("html_url")
        or not item.get("name")
        or not isinstance(owner, dict)
        or not owner.get("login")
    ):
        return "", "missing_identity"

    pushed_at = _parse_github_timestamp(item.get("pushed_at"))
    created_at = _parse_github_timestamp(item.get("created_at"))
    if pushed_at is None or created_at is None:
        return "", "invalid_timestamps"
    if pushed_at < now - timedelta(days=GITHUB_RECENT_PUSH_DAYS):
        return "", "not_recently_pushed"

    stars = _github_metric(item.get("stargazers_count"))
    forks = _github_metric(item.get("forks_count"))
    if stars is None or forks is None:
        return "", "invalid_metrics"
    is_new = created_at >= now - timedelta(days=GITHUB_NEW_REPOSITORY_DAYS)
    if is_new:
        if stars < GITHUB_NEW_MIN_STARS or forks < GITHUB_NEW_MIN_FORKS:
            return "", "new_repository_below_baseline"
        return "new", None
    if stars < GITHUB_MATURE_MIN_STARS or forks < GITHUB_MATURE_MIN_FORKS:
        return "", "mature_repository_below_baseline"
    return "mature", None


def _conservative_github_candidates(
    baseline_items: list[tuple[dict[str, Any], str]],
    limit: int,
    query_hash: str,
) -> list[TrendCandidate]:
    """未配置 Token 时保持可用，但不把无法验证的项目伪装成近期热点。"""
    candidates: list[TrendCandidate] = []
    for item, tier in baseline_items:
        stars = _github_metric(item.get("stargazers_count")) or 0
        forks = _github_metric(item.get("forks_count")) or 0
        if tier == "new":
            accepted = stars >= GITHUB_FALLBACK_NEW_MIN_STARS and forks >= GITHUB_FALLBACK_NEW_MIN_FORKS
        else:
            accepted = stars >= GITHUB_FALLBACK_MATURE_MIN_STARS and forks >= GITHUB_FALLBACK_MATURE_MIN_FORKS
        if accepted:
            candidates.append(_github_candidate_from_item(item, tier, None, verification="conservative_without_token"))

    candidates.sort(
        key=lambda candidate: (
            int((candidate.metadata or {}).get("stars") or 0),
            int((candidate.metadata or {}).get("forks") or 0),
        ),
        reverse=True,
    )
    logger.warning(
        "Trend GitHub 未配置 token，无法验证近期 star 增量；使用严格保守筛选 query_hash=%s eligible=%d accepted=%d",
        query_hash,
        len(baseline_items),
        len(candidates),
    )
    return candidates[:limit]


def _github_candidate_from_item(
    item: dict[str, Any],
    tier: str,
    activity: GithubStarActivity | None,
    *,
    verification: str,
) -> TrendCandidate:
    stars = _github_metric(item.get("stargazers_count")) or 0
    forks = _github_metric(item.get("forks_count")) or 0
    return TrendCandidate(
        source="github",
        title=str(item.get("full_name") or item.get("name")),
        url=str(item.get("html_url")),
        summary=item.get("description") or None,
        published_at=item.get("pushed_at") or item.get("updated_at"),
        score_hint=float(stars),
        metadata={
            "language": item.get("language"),
            "stars": stars,
            "forks": forks,
            "open_issues": item.get("open_issues_count"),
            "pushed_at": item.get("pushed_at"),
            "created_at": item.get("created_at"),
            "hotness_tier": tier,
            "hotness_verification": verification,
            "stars_last_7d": activity.stars_last_7d if activity else None,
            "stars_last_30d": activity.stars_last_30d if activity else None,
        },
    )


def _passes_github_star_velocity(tier: str, activity: GithubStarActivity) -> bool:
    if tier == "new":
        return activity.stars_last_7d >= GITHUB_NEW_MIN_STARS_LAST_7_DAYS
    return (
        activity.stars_last_7d >= GITHUB_MIN_STARS_LAST_7_DAYS
        or activity.stars_last_30d >= GITHUB_MIN_STARS_LAST_30_DAYS
    )


def _github_metric(value: Any) -> int | None:
    try:
        metric = int(value)
    except (TypeError, ValueError):
        return None
    return metric if metric >= 0 else None


def _parse_github_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def _github_star_activity(
    client: httpx.AsyncClient,
    token: str,
    baseline_items: list[tuple[dict[str, Any], str]],
    now: datetime,
) -> dict[int, GithubStarActivity]:
    """批量读取最近 200 个 star 的时间，避免每个仓库单独请求。"""
    first_page = await _github_stargazer_page(client, token, baseline_items)
    stars_by_index: dict[int, list[datetime]] = {}
    second_page_items: list[tuple[int, dict[str, Any], str, str]] = []
    cutoff_30d = now - timedelta(days=30)

    for index, (item, tier) in enumerate(baseline_items):
        page = first_page.get(index)
        if page is None:
            continue
        starred_at, page_info = page
        stars_by_index[index] = starred_at
        # 仅当最新 100 个 star 都在 30 天内时，才有可能达到 150/30 天门槛。
        if (
            len(starred_at) == GITHUB_STAR_PAGE_SIZE
            and starred_at
            and min(starred_at) >= cutoff_30d
            and page_info.get("hasNextPage")
            and page_info.get("endCursor")
        ):
            second_page_items.append((index, item, tier, str(page_info["endCursor"])))

    if second_page_items:
        second_page = await _github_stargazer_page(
            client,
            token,
            [(item, tier) for _index, item, tier, _cursor in second_page_items],
            after_cursors=[cursor for _index, _item, _tier, cursor in second_page_items],
        )
        for second_index, (original_index, _item, _tier, _cursor) in enumerate(second_page_items):
            page = second_page.get(second_index)
            if page is not None:
                stars_by_index[original_index].extend(page[0])

    activity: dict[int, GithubStarActivity] = {}
    cutoff_7d = now - timedelta(days=7)
    for index, timestamps in stars_by_index.items():
        activity[index] = GithubStarActivity(
            stars_last_7d=sum(timestamp >= cutoff_7d for timestamp in timestamps),
            stars_last_30d=sum(timestamp >= cutoff_30d for timestamp in timestamps),
        )
    return activity


async def _github_stargazer_page(
    client: httpx.AsyncClient,
    token: str,
    baseline_items: list[tuple[dict[str, Any], str]],
    *,
    after_cursors: list[str] | None = None,
) -> dict[int, tuple[list[datetime], dict[str, Any]]]:
    fields: list[str] = []
    for index, (item, _tier) in enumerate(baseline_items):
        owner = item.get("owner", {}).get("login") if isinstance(item.get("owner"), dict) else None
        name = item.get("name")
        if not isinstance(owner, str) or not isinstance(name, str):
            continue
        after = ""
        if after_cursors:
            after = f", after: {json.dumps(after_cursors[index])}"
        fields.append(
            f'''repo_{index}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{
                stargazers(first: {GITHUB_STAR_PAGE_SIZE}{after}, orderBy: {{field: STARRED_AT, direction: DESC}}) {{
                    edges {{ starredAt }}
                    pageInfo {{ endCursor hasNextPage }}
                }}
            }}'''
        )
    if not fields:
        return {}

    response = await client.post(
        "https://api.github.com/graphql",
        json={"query": "query TrendGithubStarVelocity {\n" + "\n".join(fields) + "\n}"},
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("GitHub GraphQL 返回格式不正确")
    errors = payload.get("errors")
    if errors:
        message = errors[0].get("message") if isinstance(errors[0], dict) else "unknown error"
        raise ValueError(f"GitHub GraphQL 查询失败: {message}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("GitHub GraphQL 未返回 data")

    result: dict[int, tuple[list[datetime], dict[str, Any]]] = {}
    for index in range(len(baseline_items)):
        repository = data.get(f"repo_{index}")
        stargazers = repository.get("stargazers") if isinstance(repository, dict) else None
        if not isinstance(stargazers, dict):
            continue
        timestamps = [
            timestamp
            for edge in stargazers.get("edges") or []
            if isinstance(edge, dict)
            for timestamp in [_parse_github_timestamp(edge.get("starredAt"))]
            if timestamp is not None
        ]
        page_info = stargazers.get("pageInfo")
        result[index] = (timestamps, page_info if isinstance(page_info, dict) else {})
    return result


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
