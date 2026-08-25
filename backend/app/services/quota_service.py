"""配额管理服务 — 使用Redis INCR原子操作进行实时API调用计数。

Redis keys:
  quota:comment_api:{YYYY-MM-DD}  — 评论接口当日调用计数
  quota:video_api:{YYYY-MM-DD}    — 作品接口当日调用计数
TTL: 25小时，确保跨天自动清零。
"""
import logging
from datetime import datetime, timezone, timedelta

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

# API类型 → 每日上限的映射
_QUOTA_LIMITS: dict[str, int] = {
    "comment_api": settings.DAILY_MAX_COMMENT_REQUESTS,
    "video_api": settings.DAILY_MAX_VIDEO_REQUESTS,
}

# Redis key前缀
_KEY_PREFIX = "quota"


def _build_key(api_type: str, date_str: str | None = None) -> str:
    """构建Redis计数key: quota:comment_api:2026-08-18"""
    if date_str is None:
        # 使用 Asia/Shanghai 时区的当天日期
        now_cst = datetime.now(timezone.utc) + timedelta(hours=8)
        date_str = now_cst.strftime("%Y-%m-%d")
    return f"{_KEY_PREFIX}:{api_type}:{date_str}"


async def _get_redis() -> aioredis.Redis:
    """获取Redis连接（每次调用时创建，避免连接泄漏）"""
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


class QuotaService:

    @staticmethod
    async def increment_api_call(api_type: str, count: int = 1) -> int:
        """记录一次API调用，使用INCR原子操作。返回递增后的值。"""
        if api_type not in _QUOTA_LIMITS:
            logger.warning("Unknown api_type '%s', skipping quota increment", api_type)
            return 0

        key = _build_key(api_type)
        redis = await _get_redis()
        try:
            pipe = redis.pipeline()
            pipe.incrby(key, count)
            pipe.expire(key, settings.QUOTA_REDIS_TTL_SECONDS)
            results = await pipe.execute()
            new_val = results[0]
            logger.debug("Quota incremented: %s = %d", key, new_val)
            return new_val
        except Exception as exc:
            logger.error("Failed to increment quota for %s: %s", api_type, exc)
            return 0
        finally:
            await redis.close()

    @staticmethod
    async def get_today_usage(api_type: str) -> int:
        """获取今日已用次数"""
        if api_type not in _QUOTA_LIMITS:
            return 0
        key = _build_key(api_type)
        redis = await _get_redis()
        try:
            val = await redis.get(key)
            return int(val) if val else 0
        except Exception as exc:
            logger.error("Failed to get quota for %s: %s", api_type, exc)
            return 0
        finally:
            await redis.close()

    @staticmethod
    async def check_quota(api_type: str) -> tuple[bool, float]:
        """检查配额，返回(是否可用, 使用率%)"""
        if api_type not in _QUOTA_LIMITS:
            return True, 0.0

        usage = await QuotaService.get_today_usage(api_type)
        limit = _QUOTA_LIMITS[api_type]
        usage_rate = (usage / limit) * 100 if limit > 0 else 0.0
        available = usage < limit
        return available, round(usage_rate, 2)

    @staticmethod
    async def is_quota_exceeded(api_type: str) -> bool:
        """是否超限"""
        available, _ = await QuotaService.check_quota(api_type)
        return not available

    @staticmethod
    async def get_all_quotas() -> dict:
        """获取所有配额使用情况"""
        result = {}
        for api_type, limit in _QUOTA_LIMITS.items():
            usage = await QuotaService.get_today_usage(api_type)
            usage_rate = (usage / limit) * 100 if limit > 0 else 0.0
            available = usage < limit
            result[api_type] = {
                "usage": usage,
                "limit": limit,
                "usage_rate": round(usage_rate, 2),
                "available": available,
                "exceeded": not available,
            }
        return result

    @staticmethod
    async def get_quota_info(api_type: str) -> dict:
        """获取单个配额详情"""
        if api_type not in _QUOTA_LIMITS:
            return {"error": f"Unknown api_type: {api_type}"}
        usage = await QuotaService.get_today_usage(api_type)
        limit = _QUOTA_LIMITS[api_type]
        usage_rate = (usage / limit) * 100 if limit > 0 else 0.0
        available = usage < limit
        return {
            "api_type": api_type,
            "usage": usage,
            "limit": limit,
            "usage_rate": round(usage_rate, 2),
            "available": available,
            "exceeded": not available,
        }
