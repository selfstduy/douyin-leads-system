"""私信发送队列服务 — 限流调度、去重、账号轮换、溢出处理。"""
import asyncio
import logging
import random
from datetime import datetime, timezone, date, timedelta
from typing import Optional, List

import redis.asyncio as aioredis
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dm_queue import DmQueue
from app.models.lead import Lead
from app.models.monitor import DouyinChatAccount
from app.services.openkf_service import openkf_service
from app.services.risk_control_service import risk_control_service, EVENT_SENT

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


def _daily_key(d: date) -> str:
    return f"dm:daily:{d.isoformat()}"


def _account_key(account_id: int, d: date) -> str:
    return f"dm:account:{account_id}:{d.isoformat()}"


def _dedup_key(user_uid: str) -> str:
    return f"dm:dedup:{user_uid}"


_PAUSED_KEY = "dm:queue:paused"


class DmQueueService:
    """私信发送队列服务"""

    # ── 入队 ───────────────────────────────────────────────────────────────────

    async def enqueue(
        self,
        db: AsyncSession,
        lead_id: int,
        user_uid: str,
        comment: str,
        comment_time: Optional[datetime] = None,
    ) -> Optional[DmQueue]:
        """high意向线索入队

        - 7天去重：同一user_uid 7天内只入队一次
        - 设置priority(基于comment_time，越新优先级越高)
        - 检查当日是否溢出→溢出则scheduled_date=明天
        """
        # 7天去重检查
        if await self.check_user_dedup(user_uid):
            logger.info(
                "enqueue: user_uid=%s already sent within %d days, skipping",
                user_uid, settings.DM_USER_DEDUP_DAYS,
            )
            return None

        # 检查是否已有同一lead的pending记录（避免重复入队）
        existing = await db.execute(
            select(DmQueue).where(
                and_(
                    DmQueue.lead_id == lead_id,
                    DmQueue.status.in_(["pending", "overflow"]),
                )
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            logger.info("enqueue: lead_id=%d already in queue, skipping", lead_id)
            return None

        # 计算优先级：评论时间越新优先级越高
        # 用Unix timestamp作为priority base（越新数值越大）
        priority = 0
        if comment_time:
            priority = int(comment_time.timestamp())
        else:
            priority = int(datetime.now(timezone.utc).timestamp())

        # 检查今日是否已溢出安全线
        today = _today()
        daily_sent = await self.get_daily_sent_count()
        if daily_sent >= settings.DM_DAILY_SAFE_LIMIT:
            # 溢出 → 排到明天
            scheduled_date = today + timedelta(days=1)
            status = "overflow"
            logger.info(
                "enqueue: daily_sent=%d >= safe_limit=%d, scheduling to %s",
                daily_sent, settings.DM_DAILY_SAFE_LIMIT, scheduled_date,
            )
        else:
            scheduled_date = today
            status = "pending"

        item = DmQueue(
            lead_id=lead_id,
            user_uid=user_uid,
            original_comment=comment,
            priority=priority,
            status=status,
            scheduled_date=scheduled_date,
        )
        db.add(item)
        await db.flush()

        logger.info(
            "enqueue: lead_id=%d user_uid=%s priority=%d scheduled=%s status=%s",
            lead_id, user_uid, priority, scheduled_date, status,
        )
        return item

    # ── 处理队列 ──────────────────────────────────────────────────────────────

    async def process_queue(self, db: AsyncSession) -> dict:
        """处理发送队列(Celery定时调用)

        1. 检查是否暂停
        2. 检查当前时间是否在发送窗口(8:00-23:00)
        3. 获取今日待发送(status=pending, scheduled_date=today)
        4. 按priority排序(最新评论优先)
        5. 检查全局日上限
        6. 选择发送账号(轮换，单账号≤100/日)
        7. 随机延迟发送(打散，不扎堆)
        8. 调用openkf推送
        9. 更新状态
        """
        result = {"sent": 0, "failed": 0, "skipped": 0, "reason": ""}

        # 1. 检查暂停
        if await self.is_paused():
            result["reason"] = "队列已暂停"
            return result

        # 1b. 检查风控熔断
        if await risk_control_service.is_sending_paused():
            result["reason"] = "风控熔断: 举报拉黑率超阈值，发送已暂停"
            return result

        # 2. 检查发送窗口
        now = datetime.now()
        if not (settings.DM_SEND_WINDOW_START <= now.hour < settings.DM_SEND_WINDOW_END):
            result["reason"] = f"当前不在发送窗口({settings.DM_SEND_WINDOW_START}:00-{settings.DM_SEND_WINDOW_END}:00)"
            return result

        # 5. 检查全局日上限(使用风控有效日限，含降量)
        daily_sent = await self.get_daily_sent_count()
        effective_limit = await risk_control_service.get_effective_daily_limit(db)
        if daily_sent >= effective_limit:
            result["reason"] = f"今日已发送{daily_sent}条，达到有效上限{effective_limit}"
            return result

        remaining_global = effective_limit - daily_sent

        # 3+4. 获取今日待发送，按priority降序
        today = _today()
        batch_limit = min(settings.DM_BATCH_SIZE, remaining_global)
        stmt = (
            select(DmQueue)
            .where(
                and_(
                    DmQueue.status == "pending",
                    DmQueue.scheduled_date == today,
                )
            )
            .order_by(DmQueue.priority.desc())
            .limit(batch_limit)
        )
        items_result = await db.execute(stmt)
        items = list(items_result.scalars().all())

        if not items:
            result["reason"] = "队列中没有待发送项"
            return result

        # 6. 获取可用发送账号，按今日已发送数升序(少的优先)
        accounts = await self._get_available_accounts(db)
        if not accounts:
            result["reason"] = "没有可用的发送账号"
            return result

        # 构建账号轮换池：今日已发送数 < 上限的账号
        r = await _get_redis()
        available_accounts: List[DouyinChatAccount] = []
        for acc in accounts:
            count = await self.get_account_daily_count(acc.id)
            if count < settings.DM_ACCOUNT_DAILY_LIMIT:
                available_accounts.append(acc)

        if not available_accounts:
            result["reason"] = "所有账号今日发送已达上限"
            return result

        # 按已发送数升序排序（少的优先）
        acc_counts: list[tuple[DouyinChatAccount, int]] = []
        for acc in available_accounts:
            cnt = await self.get_account_daily_count(acc.id)
            acc_counts.append((acc, cnt))
        acc_counts.sort(key=lambda x: x[1])

        # 7+8+9. 逐条发送
        account_idx = 0
        for item in items:
            # 检查全局上限(使用风控有效日限)
            if daily_sent >= effective_limit:
                result["reason"] = "达到有效上限，停止发送"
                break

            # 风控黑名单检查
            if await risk_control_service.is_blacklisted(item.user_uid):
                item.status = "skipped"
                item.error_message = "用户在黑名单中"
                result["skipped"] += 1
                continue

            # 选择账号（轮换）
            selected_account = None
            for offset in range(len(acc_counts)):
                idx = (account_idx + offset) % len(acc_counts)
                acc, cnt = acc_counts[idx]
                if cnt < settings.DM_ACCOUNT_DAILY_LIMIT:
                    selected_account = acc
                    acc_counts[idx] = (acc, cnt + 1)
                    account_idx = idx + 1
                    break

            if not selected_account:
                # 所有账号都满了
                result["reason"] = "所有账号今日发送已达上限"
                break

            # 去重检查（Redis原子操作）
            dedup_r = await r.set(
                _dedup_key(item.user_uid), "1", nx=True,
                ex=settings.DM_USER_DEDUP_DAYS * 86400,
            )
            if dedup_r is None:
                # 7天内已发送过，跳过
                item.status = "skipped"
                item.error_message = "7天内已发送过私信"
                result["skipped"] += 1
                continue

            # 随机延迟发送(打散)
            delay = random.uniform(
                settings.DM_MIN_INTERVAL_SEC, settings.DM_MAX_INTERVAL_SEC
            )
            await asyncio.sleep(delay)

            # 调用OpenKF推送
            lead = await self._get_lead(db, item.lead_id)
            if not lead:
                item.status = "failed"
                item.error_message = "线索不存在"
                result["failed"] += 1
                continue

            # 构造chat_id
            chat_id = lead.chat_id or f"lead-{lead.id}"
            push_ok = False
            ext_msg_id = ""
            if settings.OPENKF_CALLBACK_URL:
                push_ok, ext_msg_id = await openkf_service.push_message_to_chatdoing(
                    chat_id=chat_id,
                    sender_id=item.user_uid,
                    content=item.original_comment,
                    msg_type=0,
                    chat_status=2,  # AI托管
                )
            else:
                logger.warning(
                    "process_queue: OPENKF_CALLBACK_URL not configured, "
                    "marking as failed"
                )

            if push_ok:
                # 更新队列项状态
                item.status = "sent"
                item.sent_at = datetime.now(timezone.utc)
                item.send_account_id = selected_account.id
                daily_sent += 1
                result["sent"] += 1

                # 更新Lead
                lead.chat_id = chat_id
                lead.chat_status = 2  # AI托管
                if lead.status == "new":
                    lead.status = "contacted"

                # 更新Redis计数
                await r.incr(_daily_key(today))
                await r.expire(_daily_key(today), 25 * 3600)
                await r.incr(_account_key(selected_account.id, today))
                await r.expire(_account_key(selected_account.id, today), 25 * 3600)

                # 记录风控sent事件(用于举报拉黑率计算)
                await risk_control_service.record_event(db, EVENT_SENT)
            else:
                item.status = "failed"
                item.error_message = "OpenKF推送失败"
                result["failed"] += 1
                # 回滚去重标记（允许下次重试）
                await r.delete(_dedup_key(item.user_uid))

        await db.flush()
        logger.info(
            "process_queue: sent=%d failed=%d skipped=%d reason=%s",
            result["sent"], result["failed"], result["skipped"], result["reason"],
        )
        return result

    # ── 溢出处理 ──────────────────────────────────────────────────────────────

    async def overflow_to_next_day(self, db: AsyncSession) -> int:
        """每日23:00将当日未发送的pending移到明天"""
        today = _today()
        tomorrow = today + timedelta(days=1)
        result = await db.execute(
            update(DmQueue)
            .where(
                and_(
                    DmQueue.status == "pending",
                    DmQueue.scheduled_date == today,
                )
            )
            .values(status="overflow", scheduled_date=tomorrow)
        )
        count = result.rowcount
        await db.flush()
        logger.info("overflow_to_next_day: moved %d items to %s", count, tomorrow)
        return count

    # ── 统计查询 ──────────────────────────────────────────────────────────────

    async def get_daily_sent_count(self) -> int:
        """今日已发送数（Redis全局计数）"""
        r = await _get_redis()
        count = await r.get(_daily_key(_today()))
        return int(count) if count else 0

    async def get_account_daily_count(self, account_id: int) -> int:
        """某账号今日已发送数（Redis计数）"""
        r = await _get_redis()
        count = await r.get(_account_key(account_id, _today()))
        return int(count) if count else 0

    async def check_user_dedup(self, user_uid: str) -> bool:
        """检查用户7天内是否已发送过"""
        r = await _get_redis()
        return bool(await r.exists(_dedup_key(user_uid)))

    async def get_queue_stats(self, db: AsyncSession) -> dict:
        """队列统计：待发送、今日已发、溢出待明日"""
        today = _today()
        tomorrow = today + timedelta(days=1)

        # 待发送（今日pending）
        pending_result = await db.execute(
            select(func.count(DmQueue.id)).where(
                and_(
                    DmQueue.status == "pending",
                    DmQueue.scheduled_date == today,
                )
            )
        )
        pending = pending_result.scalar() or 0

        # 今日已发（优先用Redis，降级用DB）
        daily_sent = await self.get_daily_sent_count()

        # 溢出待明日
        overflow_result = await db.execute(
            select(func.count(DmQueue.id)).where(
                and_(
                    DmQueue.status.in_(["overflow", "pending"]),
                    DmQueue.scheduled_date == tomorrow,
                )
            )
        )
        overflow = overflow_result.scalar() or 0

        # 总计sent
        sent_result = await db.execute(
            select(func.count(DmQueue.id)).where(DmQueue.status == "sent")
        )
        total_sent = sent_result.scalar() or 0

        # 失败
        failed_result = await db.execute(
            select(func.count(DmQueue.id)).where(DmQueue.status == "failed")
        )
        total_failed = failed_result.scalar() or 0

        return {
            "pending": pending,
            "daily_sent": daily_sent,
            "daily_limit": settings.DM_DAILY_SAFE_LIMIT,
            "global_limit": settings.DM_DAILY_GLOBAL_LIMIT,
            "overflow_tomorrow": overflow,
            "total_sent": total_sent,
            "total_failed": total_failed,
            "is_paused": await self.is_paused(),
        }

    async def get_queue_list(
        self,
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> dict:
        """队列列表(分页，状态筛选)"""
        conditions = []
        if status:
            conditions.append(DmQueue.status == status)

        # 总数
        count_stmt = select(func.count(DmQueue.id))
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total = (await db.execute(count_stmt)).scalar() or 0

        # 分页查询
        stmt = select(DmQueue).order_by(DmQueue.id.desc())
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        items = result.scalars().all()

        return {
            "items": [
                {
                    "id": item.id,
                    "lead_id": item.lead_id,
                    "user_uid": item.user_uid,
                    "original_comment": item.original_comment[:200],
                    "priority": item.priority,
                    "status": item.status,
                    "scheduled_date": item.scheduled_date.isoformat() if item.scheduled_date else None,
                    "sent_at": item.sent_at.isoformat() if item.sent_at else None,
                    "send_account_id": item.send_account_id,
                    "error_message": item.error_message,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ── 暂停/恢复 ──────────────────────────────────────────────────────────────

    async def pause(self) -> bool:
        """暂停队列"""
        r = await _get_redis()
        await r.set(_PAUSED_KEY, "1")
        logger.info("DM queue paused")
        return True

    async def resume(self) -> bool:
        """恢复队列"""
        r = await _get_redis()
        await r.delete(_PAUSED_KEY)
        logger.info("DM queue resumed")
        return True

    async def is_paused(self) -> bool:
        """检查队列是否已暂停"""
        r = await _get_redis()
        return bool(await r.exists(_PAUSED_KEY))

    # ── 内部辅助方法 ──────────────────────────────────────────────────────────

    async def _get_available_accounts(self, db: AsyncSession) -> List[DouyinChatAccount]:
        """获取所有在线的发送账号"""
        result = await db.execute(
            select(DouyinChatAccount).where(
                DouyinChatAccount.login_status == "online"
            ).order_by(DouyinChatAccount.id)
        )
        return list(result.scalars().all())

    async def _get_lead(self, db: AsyncSession, lead_id: int) -> Optional[Lead]:
        """获取线索"""
        result = await db.execute(select(Lead).where(Lead.id == lead_id))
        return result.scalar_one_or_none()


# ── 模块级单例 ────────────────────────────────────────────────────────────────

dm_queue_service = DmQueueService()
