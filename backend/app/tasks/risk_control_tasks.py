"""风控定时任务 — 每10分钟检查举报拉黑率并触发降量/熔断。"""
import asyncio
import logging

import redis.asyncio as aioredis

from app.tasks.celery_app import celery_app
from app.core.deps import async_session_factory
from app.core.config import settings
from app.services.risk_control_service import (
    risk_control_service,
    LEVEL_NORMAL,
    LEVEL_WARNING_,
    LEVEL_CRITICAL_,
)
from app.services.alert_service import AlertService, LEVEL_WARNING, SOURCE_REPORT

logger = logging.getLogger(__name__)

# 防重复告警Redis key前缀
_ALERT_SENT_KEY = "risk:alert_sent"


@celery_app.task(name="app.tasks.risk_control_tasks.check_report_rate")
def check_report_rate():
    """每10分钟检查举报拉黑率

    流程:
        1. 获取今日统计
        2. 计算率值 = (report+block)/sent
        3. 判断是否触发 warning/critical
        4. warning: 发告警 + 设置降量标记(throttle)
        5. critical: 调用pause_sending熔断暂停
    样本量不足(<RISK_MIN_SAMPLE)时不触发。
    """

    async def _check():
        async with async_session_factory() as db:
            try:
                stats = await risk_control_service.get_today_stats(db)
                level = await risk_control_service.check_risk_level(db)

                # 样本不足
                if stats.sent_count < settings.RISK_MIN_SAMPLE:
                    logger.info(
                        "check_report_rate: sent=%d < min_sample=%d, skip",
                        stats.sent_count, settings.RISK_MIN_SAMPLE,
                    )
                    return {"level": LEVEL_NORMAL, "skipped": True, "sent_count": stats.sent_count}

                rate = (stats.report_count + stats.block_count) / stats.sent_count
                redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                today = stats.date.isoformat()

                try:
                    if level == LEVEL_CRITICAL_:
                        # critical: 熔断暂停
                        dedup_key = f"{_ALERT_SENT_KEY}:{today}:critical"
                        already_sent = await redis.get(dedup_key)
                        if not already_sent:
                            await risk_control_service.pause_sending(
                                db, reason="举报拉黑率超过临界阈值自动熔断"
                            )
                            await db.commit()
                            await redis.set(dedup_key, "1", ex=86400)
                            logger.warning(
                                "check_report_rate: CRITICAL pause triggered, rate=%.4f", rate
                            )

                    elif level == LEVEL_WARNING_:
                        # warning: 降量 + 告警
                        dedup_key = f"{_ALERT_SENT_KEY}:{today}:warning"
                        already_sent = await redis.get(dedup_key)
                        if not already_sent:
                            await risk_control_service.set_throttle(
                                reason="举报拉黑率超过预警阈值自动降量"
                            )
                            await AlertService.send_alert(
                                db,
                                level=LEVEL_WARNING,
                                title="私信风控预警: 举报拉黑率升高",
                                content=(
                                    f"今日统计: 发送{stats.sent_count}条, "
                                    f"举报{stats.report_count}次, 拉黑{stats.block_count}次\n"
                                    f"当前举报拉黑率: {rate:.2%}\n"
                                    f"预警阈值: {settings.REPORT_RATE_WARNING:.2%}\n"
                                    f"已自动降量至{settings.DM_THROTTLE_RATIO:.0%}。"
                                ),
                                source=SOURCE_REPORT,
                            )
                            await db.commit()
                            await redis.set(dedup_key, "1", ex=86400)
                            logger.warning(
                                "check_report_rate: WARNING throttle triggered, rate=%.4f", rate
                            )

                    else:
                        # 正常: 清除降量标记(如果之前设过)
                        if await risk_control_service.is_throttled():
                            await risk_control_service.clear_throttle()
                            logger.info("check_report_rate: rate normal, cleared throttle")
                finally:
                    await redis.close()

                return {
                    "level": level,
                    "rate": round(rate, 4),
                    "sent_count": stats.sent_count,
                    "report_count": stats.report_count,
                    "block_count": stats.block_count,
                }
            except Exception as exc:
                await db.rollback()
                logger.error("check_report_rate failed: %s", exc, exc_info=True)
                return {"error": str(exc)}

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_check())
        loop.close()
        logger.info("Risk check completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Risk check failed: %s", exc)
        return {"error": str(exc)}
