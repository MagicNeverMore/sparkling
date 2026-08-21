"""选题库 CRUD、封面和社媒发布关联。"""
from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ...config import config
from ...db import get_current_database_config, get_session
from ...logger import get_logger
from ...models import ContentTopic, ContentTopicPublication, SocialMediaVideo, UserTask
from ...time_utils import get_timezone, utc_isoformat, utc_naive_to_local

router = APIRouter()
logger = get_logger(__name__)

TopicStatus = Literal["not_started", "working", "published"]
_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
_MAX_COVER_SIZE = 10 * 1024 * 1024
_PLATFORMS = {"youtube", "bilibili", "douyin", "xiaohongshu", "wechat_channels"}


class PublicationIn(BaseModel):
    platform: str = Field(min_length=1, max_length=80)
    social_media_video_id: str | None = None

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        if value not in _PLATFORMS:
            raise ValueError("不支持的发布平台")
        return value


class PublicationOut(PublicationIn):
    id: str
    video_title: str | None = None
    external_video_id: str | None = None


class TopicCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    category: str | None = Field(default=None, max_length=120)
    status: TopicStatus = "not_started"
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    timezone: str = "UTC"
    publications: list[PublicationIn] = Field(default_factory=list)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        get_timezone(value)
        return value


class TopicPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    category: str | None = Field(default=None, max_length=120)
    status: TopicStatus | None = None
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    timezone: str = "UTC"
    publications: list[PublicationIn] | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        get_timezone(value)
        return value


class TopicOut(BaseModel):
    id: str
    title: str
    description: str | None
    category: str | None
    status: TopicStatus
    scheduled_at: str | None
    published_at: str | None
    cover_url: str | None
    task_id: str | None
    task_completed: bool | None
    publications: list[PublicationOut]
    created_at: str
    updated_at: str


class TopicListOut(BaseModel):
    items: list[TopicOut]
    categories: list[str]


class VideoOut(BaseModel):
    id: str
    title: str
    platform: str
    external_video_id: str
    published_at: str


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _cover_dir() -> Path:
    db_path = get_current_database_config().db_path or config.db_path
    return Path(db_path).expanduser().resolve().parent / "uploads" / "topic-covers"


def _remove_cover(cover_path: str | None) -> None:
    if not cover_path:
        return
    path = _cover_dir() / Path(cover_path).name
    if path.is_file():
        path.unlink()


def _task_due_date(topic: ContentTopic, timezone_name: str) -> str | None:
    if topic.scheduled_at is None:
        return None
    return utc_naive_to_local(topic.scheduled_at, timezone_name).date().isoformat()


def _sync_task(topic: ContentTopic, session: Session, timezone_name: str) -> None:
    task = session.get(UserTask, topic.task_id) if topic.task_id else None
    if topic.task_id and task is None:
        topic.task_id = None
    if topic.status == "working":
        if task is None:
            task = UserTask(
                title=topic.title,
                description=topic.description,
                category="自媒体",
                due_date=_task_due_date(topic, timezone_name),
            )
            session.add(task)
            session.flush()
            topic.task_id = task.id
        else:
            task.due_date = _task_due_date(topic, timezone_name)
            task.updated_at = datetime.utcnow()
    elif topic.status == "published" and task is not None and not task.completed:
        task.completed = True
        task.completed_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()


def _validate_publications(items: list[PublicationIn], session: Session) -> dict[str, SocialMediaVideo]:
    ids = {item.social_media_video_id for item in items if item.social_media_video_id}
    videos = {video.id: video for video in session.query(SocialMediaVideo).filter(SocialMediaVideo.id.in_(ids)).all()} if ids else {}
    missing = ids - videos.keys()
    if missing:
        raise HTTPException(status_code=422, detail="关联的视频不存在")
    for item in items:
        if item.social_media_video_id:
            item.platform = videos[item.social_media_video_id].platform
    return videos


