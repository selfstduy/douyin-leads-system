"""私信队列Celery定时任务 — 队列处理与溢出迁移。"""
import asyncio
import logging

from app.core.deps import async_session_factory
from app.services.dm_queue_service import dm_queue_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.dm_queue_tasks.process_dm_queue",
    bind=True,
    max_retries=0,
)
def process_dm_queue(self):
    """每分钟检查队列并发送

    由beat每分钟触发一次，每次最多处理DM_BATCH_SIZE条。
    """
    async def _process():
        async with async_session_factory() as db:
            try:
                result = await dm_queue_service.process_queue(db)
                await db.commit()
                return result
            except Exception as exc:
                await db.rollback()
                raise exc

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_process())
        loop.close()

        if result["sent"] > 0 or result["failed"] > 0 or result["skipped"] > 0:
            logger.info(
                "process_dm_queue: sent=%d failed=%d skipped=%d reason=%s",
                result["sent"], result["failed"], result["skipped"],
                result.get("reason", ""),
            )
        return result

    except Exception as exc:
        logger.error("process_dm_queue failed: %s", exc)
        return {"error": str(exc), "sent": 0, "failed": 0, "skipped": 0}


@celery_app.task(
    name="app.tasks.dm_queue_tasks.overflow_to_next_day",
    bind=True,
    max_retries=0,
)
def overflow_to_next_day(self):
    """每日23:00将当日未发送的pending移到明天"""
    async def _overflow():
        async with async_session_factory() as db:
            try:
                count = await dm_queue_service.overflow_to_next_day(db)
                await db.commit()
                return count
            except Exception as exc:
                await db.rollback()
                raise exc

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        count = loop.run_until_complete(_overflow())
        loop.close()

        logger.info("overflow_to_next_day: moved %d items to tomorrow", count)
        return {"moved": count}

    except Exception as exc:
        logger.error("overflow_to_next_day failed: %s", exc)
        return {"error": str(exc), "moved": 0}
