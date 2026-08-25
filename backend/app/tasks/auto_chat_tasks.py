"""AI自动对话Celery任务 — 异步触发AI对话，不阻塞线索创建流程。"""
import asyncio
import logging

from app.core.deps import async_session_factory
from app.services.auto_chat_service import auto_chat_service
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.auto_chat_tasks.trigger_ai_conversation",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
)
def trigger_ai_conversation(self, lead_id: int):
    """
    异步触发AI对话，不阻塞线索创建流程。

    由 intent_service 在创建高/中意向线索后调用：
        trigger_ai_conversation.delay(lead_id)
    """
    async def _initiate():
        async with async_session_factory() as db:
            try:
                result = await auto_chat_service.initiate_ai_conversation(lead_id, db)
                await db.commit()
                return result
            except Exception as exc:
                await db.rollback()
                raise exc

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_initiate())
        loop.close()

        if result:
            logger.info(
                "trigger_ai_conversation: lead_id=%d chat_id=%s push_ok=%s",
                lead_id,
                result.get("chat_id", ""),
                result.get("push_ok", False),
            )
        return result

    except Exception as exc:
        logger.error(
            "trigger_ai_conversation failed for lead_id=%d: %s", lead_id, exc,
        )
        # 重试（最多 max_retries 次）
        raise self.retry(exc=exc)