def _replace_publications(topic: ContentTopic, items: list[PublicationIn], session: Session) -> None:
    _validate_publications(items, session)
    session.query(ContentTopicPublication).filter_by(topic_id=topic.id).delete()
    session.add_all([
        ContentTopicPublication(topic_id=topic.id, platform=item.platform, social_media_video_id=item.social_media_video_id)
        for item in items
    ])


def _to_out(topic: ContentTopic, session: Session) -> TopicOut:
    links = session.query(ContentTopicPublication).filter_by(topic_id=topic.id).all()
    video_ids = [link.social_media_video_id for link in links if link.social_media_video_id]
    videos = {item.id: item for item in session.query(SocialMediaVideo).filter(SocialMediaVideo.id.in_(video_ids)).all()} if video_ids else {}
    task = session.get(UserTask, topic.task_id) if topic.task_id else None
    return TopicOut(
        id=topic.id, title=topic.title, description=topic.description, category=topic.category,
        status=topic.status, scheduled_at=utc_isoformat(topic.scheduled_at) if topic.scheduled_at else None,
        published_at=utc_isoformat(topic.published_at) if topic.published_at else None,
        cover_url=f"/api/social-media/topic/{topic.id}/cover" if topic.cover_path else None,
        task_id=topic.task_id, task_completed=task.completed if task else None,
        publications=[PublicationOut(id=link.id, platform=link.platform, social_media_video_id=link.social_media_video_id,
            video_title=videos[link.social_media_video_id].title if link.social_media_video_id in videos else None,
            external_video_id=videos[link.social_media_video_id].external_video_id if link.social_media_video_id in videos else None)
            for link in links],
        created_at=utc_isoformat(topic.created_at), updated_at=utc_isoformat(topic.updated_at),
    )


@router.get("", response_model=TopicListOut)
def list_topics(query: str | None = Query(default=None), status: TopicStatus | None = None,
                category: str | None = None, session: Session = Depends(get_session)) -> TopicListOut:
    topics = session.query(ContentTopic)
    if query:
        pattern = f"%{query.strip()}%"
        topics = topics.filter(or_(ContentTopic.title.ilike(pattern), ContentTopic.description.ilike(pattern)))
    if status:
        topics = topics.filter(ContentTopic.status == status)
    if category:
        topics = topics.filter(ContentTopic.category == category)
    items = topics.order_by(ContentTopic.updated_at.desc()).all()
    categories = [value for (value,) in session.query(ContentTopic.category).filter(ContentTopic.category.is_not(None)).distinct().order_by(ContentTopic.category).all()]
    logger.info("topic.list query=%s status=%s category=%s count=%d", query, status, category, len(items))
    return TopicListOut(items=[_to_out(topic, session) for topic in items], categories=categories)


@router.get("/available", response_model=list[TopicOut])
def list_available_topics(session: Session = Depends(get_session)) -> list[TopicOut]:
    topics = session.query(ContentTopic).filter(ContentTopic.status == "not_started").order_by(ContentTopic.title).all()
    logger.info("topic.available_list count=%d", len(topics))
    return [_to_out(topic, session) for topic in topics]


