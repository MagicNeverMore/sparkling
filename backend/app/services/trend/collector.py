"""Trend 采集、LLM 评分与入库逻辑。"""
from __future__ import annotations

import asyncio
import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from ...db import SessionLocal
from ...logger import get_logger
from ...models import Settings, TaskQueue, TrendItem, TrendRssSource, TrendRun
from ...time_utils import local_to_utc_naive, utc_naive_to_local
from .. import task_queue as tq
from ..ai.openai_compat import normalize_base_url
from ..settings.settings_snapshot import TrendSettingsSnapshot, snapshot_trend_settings
from .sources import (
    RssSourceConfig,
    TrendCandidate,
    canonical_url,
    discover_candidates,
    discover_rss_candidates,
    normalize_source_config,
)

logger = get_logger(__name__)

DEFAULT_TREND_PROMPT = "AI tools, developer tools, software startups, creator economy, technology trends"
MAX_FETCH_BYTES = 500_000
MAX_PAGE_TEXT_CHARS = 6_000
MAX_EVIDENCE_ITEMS = 6
MAX_FOLLOW_UP_ROUNDS = 2
MAX_TREND_BRAND_PROMPT_CHARS = 4_000
# reasoning model 的思考过程也会计入该上限，需为最终 JSON 预留足够空间。
MAX_TREND_COMPLETION_TOKENS = 3_200
MAX_TREND_SEARCH_QUERIES = 5
MAX_TREND_SEARCH_QUERY_CHARS = 120
# reasoning model 的思考过程也会计入该上限，需为最终 JSON 预留足够空间。
MAX_TREND_QUERY_PLAN_TOKENS = 1_600
TREND_PROVIDER_TEST_TIMEOUT_SECONDS = 20.0
TREND_LLM_TIMEOUT_SECONDS = 120.0
TrendSettings = Settings | TrendSettingsSnapshot


@dataclass
class WebFetchResult:
    url: str
    final_url: str
    ok: bool
    title: str | None = None
    description: str | None = None
    text: str | None = None
    error: str | None = None

    def to_llm_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "ok": self.ok,
            "title": self.title,
            "description": self.description,
            "text": (self.text or "")[:MAX_PAGE_TEXT_CHARS],
            "error": self.error,
        }


@dataclass
class TrendEvidence:
    candidate: TrendCandidate
    fetched: WebFetchResult

    def to_llm_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate.to_llm_dict(),
            "webfetch": self.fetched.to_llm_dict(),
        }


def _now() -> datetime:
    return datetime.utcnow()


def _load_source_config(settings: TrendSettings) -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(settings.trend_source_config or "{}")
    except json.JSONDecodeError:
        raw = {}
    return normalize_source_config(raw)


def _resolve_trend_provider(settings: TrendSettings) -> tuple[str | None, str | None, str | None]:
    """Trend provider 默认复用 Chat provider，单独填写后覆盖。"""
    if settings.trend_base_url:
        return (
            settings.trend_base_url,
            settings.trend_api_key,
            settings.trend_model or settings.chat_model,
        )
    return (
        settings.chat_base_url,
        settings.trend_api_key or settings.chat_api_key,
        settings.trend_model or settings.chat_model,
    )


def _get_trend_client(
    settings: TrendSettings,
    *,
    timeout_seconds: float = TREND_LLM_TIMEOUT_SECONDS,
    max_retries: int = 1,
) -> tuple[AsyncOpenAI, str]:
    base_url, api_key, model = _resolve_trend_provider(settings)
    if not model:
        raise ValueError("请先配置 Chat provider 或 Trend LLM provider")
    timeout = httpx.Timeout(timeout_seconds, connect=min(8.0, timeout_seconds))
    client = AsyncOpenAI(
        api_key=api_key or "not-set",
        base_url=normalize_base_url(base_url),
        timeout=timeout,
        max_retries=max_retries,
    )
    return client, model


