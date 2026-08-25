"""风控服务 — 举报拉黑率监控、降量熔断、用户黑名单管理。

业务规则:
    - 举报拉黑率 = (report_count + block_count) / sent_count
    - 率 > 1.0% → critical: 熔断暂停发送
    - 率 > 0.7% → warning: 降量至50%
    - sent_count < 50 时不触发(样本太少)
    - 黑名单用户不再发送私信
"""
import logging
from datetime import date, datetime, timezone
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dm_stats import DmDailyStats, UserBlacklist
from app.services.alert_service import (
    AlertService,
    LEVEL_WARNING,
    LEVEL_CRITICAL,
    SOURCE_REPORT,
)

logger = logging.getLogger(__name__)

# ── Redis helpers ─────────────────────────────────────────────────────────────

_redis: Optional[aioredis.Redis] = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _today() -> date:
    return date.today()


def _paused_key(d: date) -> str:
    return f"risk:paused:{d.isoformat()}"


def _throttle_key(d: date) -> str:
    return f"risk:throttle:{d.isoformat()}"


# Redis Set key for blacklist cache
_BLACKLIST_SET_KEY = "blacklist:users"


# ── 事件类型常量 ─────────────────────────────────────────────────────────────

EVENT_SENT = "sent"
EVENT_READ = "read"
EVENT_REPLY = "reply"
EVENT_REPORT = "report"
EVENT_BLOCK = "block"
EVENT_WECHAT_ADDED = "wechat_added"

_EVENT_COLUMN_MAP = {
    EVENT_SENT: "sent_count",
    EVENT_READ: "read_count",
    EVENT_REPLY: "reply_count",
    EVENT_REPORT: "report_count",
    EVENT_BLOCK: "block_count",
    EVENT_WECHAT_ADDED: "wechat_added_count",
}

# 风控等级
LEVEL_NORMAL = "normal"
LEVEL_WARNING_ = "warning"
LEVEL_CRITICAL_ = "critical"


