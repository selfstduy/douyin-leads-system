import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.deps import async_session_factory
from app.models.topic_monitor import TopicMonitor
from app.models.monitor import MonitorAccount
from app.models.video import Video
from app.services.crawler_service import (
    crawl_account_comments,
    crawl_topic_comments,
    sync_account_videos,
    poll_video_comments,
    should_poll_video,
)
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# ── 辅助：运行异步协程 ──────────────────────────────────────────────────────

def _run_async(coro):
    """在 Celery 同步任务中运行异步协程"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        loop.close()
        return result
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(coro)
        loop.close()
        return result


# ── 原有采集任务（保留兼容） ─────────────────────────────────────────────────

@celery_app.task(name="app.tasks.crawler_tasks.poll_all_monitors", bind=True, max_retries=3)
def poll_all_monitors(self):
    """
    扫描所有active状态的monitor_accounts，为每个创建子任务。
    由beat每分钟触发一次。
    """
    async def _poll():
        async with async_session_factory() as db:
            result = await db.execute(
                select(MonitorAccount.id, MonitorAccount.status).where(
                    MonitorAccount.status == "active"
                )
            )
            accounts = result.all()
            return [row[0] for row in accounts]

    account_ids = _run_async(_poll())

    logger.info("Found %d active monitor accounts, dispatching crawl tasks", len(account_ids))

    for monitor_id in account_ids:
        try:
            crawl_single_monitor.delay(monitor_id)
        except Exception as exc:
            logger.error("Failed to dispatch task for monitor %d: %s", monitor_id, exc)


@celery_app.task(
    name="app.tasks.crawler_tasks.crawl_single_monitor",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def crawl_single_monitor(self, monitor_id: int):
    """单个账号的采集任务，异常不影响其他账号"""
    async def _crawl():
        async with async_session_factory() as db:
            try:
                result = await crawl_account_comments(db, monitor_id)
                await db.commit()
                return result
            except Exception as exc:
                await db.rollback()
                raise exc

    try:
        result = _run_async(_crawl())
        logger.info("Crawl completed for monitor %d: %s", monitor_id, result)
        return result
    except Exception as exc:
        logger.error("Crawl failed for monitor %d: %s", monitor_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for monitor %d", monitor_id)
            return {"status": "error", "monitor_id": monitor_id, "error": str(exc)}


@celery_app.task(name="app.tasks.crawler_tasks.poll_topic_monitors", bind=True, max_retries=3)
def poll_topic_monitors(self):
    """
    扫描所有active状态的topic_monitors，为每个创建子任务。
    由beat每分钟触发一次。
    """
    async def _poll():
        async with async_session_factory() as db:
            result = await db.execute(
                select(TopicMonitor.id, TopicMonitor.status).where(
                    TopicMonitor.status == "active"
                )
            )
            monitors = result.all()
            return [row[0] for row in monitors]

    monitor_ids = _run_async(_poll())

    logger.info("Found %d active topic monitors, dispatching crawl tasks", len(monitor_ids))

    for monitor_id in monitor_ids:
        try:
            crawl_single_topic_monitor.delay(monitor_id)
        except Exception as exc:
            logger.error("Failed to dispatch topic task for monitor %d: %s", monitor_id, exc)


@celery_app.task(
    name="app.tasks.crawler_tasks.crawl_single_topic_monitor",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def crawl_single_topic_monitor(self, topic_monitor_id: int):
    """单个话题的采集任务，异常不影响其他话题"""
    async def _crawl():
        async with async_session_factory() as db:
            try:
                result = await crawl_topic_comments(db, topic_monitor_id)
                await db.commit()
                return result
            except Exception as exc:
                await db.rollback()
                raise exc

    try:
        result = _run_async(_crawl())
        logger.info("Topic crawl completed for monitor %d: %s", topic_monitor_id, result)
        return result
    except Exception as exc:
        logger.error("Topic crawl failed for monitor %d: %s", topic_monitor_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for topic monitor %d", topic_monitor_id)
            return {"status": "error", "topic_monitor_id": topic_monitor_id, "error": str(exc)}


# ── 视频生命周期管理任务 ─────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.crawler_tasks.sync_all_account_videos",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def sync_all_account_videos(self):
    """
    每 ACCOUNT_SYNC_INTERVAL_HOURS 小时执行一次：
    遍历所有 active 的 monitor_accounts，调用 sync_account_videos 同步视频列表。
    """
    async def _get_active_accounts():
        async with async_session_factory() as db:
            result = await db.execute(
                select(MonitorAccount.id).where(MonitorAccount.status == "active")
            )
            return [row[0] for row in result.all()]

    async def _sync_one(account_id: int):
        async with async_session_factory() as db:
            try:
                result = await sync_account_videos(db, account_id)
                await db.commit()
                return result
            except Exception as exc:
                await db.rollback()
                logger.error("sync_account_videos failed for account %d: %s", account_id, exc)
                return {"status": "error", "account_id": account_id, "error": str(exc)}

    try:
        account_ids = _run_async(_get_active_accounts())
        logger.info("sync_all_account_videos: found %d active accounts", len(account_ids))

        results = []
        for account_id in account_ids:
            try:
                result = _run_async(_sync_one(account_id))
                results.append(result)
            except Exception as exc:
                logger.error("sync_all_account_videos: failed for account %d: %s", account_id, exc)
                results.append({"status": "error", "account_id": account_id, "error": str(exc)})

        return {"total_accounts": len(account_ids), "results": results}
    except Exception as exc:
        logger.error("sync_all_account_videos failed: %s", exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"status": "error", "error": str(exc)}


@celery_app.task(name="app.tasks.crawler_tasks.poll_all_video_comments", bind=True, max_retries=3)
def poll_all_video_comments(self):
    """
    每分钟执行一次：
    - 只轮询 status=active 的视频
    - 根据 should_poll_video 判断是否到时间
    - 并发控制：最大 MAX_CONCURRENT_VIDEO_POLL 并发
    """
    async def _get_pollable_videos():
        async with async_session_factory() as db:
            result = await db.execute(
                select(Video).where(Video.status == "active")
            )
            videos = result.scalars().all()
            # 在内存中过滤出需要轮询的视频
            return [(v.id, v.video_id) for v in videos if should_poll_video(v)]

    async def _poll_one(video_db_id: int, sem: asyncio.Semaphore):
        async with sem:
            async with async_session_factory() as db:
                try:
                    result = await poll_video_comments(db, video_db_id)
                    await db.commit()
                    return result
                except Exception as exc:
                    await db.rollback()
                    logger.error("poll_video_comments failed for video %d: %s", video_db_id, exc)
                    return {"status": "error", "video_id": video_db_id, "error": str(exc)}

    async def _run_all():
        pollable = await _get_pollable_videos()
        if not pollable:
            return {"polled": 0, "results": []}

        sem = asyncio.Semaphore(settings.MAX_CONCURRENT_VIDEO_POLL)
        tasks = [_poll_one(vid_db_id, sem) for vid_db_id, _ in pollable]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final_results = []
        for r in results:
            if isinstance(r, Exception):
                final_results.append({"status": "error", "error": str(r)})
            else:
                final_results.append(r)

        return {"polled": len(pollable), "results": final_results}

    try:
        result = _run_async(_run_all())
        logger.info("poll_all_video_comments: %s", {k: v for k, v in result.items() if k != "results"})
        return result
    except Exception as exc:
        logger.error("poll_all_video_comments failed: %s", exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"status": "error", "error": str(exc)}


@celery_app.task(name="app.tasks.crawler_tasks.expire_old_videos", bind=True, max_retries=2)
def expire_old_videos(self):
    """
    每小时执行一次：
    将发布超过 VIDEO_LIFECYCLE_DAYS 天的视频标记为 expired。
    """
    from datetime import datetime, timedelta, timezone

    async def _expire():
        async with async_session_factory() as db:
            now = datetime.now(timezone.utc)
            cutoff = now - timedelta(days=settings.VIDEO_LIFECYCLE_DAYS)

            result = await db.execute(
                select(Video).where(
                    Video.status != "expired",
                    Video.publish_time < cutoff,
                    Video.publish_time.isnot(None),
                )
            )
            videos = result.scalars().all()
            count = 0
            for v in videos:
                v.status = "expired"
                count += 1

            await db.flush()
            await db.commit()
            return count

    try:
        count = _run_async(_expire())
        logger.info("expire_old_videos: marked %d videos as expired", count)
        return {"expired_count": count}
    except Exception as exc:
        logger.error("expire_old_videos failed: %s", exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {"status": "error", "error": str(exc)}