@router.get("/videos", response_model=list[VideoOut])
def list_topic_videos(
    platform: str = Query(default="youtube"),
    query: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[VideoOut]:
    videos = session.query(SocialMediaVideo).filter(SocialMediaVideo.platform == platform)
    if query:
        videos = videos.filter(SocialMediaVideo.title.ilike(f"%{query.strip()}%"))
    items = videos.order_by(SocialMediaVideo.published_at.desc()).limit(100).all()
    logger.info("topic.video_search platform=%s query=%s count=%d", platform, query, len(items))
    return [VideoOut(id=item.id, title=item.title, platform=item.platform, external_video_id=item.external_video_id,
        published_at=utc_isoformat(item.published_at)) for item in items]


@router.post("", response_model=TopicOut, status_code=201)
def create_topic(body: TopicCreate, session: Session = Depends(get_session)) -> TopicOut:
    publications = _validate_publications(body.publications, session)
    topic = ContentTopic(title=body.title.strip(), description=body.description, category=body.category,
        status=body.status, scheduled_at=_utc_naive(body.scheduled_at), published_at=_utc_naive(body.published_at))
    session.add(topic)
    session.flush()
    session.add_all([ContentTopicPublication(topic_id=topic.id, platform=publications[item.social_media_video_id].platform if item.social_media_video_id else item.platform, social_media_video_id=item.social_media_video_id) for item in body.publications])
    _sync_task(topic, session, body.timezone)
    session.commit()
    session.refresh(topic)
    logger.info("topic.created topic_id=%s status=%s publications=%d task_id=%s", topic.id, topic.status, len(body.publications), topic.task_id)
    return _to_out(topic, session)


@router.get("/{topic_id}", response_model=TopicOut)
def get_topic(topic_id: str, session: Session = Depends(get_session)) -> TopicOut:
    topic = session.get(ContentTopic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="选题不存在")
    logger.info("topic.read topic_id=%s", topic_id)
    return _to_out(topic, session)


@router.patch("/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: str, body: TopicPatch, session: Session = Depends(get_session)) -> TopicOut:
    topic = session.get(ContentTopic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="选题不存在")
    for field in ("title", "description", "category", "status"):
        if field in body.model_fields_set:
            setattr(topic, field, getattr(body, field))
    if "scheduled_at" in body.model_fields_set:
        topic.scheduled_at = _utc_naive(body.scheduled_at)
    if "published_at" in body.model_fields_set:
        topic.published_at = _utc_naive(body.published_at)
    if body.publications is not None:
        _replace_publications(topic, body.publications, session)
    topic.updated_at = datetime.utcnow()
    _sync_task(topic, session, body.timezone)
    session.commit()
    session.refresh(topic)
    logger.info("topic.updated topic_id=%s fields=%s status=%s task_id=%s", topic.id, sorted(body.model_fields_set), topic.status, topic.task_id)
    return _to_out(topic, session)


@router.delete("/{topic_id}", status_code=204)
def delete_topic(topic_id: str, session: Session = Depends(get_session)) -> None:
    topic = session.get(ContentTopic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="选题不存在")
    _remove_cover(topic.cover_path)
    session.delete(topic)
    session.commit()
    logger.info("topic.deleted topic_id=%s", topic_id)


@router.get("/{topic_id}/cover")
def get_cover(topic_id: str, session: Session = Depends(get_session)) -> FileResponse:
    topic = session.get(ContentTopic, topic_id)
    if topic is None or not topic.cover_path:
        raise HTTPException(status_code=404, detail="封面不存在")
    path = _cover_dir() / Path(topic.cover_path).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="封面文件不存在")
    logger.info("topic.cover_read topic_id=%s", topic_id)
    return FileResponse(path)


@router.post("/{topic_id}/cover", response_model=TopicOut)
def upload_cover(topic_id: str, file: UploadFile = File(...), session: Session = Depends(get_session)) -> TopicOut:
    topic = session.get(ContentTopic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="选题不存在")
    suffix = _IMAGE_TYPES.get(file.content_type or "")
    if suffix is None:
        raise HTTPException(status_code=415, detail="仅支持 PNG、JPEG、WebP、GIF 图片")
    directory = _cover_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{uuid.uuid4().hex}{suffix}"
    with target.open("wb") as output:
        shutil.copyfileobj(file.file, output, length=1024 * 1024)
    if target.stat().st_size > _MAX_COVER_SIZE:
        target.unlink()
        raise HTTPException(status_code=413, detail="封面不能超过 10 MB")
    _remove_cover(topic.cover_path)
    topic.cover_path = target.name
    topic.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(topic)
    logger.info("topic.cover_uploaded topic_id=%s filename=%s bytes=%d", topic_id, target.name, target.stat().st_size)
    return _to_out(topic, session)


@router.delete("/{topic_id}/cover", response_model=TopicOut)
def delete_cover(topic_id: str, session: Session = Depends(get_session)) -> TopicOut:
    topic = session.get(ContentTopic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="选题不存在")
    _remove_cover(topic.cover_path)
    topic.cover_path = None
    topic.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(topic)
    logger.info("topic.cover_deleted topic_id=%s", topic_id)
    return _to_out(topic, session)