class RiskControlService:
    """风控服务 — 举报拉黑率监控与熔断"""

    # ── 事件记录 ─────────────────────────────────────────────────────────────

    async def record_event(
        self,
        db: AsyncSession,
        event_type: str,
        count: int = 1,
    ) -> Optional[DmDailyStats]:
        """记录事件: sent/read/reply/report/block/wechat_added

        使用 upsert 更新当日 dm_daily_stats 记录。
        """
        column = _EVENT_COLUMN_MAP.get(event_type)
        if column is None:
            logger.warning("record_event: unknown event_type=%s", event_type)
            return None

        today = _today()

        # 先尝试查询当日记录
        result = await db.execute(
            select(DmDailyStats).where(DmDailyStats.date == today).limit(1)
        )
        stats = result.scalar_one_or_none()

        if stats is None:
            # 插入新记录
            stats = DmDailyStats(date=today)
            setattr(stats, column, count)
            db.add(stats)
        else:
            # 更新已有记录
            setattr(stats, column, getattr(stats, column) + count)

        await db.flush()
        logger.info(
            "record_event: type=%s count=%d date=%s %s=%d",
            event_type, count, today, column, getattr(stats, column),
        )
        return stats

    # ── 统计查询 ─────────────────────────────────────────────────────────────

    async def get_today_stats(self, db: AsyncSession) -> DmDailyStats:
        """获取今日统计(不存在则返回空壳对象)"""
        today = _today()
        result = await db.execute(
            select(DmDailyStats).where(DmDailyStats.date == today).limit(1)
        )
        stats = result.scalar_one_or_none()
        if stats is None:
            stats = DmDailyStats(date=today)
        return stats

    async def get_report_rate(self, db: AsyncSession) -> float:
        """计算当前举报拉黑率 = (report+block)/sent"""
        stats = await self.get_today_stats(db)
        if stats.sent_count == 0:
            return 0.0
        return (stats.report_count + stats.block_count) / stats.sent_count

    async def check_risk_level(self, db: AsyncSession) -> str:
        """检查风控等级: normal/warning/critical

        - sent_count < RISK_MIN_SAMPLE → normal(样本不足)
        - rate > REPORT_RATE_CRITICAL(1.0%) → critical
        - rate > REPORT_RATE_WARNING(0.7%) → warning
        - else → normal
        """
        stats = await self.get_today_stats(db)

        # 样本不足时不触发
        if stats.sent_count < settings.RISK_MIN_SAMPLE:
            return LEVEL_NORMAL

        rate = (stats.report_count + stats.block_count) / stats.sent_count

        if rate > settings.REPORT_RATE_CRITICAL:
            return LEVEL_CRITICAL_
        if rate > settings.REPORT_RATE_WARNING:
            return LEVEL_WARNING_
        return LEVEL_NORMAL

    async def get_effective_daily_limit(self, db: AsyncSession) -> int:
        """获取当前有效日限(降量后的)

        - critical → 0(暂停)
        - warning → 原限 * DM_THROTTLE_RATIO(默认50%)
        - normal → 原限(DM_DAILY_SAFE_LIMIT)
        """
        level = await self.check_risk_level(db)

        if level == LEVEL_CRITICAL_:
            return 0
        if level == LEVEL_WARNING_:
            return int(settings.DM_DAILY_SAFE_LIMIT * settings.DM_THROTTLE_RATIO)
        return settings.DM_DAILY_SAFE_LIMIT

    # ── 熔断暂停/恢复 ─────────────────────────────────────────────────────────

    async def is_sending_paused(self) -> bool:
        """是否已熔断暂停(检查Redis标记: risk:paused:{date})"""
        r = await _get_redis()
        return bool(await r.exists(_paused_key(_today())))

    async def pause_sending(self, db: AsyncSession, reason: str):
        """熔断暂停发送

        - 设置Redis标记 risk:paused:{date}(当日有效)
        - 发送critical告警
        """
        r = await _get_redis()
        today = _today()
        # 当日剩余秒数 + 1小时缓冲
        end_of_day = datetime.combine(today, datetime.max.time())
        ttl = int((end_of_day - datetime.now()).total_seconds()) + 3600
        await r.set(_paused_key(today), reason, ex=max(ttl, 3600))

        # 发送critical告警
        stats = await self.get_today_stats(db)
        rate = (stats.report_count + stats.block_count) / max(stats.sent_count, 1)
        await AlertService.send_alert(
            db,
            level=LEVEL_CRITICAL,
            title="私信发送已熔断暂停",
            content=(
                f"触发原因: {reason}\n"
                f"今日统计: 发送{stats.sent_count}条, 举报{stats.report_count}次, "
                f"拉黑{stats.block_count}次\n"
                f"当前举报拉黑率: {rate:.2%}\n"
                f"熔断阈值: {settings.REPORT_RATE_CRITICAL:.2%}\n"
                f"需管理员确认后手动恢复。"
            ),
            source=SOURCE_REPORT,
        )
        await db.flush()
        logger.warning("pause_sending: reason=%s rate=%.4f", reason, rate)

    async def resume_sending(self, db: AsyncSession) -> bool:
        """人工确认恢复(需admin操作)

        - 清除Redis暂停标记
        - 清除降量标记
        - 发送info告警通知恢复
        """
        r = await _get_redis()
        today = _today()
        await r.delete(_paused_key(today))
        await r.delete(_throttle_key(today))

        await AlertService.send_alert(
            db,
            level=LEVEL_WARNING,
            title="私信发送已恢复",
            content="管理员手动恢复发送，熔断状态已解除。",
            source=SOURCE_REPORT,
        )
        await db.flush()
        logger.info("resume_sending: pause cleared for %s", today)
        return True

    # ── 降量标记 ─────────────────────────────────────────────────────────────

    async def set_throttle(self, reason: str):
        """设置降量标记(供定时任务调用)"""
        r = await _get_redis()
        today = _today()
        end_of_day = datetime.combine(today, datetime.max.time())
        ttl = int((end_of_day - datetime.now()).total_seconds()) + 3600
        await r.set(_throttle_key(today), reason, ex=max(ttl, 3600))

    async def clear_throttle(self):
        """清除降量标记"""
        r = await _get_redis()
        await r.delete(_throttle_key(_today()))

    async def is_throttled(self) -> bool:
        """是否处于降量状态"""
        r = await _get_redis()
        return bool(await r.exists(_throttle_key(_today())))

    # ── 黑名单管理 ───────────────────────────────────────────────────────────

    async def add_to_blacklist(
        self, db: AsyncSession, user_uid: str, reason: str = "manual"
    ) -> UserBlacklist:
        """加入黑名单(数据库 + Redis Set缓存)"""
        # 幂等: 检查是否已存在
        existing = await db.execute(
            select(UserBlacklist).where(UserBlacklist.user_uid == user_uid).limit(1)
        )
        entry = existing.scalar_one_or_none()
        if entry:
            logger.info("add_to_blacklist: user_uid=%s already blacklisted", user_uid)
            return entry

        entry = UserBlacklist(user_uid=user_uid, reason=reason)
        db.add(entry)
        await db.flush()

        # 同步到Redis Set缓存
        r = await _get_redis()
        await r.sadd(_BLACKLIST_SET_KEY, user_uid)

        logger.info("add_to_blacklist: user_uid=%s reason=%s", user_uid, reason)
        return entry

    async def is_blacklisted(self, user_uid: str) -> bool:
        """检查是否在黑名单(优先Redis Set缓存)"""
        r = await _get_redis()
        return bool(await r.sismember(_BLACKLIST_SET_KEY, user_uid))

    async def get_blacklist(
        self, db: AsyncSession, page: int = 1, page_size: int = 20
    ) -> dict:
        """获取黑名单列表(分页)"""
        # 总数
        count_stmt = select(func.count(UserBlacklist.id))
        total = (await db.execute(count_stmt)).scalar() or 0

        # 分页查询
        stmt = (
            select(UserBlacklist)
            .order_by(UserBlacklist.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        items = result.scalars().all()

        return {
            "items": [
                {
                    "id": item.id,
                    "user_uid": item.user_uid,
                    "reason": item.reason,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def remove_from_blacklist(self, db: AsyncSession, user_uid: str) -> bool:
        """移出黑名单(数据库 + Redis缓存)"""
        result = await db.execute(
            delete(UserBlacklist).where(UserBlacklist.user_uid == user_uid)
        )
        await db.flush()

        # 从Redis缓存移除
        r = await _get_redis()
        await r.srem(_BLACKLIST_SET_KEY, user_uid)

        removed = result.rowcount > 0
        logger.info("remove_from_blacklist: user_uid=%s removed=%s", user_uid, removed)
        return removed

    async def _sync_blacklist_to_redis(self, db: AsyncSession):
        """将数据库黑名单全量同步到Redis(供初始化或修复使用)"""
        result = await db.execute(select(UserBlacklist.user_uid))
        uids = [row[0] for row in result.all()]

        r = await _get_redis()
        # 先清空旧缓存再重建
        await r.delete(_BLACKLIST_SET_KEY)
        if uids:
            await r.sadd(_BLACKLIST_SET_KEY, *uids)

        logger.info("_sync_blacklist_to_redis: synced %d entries", len(uids))

    # ── 综合状态 ─────────────────────────────────────────────────────────────

    async def get_status(self, db: AsyncSession) -> dict:
        """获取当前风控综合状态(供API调用)"""
        stats = await self.get_today_stats(db)
        rate = (stats.report_count + stats.block_count) / stats.sent_count if stats.sent_count else 0.0
        level = await self.check_risk_level(db)
        is_paused = await self.is_sending_paused()
        is_throttled = await self.is_throttled()
        effective_limit = await self.get_effective_daily_limit(db)

        return {
            "level": level,
            "is_paused": is_paused,
            "is_throttled": is_throttled,
            "report_rate": round(rate, 4),
            "report_rate_pct": f"{rate:.2%}",
            "sent_count": stats.sent_count,
            "read_count": stats.read_count,
            "reply_count": stats.reply_count,
            "report_count": stats.report_count,
            "block_count": stats.block_count,
            "wechat_added_count": stats.wechat_added_count,
            "effective_daily_limit": effective_limit,
            "daily_limit": settings.DM_DAILY_SAFE_LIMIT,
            "warning_threshold": settings.REPORT_RATE_WARNING,
            "critical_threshold": settings.REPORT_RATE_CRITICAL,
            "min_sample": settings.RISK_MIN_SAMPLE,
        }


# ── 模块级单例 ────────────────────────────────────────────────────────────────

risk_control_service = RiskControlService()