def _should_retry_without_response_format(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "response_format" in message
        or "response format" in message
        or "json_object" in message
        or ("format" in message and ("unsupported" in message or "not support" in message))
    )


async def _create_json_chat_completion(
    client: AsyncOpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int | None = None,
    temperature: float | None = None,
):
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature
    try:
        return await client.chat.completions.create(**kwargs)
    except Exception as exc:
        if not _should_retry_without_response_format(exc):
            raise
        logger.info("Trend LLM provider 不支持 response_format，改用 JSON-only prompt 重试")
        kwargs.pop("response_format", None)
        return await client.chat.completions.create(**kwargs)


async def test_trend_provider(settings: TrendSettings) -> tuple[bool, float, str | None]:
    start = datetime.utcnow()
    client: AsyncOpenAI | None = None
    try:
        client, model = _get_trend_client(
            settings,
            timeout_seconds=TREND_PROVIDER_TEST_TIMEOUT_SECONDS,
            max_retries=0,
        )
        await asyncio.wait_for(
            _create_json_chat_completion(
                client,
                model=model,
                messages=[{"role": "user", "content": "Return JSON only: {\"ok\": true}"}],
                max_tokens=20,
            ),
            timeout=TREND_PROVIDER_TEST_TIMEOUT_SECONDS + 1,
        )
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return True, round(latency, 1), None
    except asyncio.TimeoutError:
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return False, round(latency, 1), f"Trend LLM provider 测试超时（>{TREND_PROVIDER_TEST_TIMEOUT_SECONDS:.0f}s）"
    except Exception as exc:
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return False, round(latency, 1), str(exc)
    finally:
        if client is not None and not client.is_closed():
            await client.close()


def enqueue_trend_run(session: Session, trigger: str = "manual") -> TrendRun:
    run = TrendRun(trigger=trigger, status="pending")
    session.add(run)
    session.commit()
    session.refresh(run)
    tq.enqueue(session, "trend_collect", {"run_id": run.id})
    return run


def maybe_enqueue_due_trend_run(session: Session, settings: Settings, now: datetime | None = None) -> TrendRun | None:
    """轻量 scheduler：到期时创建一个 trend_collect 任务。"""
    now = now or _now()
    if not settings.trend_schedule_enabled:
        return None

    if settings.trend_next_run_at is None:
        settings.trend_next_run_at = calculate_next_run_at(settings, now)
        session.commit()
        return None

    if settings.trend_next_run_at > now:
        return None

    active_run = (
        session.query(TrendRun)
        .filter(TrendRun.status.in_(["pending", "running"]))
        .order_by(TrendRun.created_at.desc())
        .first()
    )
    active_task = (
        session.query(TaskQueue)
        .filter(TaskQueue.task_type == "trend_collect")
        .filter(TaskQueue.status.in_(["pending", "running"]))
        .first()
    )
    if active_run or active_task:
        return None

    settings.trend_next_run_at = calculate_next_run_at(settings, now + timedelta(seconds=1))
    session.commit()
    return enqueue_trend_run(session, "scheduled")


def calculate_next_run_at(settings: TrendSettings, now: datetime | None = None) -> datetime:
    now = now or _now()
    hour, minute = _parse_schedule_time(settings.trend_schedule_time)
    mode = settings.trend_schedule_mode or "weekly"
    if mode == "interval":
        interval_hours = _parse_interval_hours(settings.trend_schedule_interval_hours)
        return now + timedelta(hours=interval_hours)

    timezone_name = getattr(settings, "trend_timezone", None)
    local_now = utc_naive_to_local(now, timezone_name)
    days = _parse_schedule_days(settings.trend_schedule_days_json)
    for day_offset in range(0, 14):
        candidate = (local_now + timedelta(days=day_offset)).replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        # datetime.weekday(): Monday=0；UI/API 保存 Monday=1 ... Sunday=7。
        if candidate > local_now and candidate.weekday() + 1 in days:
            return local_to_utc_naive(candidate)

    # 防御性兜底：配置异常时退回到明天同一时间。
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return local_to_utc_naive(candidate)


