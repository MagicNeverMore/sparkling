"""为 Social Media Analysis 写入可重复生成的 YouTube 日级 mock 数据。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal, get_engine, uses_postgresql
from app.logger import get_logger, setup_logging
from app.migrations import run_migrations_for_engine
from app.models import SocialMediaDataset, SocialMediaVideoSnapshot
from app.services.social_media.config import load_social_media_config, update_social_media_config
from app.time_utils import utc_isoformat

logger = get_logger(__name__)
MOCK_CHANNEL_ID = "mock-youtube-channel"

VIDEOS = [
    ("mock-ai-workflow", "I Built an AI Workflow That Saves 10 Hours a Week", 742, 95),
    ("mock-creator-tools", "7 Creator Tools I Actually Use Every Day", 518, 72),
    ("mock-weekly-news", "This Week in AI: Agents, Models and Open Source", 964, 50),
    ("mock-react-performance", "React Performance: Fixing a Slow Dashboard", 1286, 43),
    ("mock-content-system", "My Simple Content System for Consistent Publishing", 634, 31),
    ("mock-short-prompt", "One Prompt Trick for Better AI Answers #Shorts", 48, 19),
    ("mock-studio-tour", "Behind the Scenes: My Minimal Home Studio", 455, 12),
    ("mock-live-replay", "Live Replay: Building a Small SaaS from Scratch", 3725, 7),
]


def seed() -> tuple[str, int, int]:
    config = load_social_media_config()
    if config.youtube_connected and config.youtube_channel_id != MOCK_CHANNEL_ID:
        raise RuntimeError("当前已连接真实 YouTube 频道；为避免污染真实账号数据，未写入 mock")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    latest_metric_date = now.date() - timedelta(days=1)
    metric_dates = [latest_metric_date - timedelta(days=offset) for offset in (2, 1, 0)]

    with SessionLocal() as session:
        for day_index, metric_date in enumerate(metric_dates):
            metric_date_text = metric_date.isoformat()
            dataset = (
                session.query(SocialMediaDataset)
                .filter(SocialMediaDataset.platform == "youtube")
                .filter(SocialMediaDataset.external_account_id == MOCK_CHANNEL_ID)
                .filter(SocialMediaDataset.metric_date == metric_date_text)
                .one_or_none()
            )
            if dataset is None:
                dataset = SocialMediaDataset(
                    platform="youtube",
                    external_account_id=MOCK_CHANNEL_ID,
                    metric_date=metric_date_text,
                    status="complete",
                    collected_at=now,
                )
                session.add(dataset)
                session.flush()
            else:
                session.query(SocialMediaVideoSnapshot).filter(
                    SocialMediaVideoSnapshot.dataset_id == dataset.id
                ).delete(synchronize_session=False)
                dataset.status = "complete"
                dataset.collected_at = now
                dataset.updated_at = now

            for video_index, (video_id, title, duration, age_days) in enumerate(VIDEOS):
                scale = 1 + day_index * 0.12
                views = round((18420 / (video_index + 1)) * scale)
                gained = max(0, round((42 / (video_index + 1)) * scale))
                lost = 1 if video_index < 3 and day_index == 1 else 0
                session.add(
                    SocialMediaVideoSnapshot(
                        dataset_id=dataset.id,
                        external_video_id=video_id,
                        title=title,
                        published_at=now - timedelta(days=age_days, hours=video_index),
                        duration_seconds=duration,
                        views=views,
                        ctr=round(7.8 - video_index * 0.62 + day_index * 0.15, 2),
                        average_view_duration_seconds=round(duration * (0.57 - video_index * 0.025), 1),
                        average_view_percentage=round((0.57 - video_index * 0.025) * 100, 2),
                        subscribers_gained=gained,
                        subscribers_lost=lost,
                        net_subscribers=gained - lost,
                    )
                )
        session.commit()

    update_social_media_config(
        youtube_channel_id=MOCK_CHANNEL_ID,
        youtube_channel_title="Sparkling Mock Channel",
        last_run_at=utc_isoformat(now),
        next_run_at=None,
    )
    return latest_metric_date.isoformat(), len(metric_dates), len(VIDEOS)


def main() -> None:
    setup_logging()
    run_migrations_for_engine(get_engine(), render_as_batch=not uses_postgresql())
    metric_date, day_count, video_count = seed()
    logger.info(
        "Social Media mock 数据已写入 metric_date=%s days=%d videos=%d",
        metric_date,
        day_count,
        video_count,
    )
    print(f"Seeded {video_count} videos across {day_count} days. Latest metric_date: {metric_date}")


if __name__ == "__main__":
    main()
