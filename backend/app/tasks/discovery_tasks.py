"""账号发现与清洗Celery定时任务。"""
import asyncio
import logging

from app.core.deps import async_session_factory
from app.services.account_discovery_service import AccountDiscoveryService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.discovery_tasks.daily_account_discovery",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
)
def daily_account_discovery(self):
    """每日全网发现任务

    由beat每日凌晨2:00触发。
    高成本操作，包含大量API调用，不阻塞其他任务。
    """
    async def _run():
        async with async_session_factory() as db:
            try:
                service = AccountDiscoveryService()
                result = await service.run_daily_discovery(db)
                await db.commit()
                return result
            except Exception as exc:
                await db.rollback()
                raise exc

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run())
        loop.close()
        logger.info("Daily account discovery completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Daily account discovery failed: %s", exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for daily_account_discovery")
            return {"status": "error", "error": str(exc)}


@celery_app.task(
    name="app.tasks.discovery_tasks.weekly_account_cleaning",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def weekly_account_cleaning(self):
    """每周账号清洗任务

    由beat每周一凌晨3:00触发。
    清洗超过ACCOUNT_CLEAN_DAYS天无high评论的账号（软删除）。
    """
    async def _run():
        async with async_session_factory() as db:
            try:
                service = AccountDiscoveryService()
                result = await service.clean_low_quality_accounts(db)
                await db.commit()
                return result
            except Exception as exc:
                await db.rollback()
                raise exc

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_run())
        loop.close()
        logger.info("Weekly account cleaning completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Weekly account cleaning failed: %s", exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded for weekly_account_cleaning")
            return {"status": "error", "error": str(exc)}