def _parse_schedule_days(value: str | None) -> set[int]:
    if not value:
        return {1, 2, 3, 4, 5, 6, 7}
    try:
        raw = json.loads(value)
    except json.JSONDecodeError:
        return {1, 2, 3, 4, 5, 6, 7}
    if not isinstance(raw, list):
        return {1, 2, 3, 4, 5, 6, 7}
    days = {day for day in raw if isinstance(day, int) and 1 <= day <= 7}
    return days or {1, 2, 3, 4, 5, 6, 7}


def _parse_interval_hours(value: int | None) -> int:
    try:
        hours = int(value or 24)
    except (TypeError, ValueError):
        return 24
    return max(1, min(hours, 24 * 30))


def _parse_schedule_time(value: str | None) -> tuple[int, int]:
    raw = value or "09:00"
    match = re.match(r"^(\d{1,2}):(\d{2})$", raw)
    if not match:
        return 9, 0
    hour = max(0, min(int(match.group(1)), 23))
    minute = max(0, min(int(match.group(2)), 59))
    return hour, minute


async def collect_trends(run_id: str) -> dict[str, int]:
    try:
        logger.info("Trend 采集开始 run_id=%s", run_id)
        with SessionLocal() as session:
            run = session.get(TrendRun, run_id)
            if run is None:
                raise ValueError(f"Trend run not found: {run_id}")
            settings = session.get(Settings, 1)
            if settings is None:
                settings = Settings(id=1)
                session.add(settings)
                session.commit()
                session.refresh(settings)

            run.status = "running"
            run.started_at = _now()
            run.updated_at = _now()
            run.error = None
            settings_snapshot = snapshot_trend_settings(settings)
            source_config = _load_source_config(settings_snapshot)
            rss_sources = [
                RssSourceConfig(
                    id=source.id,
                    name=source.name,
                    url=source.url,
                    limit=source.item_limit,
                )
                for source in (
                    session.query(TrendRssSource)
                    .filter(TrendRssSource.enabled.is_(True))
                    .order_by(TrendRssSource.created_at.asc())
                    .all()
                )
            ]
            brand_prompt = _truncate_llm_text(
                settings_snapshot.trend_brand_prompt or DEFAULT_TREND_PROMPT,
                MAX_TREND_BRAND_PROMPT_CHARS,
            )
            threshold = (
                settings_snapshot.trend_score_threshold
                if settings_snapshot.trend_score_threshold is not None
                else 70
            )
            result_limit = max(1, min(int(settings_snapshot.trend_result_limit or 20), 100))
            session.commit()
            logger.info(
                "Trend 采集配置已加载 run_id=%s threshold=%.1f result_limit=%d",
                run_id,
                threshold,
                result_limit,
            )

        query_sources_enabled = any(
            config.get("enabled")
            for source, config in source_config.items()
            if source != "google"
        )
        if not query_sources_enabled and not rss_sources:
            raise ValueError("没有启用可用的信息源")
        search_queries = (
            await plan_search_queries(settings_snapshot, brand_prompt, source_config, run_id=run_id)
            if query_sources_enabled
            else []
        )
        candidates = await _discover_candidates_from_queries(search_queries, source_config, rss_sources)
        with SessionLocal() as session:
            run = session.get(TrendRun, run_id)
            if run is None:
                raise ValueError(f"Trend run not found: {run_id}")
            run.candidate_count = len(candidates)
            run.updated_at = _now()
            session.commit()
        logger.info("Trend 候选发现完成 run_id=%s candidates=%d", run_id, len(candidates))

        saved = 0
        seen_evidence_urls: set[str] = set()
        for candidate in candidates:
            if saved >= result_limit:
                break
            evidence = [await _build_evidence(candidate)]
            seen_evidence_urls.add(canonical_url(candidate.url))
            logger.debug("Trend 候选开始评分 run_id=%s source=%s", run_id, candidate.source)
            try:
                result = await _score_with_follow_ups(
                    settings_snapshot,
                    brand_prompt,
                    evidence,
                    source_config,
                    seen_evidence_urls,
                )
            except Exception as exc:
                logger.warning(
                    "Trend 候选评分失败，已跳过 run_id=%s source=%s error_type=%s error=%s",
                    run_id,
                    candidate.source,
                    type(exc).__name__,
                    str(exc)[:500],
                )
                continue
            if _score_value(result.get("score")) < threshold:
                logger.debug(
                    "Trend 候选评分低于阈值 run_id=%s score=%.1f threshold=%.1f",
                    run_id,
                    _score_value(result.get("score")),
                    threshold,
                )
                continue

            resources = _validated_resources(result.get("resources"), evidence)
            if not resources:
                logger.info("Trend 候选缺少可信资源，已跳过: %s", candidate.url)
                continue
            with SessionLocal() as session:
                _upsert_trend_item(session, result, resources)
            saved += 1
            logger.info("Trend 候选已入库 run_id=%s saved=%d score=%.1f", run_id, saved, _score_value(result.get("score")))

        finished = _now()
        with SessionLocal() as session:
            run = session.get(TrendRun, run_id)
            if run is None:
                raise ValueError(f"Trend run not found: {run_id}")
            settings = session.get(Settings, 1)
            run.status = "done"
            run.saved_count = saved
            run.finished_at = finished
            run.updated_at = finished
            if settings is not None:
                settings.trend_last_run_at = finished
                if settings.trend_schedule_enabled:
                    settings.trend_next_run_at = calculate_next_run_at(settings, finished)
            session.commit()
            candidate_count = run.candidate_count
        logger.info("Trend 采集完成 run_id=%s candidates=%d saved=%d", run_id, candidate_count, saved)
        return {"candidate_count": candidate_count, "saved_count": saved}
    except Exception as exc:
        finished = _now()
        with SessionLocal() as session:
            run = session.get(TrendRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error = str(exc)[:2000]
                run.finished_at = finished
                run.updated_at = finished
                session.commit()
        logger.exception("Trend 采集失败 run_id=%s error=%s", run_id, exc)
        raise


async def plan_search_queries(
    settings: TrendSettings,
    brand_prompt: str,
    source_config: dict[str, Any],
    *,
    run_id: str | None = None,
) -> list[str]:
    """让 LLM 根据完整 Brand Brain 规划 source 搜索 query。"""
    enabled_sources = [
        {"source": source, "limit": config.get("limit")}
        for source, config in normalize_source_config(source_config).items()
        if source != "google" and config.get("enabled")
    ]
    if not enabled_sources:
        raise ValueError("搜索 query 生成失败：没有启用可用的信息源")

    client, model = _get_trend_client(settings)
    payload = {
        "brand_brain_prompt": _truncate_llm_text(brand_prompt, MAX_TREND_BRAND_PROMPT_CHARS),
        "enabled_sources": enabled_sources,
        "max_queries": MAX_TREND_SEARCH_QUERIES,
        "max_query_chars": MAX_TREND_SEARCH_QUERY_CHARS,
    }
    logger.info(
        "Trend 查询规划开始 run_id=%s model=%s sources=%s brand_prompt_chars=%d max_queries=%d",
        run_id,
        model,
        [source["source"] for source in enabled_sources],
        len(payload["brand_brain_prompt"]),
        MAX_TREND_SEARCH_QUERIES,
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You plan search queries for trend discovery. "
                "Use the full Brand Brain prompt to infer search directions. "
                "Do not invent news, facts, URLs, sources, metrics, or quotes. "
                "Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "Create concise search queries suitable for GitHub repository search and "
                "Hacker News Algolia. Return JSON with exactly one key: queries. "
                "queries must be an array of 1 to 5 strings, each <= 120 characters. "
                "Prefer topic phrases over instructions or audience/persona text. "
                f"Input:\n{json.dumps(payload, ensure_ascii=False)}"
            ),
        },
    ]
    try:
        try:
            response = await asyncio.wait_for(
                _create_json_chat_completion(
                    client,
                    model=model,
                    messages=messages,
                    max_tokens=MAX_TREND_QUERY_PLAN_TOKENS,
                    temperature=0.1,
                ),
                timeout=TREND_LLM_TIMEOUT_SECONDS + 5,
            )
        except Exception as exc:
            raise ValueError(f"搜索 query 生成失败：{exc}") from exc
    finally:
        if not client.is_closed():
            await client.close()

    content, response_diagnostics = _query_plan_response_details(response)
    try:
        parsed = _parse_json_object(content)
    except Exception as exc:
        logger.warning(
            "Trend 查询规划返回无效 JSON run_id=%s model=%s choices=%d finish_reason=%s "
            "content_source=%s content_chars=%d content_sha256=%s has_refusal=%s "
            "has_reasoning_content=%s has_tool_calls=%s parse_error_type=%s",
            run_id,
            model,
            response_diagnostics["choice_count"],
            response_diagnostics["finish_reason"],
            response_diagnostics["content_source"],
            response_diagnostics["content_chars"],
            response_diagnostics["content_sha256"],
            response_diagnostics["has_refusal"],
            response_diagnostics["has_reasoning_content"],
            response_diagnostics["has_tool_calls"],
            type(exc).__name__,
        )
        raise ValueError(f"搜索 query 生成失败：LLM 返回不是有效 JSON: {exc}") from exc
    queries = _normalise_search_queries(parsed.get("queries"))
    if not queries:
        query_value = parsed.get("queries")
        logger.warning(
            "Trend 查询规划没有可用 queries run_id=%s model=%s choices=%d finish_reason=%s "
            "content_source=%s content_chars=%d content_sha256=%s has_refusal=%s "
            "has_reasoning_content=%s has_tool_calls=%s queries_present=%s queries_type=%s raw_query_count=%s "
            "normalised_query_count=%d",
            run_id,
            model,
            response_diagnostics["choice_count"],
            response_diagnostics["finish_reason"],
            response_diagnostics["content_source"],
            response_diagnostics["content_chars"],
            response_diagnostics["content_sha256"],
            response_diagnostics["has_refusal"],
            response_diagnostics["has_reasoning_content"],
            response_diagnostics["has_tool_calls"],
            "queries" in parsed,
            type(query_value).__name__,
            len(query_value) if isinstance(query_value, list) else None,
            len(queries),
        )
        raise ValueError("搜索 query 生成失败：LLM 没有返回可用 queries")
    logger.info(
        "Trend 搜索 query 已生成 run_id=%s model=%s count=%d content_source=%s content_sha256=%s",
        run_id,
        model,
        len(queries),
        response_diagnostics["content_source"],
        response_diagnostics["content_sha256"],
    )
    return queries


