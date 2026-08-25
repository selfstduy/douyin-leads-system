"""配额检查告警定时任务"""
import asyncio
import logging

from app.tasks.celery_app import celery_app
from app.core.deps import async_session_factory
from app.services.quota_service import QuotaService
from app.services.alert_service import AlertService, LEVEL_WARNING, LEVEL_CRITICAL, SOURCE_QUOTA
from app.core.config import settings

logger = logging.getLogger(__name__)

# 记录已发送告警的Redis key前缀(防重复)
_ALERT_SENT_KEY = "quota:alert_sent"


@celery_app.task(name="app.tasks.quota_tasks.check_quota_alerts")
def check_quota_alerts():
    """
    每5分钟检查配额使用率并触发告警。
    - 使用率 >= 90% → warning
    - 使用率 >= 100% → critical + 自动暂停采集
    使用Redis SET标记防重复(同一告警1小时内不重复发送)。
    """
    async def _check():
        import redis.asyncio as aioredis

        quotas = await QuotaService.get_all_quotas()
        alerts_to_send = []

        redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            for api_type, info in quotas.items():
                usage_rate = info["usage_rate"]
                exceeded = info["exceeded"]

                if exceeded or usage_rate >= settings.QUOTA_CRITICAL_THRESHOLD * 100:
                    # critical: 100% 超限
                    dedup_key = f"{_ALERT_SENT_KEY}:{api_type}:critical"
                    already_sent = await redis.get(dedup_key)
                    if not already_sent:
                        alerts_to_send.append({
                            "level": LEVEL_CRITICAL,
                            "title": f"API配额超限: {api_type}",
                            "content": (
                                f"API类型: {api_type}\n"
                                f"已用: {info['usage']}/{info['limit']} ({usage_rate}%)\n"
                                f"已达到每日上限, 采集任务已自动暂停。"
                            ),
                            "source": SOURCE_QUOTA,
                            "dedup_key": dedup_key,
                        })

                elif usage_rate >= settings.QUOTA_WARNING_THRESHOLD * 100:
                    # warning: 90% 告警
                    dedup_key = f"{_ALERT_SENT_KEY}:{api_type}:warning"
                    already_sent = await redis.get(dedup_key)
                    if not already_sent:
                        alerts_to_send.append({
                            "level": LEVEL_WARNING,
                            "title": f"API配额告警: {api_type}",
                            "content": (
                                f"API类型: {api_type}\n"
                                f"已用: {info['usage']}/{info['limit']} ({usage_rate}%)\n"
                                f"已达到90%阈值, 请关注用量。"
                            ),
                            "source": SOURCE_QUOTA,
                            "dedup_key": dedup_key,
                        })
        finally:
            await redis.close()

        # 发送告警
        if alerts_to_send:
            async with async_session_factory() as db:
                for alert_info in alerts_to_send:
                    try:
                        await AlertService.send_alert(
                            db,
                            level=alert_info["level"],
                            title=alert_info["title"],
                            content=alert_info["content"],
                            source=alert_info["source"],
                        )
                        await db.commit()

                        # 设置防重复标记 (1小时)
                        redis2 = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                        try:
                            await redis2.set(alert_info["dedup_key"], "1", ex=3600)
                        finally:
                            await redis2.close()

                        logger.info("Quota alert sent: %s - %s", alert_info["level"], alert_info["title"])
                    except Exception as exc:
                        await db.rollback()
                        logger.error("Failed to send quota alert: %s", exc)

        return {"alerts_sent": len(alerts_to_send), "quotas": quotas}

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_check())
        loop.close()
        logger.info("Quota check completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Quota check failed: %s", exc)
        return {"error": str(exc)}


@celery_app.task(name="app.tasks.quota_tasks.reset_daily_quotas")
def reset_daily_quotas():
    """
    每日零点重置配额标记(可选)。
    Redis计数key设置了25小时TTL, 会自动过期。
    此任务用于清理防重复告警的Redis标记, 确保新一天能正常告警。
    """
    async def _reset():
        import redis.asyncio as aioredis

        redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            # 扫描并删除所有防重复标记
            keys = []
            async for key in redis.scan_iter(match=f"{_ALERT_SENT_KEY}:*", count=100):
                keys.append(key)
            if keys:
                await redis.delete(*keys)
            logger.info("Cleared %d quota alert dedup keys", len(keys))
            return {"cleared_keys": len(keys)}
        finally:
            await redis.close()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_reset())
        loop.close()
        logger.info("Daily quota reset completed: %s", result)
        return result
    except Exception as exc:
        logger.error("Daily quota reset failed: %s", exc)
        return {"error": str(exc)}