def _query_plan_response_details(response: Any) -> tuple[str, dict[str, Any]]:
    """提取 query planner 响应的非敏感诊断信息，不记录 prompt 或原始内容。"""
    choices = getattr(response, "choices", None)
    choice_count = len(choices) if isinstance(choices, list) else 0
    choice = choices[0] if choice_count else None
    message = getattr(choice, "message", None)
    raw_content = getattr(message, "content", None) if message is not None else None
    reasoning_content = getattr(message, "reasoning_content", None) if message is not None else None
    content = raw_content if isinstance(raw_content, str) else ""
    if content.strip():
        content_source = "content"
    elif isinstance(reasoning_content, str) and reasoning_content.strip():
        # 部分 OpenAI-compatible provider 会把 JSON-only 响应放在该字段。
        content = reasoning_content
        content_source = "reasoning_content"
    else:
        content_source = "empty"
    finish_reason = getattr(choice, "finish_reason", None)
    tool_calls = getattr(message, "tool_calls", None) if message is not None else None

    return content or "{}", {
        "choice_count": choice_count,
        "finish_reason": str(finish_reason) if finish_reason is not None else None,
        "content_source": content_source,
        "content_chars": len(content),
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()[:16] if content else None,
        "has_refusal": bool(getattr(message, "refusal", None)) if message is not None else False,
        "has_reasoning_content": bool(reasoning_content),
        "has_tool_calls": bool(tool_calls),
    }


async def _discover_candidates_from_queries(
    queries: list[str],
    source_config: dict[str, Any],
    rss_sources: list[RssSourceConfig] | None = None,
) -> list[TrendCandidate]:
    candidates: list[TrendCandidate] = []
    seen: set[str] = set()
    for query in queries:
        query_candidates = await discover_candidates(query, source_config)
        logger.info("Trend query 候选发现完成 query=%s candidates=%d", query, len(query_candidates))
        for candidate in query_candidates:
            key = canonical_url(candidate.url)
            if not key or key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    rss_candidates = await discover_rss_candidates(rss_sources or [])
    logger.info("Trend RSS 候选发现完成 candidates=%d", len(rss_candidates))
    for candidate in rss_candidates:
        key = canonical_url(candidate.url)
        if not key or key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return candidates


def _normalise_search_queries(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    queries: list[str] = []
    seen: set[str] = set()
    for item in value:
        query = _clean_text(str(item))[:MAX_TREND_SEARCH_QUERY_CHARS]
        key = query.lower()
        if not query or key in seen:
            continue
        queries.append(query)
        seen.add(key)
        if len(queries) >= MAX_TREND_SEARCH_QUERIES:
            break
    return queries


async def _score_with_follow_ups(
    settings: TrendSettings,
    brand_prompt: str,
    evidence: list[TrendEvidence],
    source_config: dict[str, Any],
    seen_urls: set[str],
) -> dict[str, Any]:
    result = await _evaluate_evidence(settings, brand_prompt, evidence)
    for _round in range(MAX_FOLLOW_UP_ROUNDS):
        if not result.get("needs_more_search"):
            break
        queries = result.get("follow_up_queries")
        if not isinstance(queries, list) or not queries:
            break
        added = 0
        for query in queries[:2]:
            if not isinstance(query, str) or not query.strip():
                continue
            follow_candidates = await discover_candidates(query, source_config, limit_override=3)
            for candidate in follow_candidates:
                key = canonical_url(candidate.url)
                if not key or key in seen_urls:
                    continue
                seen_urls.add(key)
                evidence.append(await _build_evidence(candidate))
                added += 1
                if len(evidence) >= MAX_EVIDENCE_ITEMS:
                    break
            if len(evidence) >= MAX_EVIDENCE_ITEMS:
                break
        if added == 0:
            break
        result = await _evaluate_evidence(settings, brand_prompt, evidence)
    return result


async def _build_evidence(candidate: TrendCandidate) -> TrendEvidence:
    fetched = await fetch_url_detail(candidate.url)
    logger.debug("Trend evidence 已构建 source=%s ok=%s", candidate.source, fetched.ok)
    return TrendEvidence(candidate=candidate, fetched=fetched)


async def fetch_url_detail(url: str) -> WebFetchResult:
    headers = {
        "User-Agent": "SparklingTrendBot/0.1 (+https://localhost)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0), follow_redirects=True, headers=headers) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_FETCH_BYTES:
                        break
                    chunks.append(chunk)
                content_type = response.headers.get("content-type", "")
                raw = b"".join(chunks)
                text = raw.decode(response.encoding or "utf-8", errors="replace")
                title, description, body_text = _extract_page_text(text, content_type)
                return WebFetchResult(
                    url=url,
                    final_url=str(response.url),
                    ok=True,
                    title=title,
                    description=description,
                    text=body_text,
                )
    except Exception as exc:
        logger.warning("Trend URL 抓取失败 url=%s error=%s", url, exc)
        return WebFetchResult(url=url, final_url=url, ok=False, error=str(exc)[:500])


def _extract_page_text(raw: str, content_type: str) -> tuple[str | None, str | None, str]:
    if "html" not in content_type.lower():
        return None, None, _clean_text(raw)[:MAX_PAGE_TEXT_CHARS]

    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, flags=re.I | re.S)
    title = _clean_text(title_match.group(1)) if title_match else None
    desc_match = re.search(
        r"<meta[^>]+(?:name|property)=[\"'](?:description|og:description)[\"'][^>]+content=[\"'](.*?)[\"'][^>]*>",
        raw,
        flags=re.I | re.S,
    )
    description = _clean_text(desc_match.group(1)) if desc_match else None
    body = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", raw, flags=re.I | re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    return title, description, _clean_text(body)[:MAX_PAGE_TEXT_CHARS]


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _truncate_llm_text(value: str | None, max_chars: int) -> str:
    return _clean_text(value)[:max_chars]


async def _evaluate_evidence(
    settings: TrendSettings,
    brand_prompt: str,
    evidence: list[TrendEvidence],
) -> dict[str, Any]:
    client, model = _get_trend_client(settings)
    safe_brand_prompt = _truncate_llm_text(brand_prompt, MAX_TREND_BRAND_PROMPT_CHARS)
    payload = {
        "brand_prompt": safe_brand_prompt,
        "evidence": [item.to_llm_dict() for item in evidence[:MAX_EVIDENCE_ITEMS]],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You are a trend analyst for a solo media creator. "
                "Use only the supplied evidence. Do not invent facts, URLs, sources, metrics, or quotes. "
                "Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "Score whether this evidence can become a timely social-media content topic. "
                "The score is 0-100 and should combine relevance to brand_prompt, novelty, timeliness, "
                "audience value, and source credibility. If evidence is insufficient, set needs_more_search=true "
                "and provide up to two follow_up_queries. Required JSON keys: "
                "title, category, score, scoring_reason, core_insight, content, tags, resources, "
                "needs_more_search, follow_up_queries. resources must be an array of objects with title, url, source. "
                f"Input:\n{json.dumps(payload, ensure_ascii=False)}"
            ),
        },
    ]
    try:
        response = await asyncio.wait_for(
            _create_json_chat_completion(
                client,
                model=model,
                messages=messages,
                max_tokens=MAX_TREND_COMPLETION_TOKENS,
                temperature=0.2,
            ),
            timeout=TREND_LLM_TIMEOUT_SECONDS + 5,
        )
    finally:
        if not client.is_closed():
            await client.close()
    content, response_diagnostics = _query_plan_response_details(response)
    try:
        parsed = _parse_json_object(content)
    except Exception as exc:
        logger.warning(
            "Trend 评分返回无效 JSON model=%s choices=%d finish_reason=%s content_source=%s "
            "content_chars=%d content_sha256=%s has_refusal=%s has_reasoning_content=%s "
            "has_tool_calls=%s parse_error_type=%s evidence_count=%d",
            model,
            response_diagnostics["choice_count"],
            response_diagnostics["finish_reason"],
            response_diagnostics["content_source"],
            response_diagnostics["content_chars"],
            response_diagnostics["content_sha256"],
            response_diagnostics["has_refusal"],
            response_diagnostics["has_reasoning_content"],
            response_diagnostics["has_tool_calls"],
            type(exc).__name__,
            len(evidence),
        )
        raise
    parsed["score"] = _score_value(parsed.get("score"))
    logger.debug(
        "Trend LLM 评分完成 model=%s score=%.1f evidence_count=%d content_source=%s",
        model,
        parsed["score"],
        len(evidence),
        response_diagnostics["content_source"],
    )
    return parsed


def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("LLM 返回的 JSON 不是 object")
    return value


def _score_value(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(score, 100))


def _validated_resources(raw_resources: Any, evidence: list[TrendEvidence]) -> list[dict[str, str]]:
    observed = _observed_resource_map(evidence)
    valid: list[dict[str, str]] = []
    seen: set[str] = set()
    if isinstance(raw_resources, list):
        for item in raw_resources:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            key = canonical_url(url)
            if not key or key not in observed or key in seen:
                continue
            base = observed[key]
            valid.append(
                {
                    "title": str(item.get("title") or base["title"]),
                    "url": base["url"],
                    "source": base["source"],
                }
            )
            seen.add(key)
    # 确保实际使用过的来源不会因为 LLM 漏填而丢失。
    for key, item in observed.items():
        if key in seen:
            continue
        valid.append(item)
        seen.add(key)
    return valid


def _observed_resource_map(evidence: list[TrendEvidence]) -> dict[str, dict[str, str]]:
    observed: dict[str, dict[str, str]] = {}
    for item in evidence:
        candidate = item.candidate
        for url in _candidate_urls(item):
            key = canonical_url(url)
            if not key:
                continue
            observed[key] = {
                "title": item.fetched.title or candidate.title,
                "url": url,
                "source": candidate.source,
            }
    return observed


def _candidate_urls(evidence: TrendEvidence) -> list[str]:
    urls = [evidence.candidate.url]
    if evidence.fetched.final_url and evidence.fetched.final_url != evidence.candidate.url:
        urls.append(evidence.fetched.final_url)
    metadata = evidence.candidate.metadata or {}
    for key in ("hn_url",):
        value = metadata.get(key)
        if value:
            urls.append(str(value))
    return urls


def _upsert_trend_item(session: Session, result: dict[str, Any], resources: list[dict[str, str]]) -> TrendItem:
    now = _now()
    title = _clean_text(str(result.get("title") or ""))[:500] or "Untitled trend"
    tags = _normalise_tags(result.get("tags"))
    fingerprint = _fingerprint(title, resources)
    existing = session.query(TrendItem).filter(TrendItem.fingerprint == fingerprint).first()
    target = existing or TrendItem(
        fingerprint=fingerprint,
        first_seen_at=now,
        created_at=now,
    )
    target.title = title
    target.category = _clean_text(str(result.get("category") or ""))[:120] or None
    target.score = _score_value(result.get("score"))
    target.scoring_reason = _clean_text(str(result.get("scoring_reason") or ""))[:1000] or None
    target.core_insight = _clean_text(str(result.get("core_insight") or ""))[:2000] or None
    target.content = _clean_text(str(result.get("content") or ""))[:8000] or None
    target.tags_json = json.dumps(_merge_tags(_json_list(target.tags_json), tags), ensure_ascii=False)
    target.resources_json = json.dumps(
        _merge_resources(_json_list(target.resources_json), resources),
        ensure_ascii=False,
    )
    target.last_seen_at = now
    target.updated_at = now
    if existing is None:
        session.add(target)
    session.commit()
    session.refresh(target)
    return target


def _fingerprint(title: str, resources: list[dict[str, str]]) -> str:
    primary_url = canonical_url(resources[0]["url"]) if resources else ""
    base = primary_url or re.sub(r"\W+", " ", title.lower()).strip()
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def _normalise_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for item in value:
        tag = _clean_text(str(item)).strip("#")[:40]
        if tag and tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
        if len(tags) >= 8:
            break
    return tags


def _json_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _merge_tags(existing: list[Any], new: list[str]) -> list[str]:
    merged: list[str] = []
    for item in [*existing, *new]:
        tag = _clean_text(str(item)).strip("#")[:40]
        if tag and tag.lower() not in {t.lower() for t in merged}:
            merged.append(tag)
        if len(merged) >= 12:
            break
    return merged


def _merge_resources(existing: list[Any], new: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in [*existing, *new]:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        key = canonical_url(url)
        if not key or key in seen:
            continue
        merged.append(
            {
                "title": _clean_text(str(item.get("title") or url))[:300],
                "url": url,
                "source": _clean_text(str(item.get("source") or "web"))[:80],
            }
        )
        seen.add(key)
        if len(merged) >= 12:
            break
    return merged
