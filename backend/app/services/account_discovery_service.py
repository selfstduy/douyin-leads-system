"""账号自动发现与清洗服务 — 全网搜索高意向账号并淘汰低质账号。"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import get_sentiment_adapter, get_llm_adapter
from app.adapters.base import VideoDTO
from app.adapters.llm_base import IntentLevel
from app.core.config import settings
from app.models.monitor import MonitorAccount

logger = logging.getLogger(__name__)

# 每次AI批量分析的最大评论数
_DISCOVERY_BATCH_SIZE = 50


class AccountDiscoveryService:
    """全网账号发现与自动清洗服务"""

    async def run_daily_discovery(self, db: AsyncSession) -> dict:
        """每日全网发现任务

        流程：
        1. 获取关键词列表
        2. 对每个关键词搜索视频(最大DISCOVERY_MAX_PAGES页)
        3. 对每个视频检查：发布时间≤3天、评论数≥阈值
        4. 抓取视频评论，AI分析统计high数量
        5. high≥DISCOVERY_HIGH_THRESHOLD → 提取所属账号
        6. 账号去重(已在监控池的跳过)
        7. 池子满了→淘汰最久没有high评论的旧账号
        8. 新账号入库，source="discovered"
        """
        keywords = [
            k.strip() for k in settings.DISCOVERY_KEYWORDS.split(",") if k.strip()
        ]
        adapter = get_sentiment_adapter()
        llm_adapter = get_llm_adapter()
        now = datetime.now(timezone.utc)
        video_cutoff = now - timedelta(days=settings.DISCOVERY_VIDEO_DAYS)

        # 汇总每个账号的high评论数
        account_high_map: Dict[str, dict] = {}  # account_uid -> {nickname, high_count}
        total_videos_scanned = 0
        total_keywords_scanned = 0

        for keyword in keywords:
            total_keywords_scanned += 1
            logger.info("Discovery: searching keyword '%s'", keyword)

            for page in range(1, settings.DISCOVERY_MAX_PAGES + 1):
                try:
                    videos = await adapter.search_videos_by_keyword(
                        keyword, page, page_size=20
                    )
                except Exception as exc:
                    logger.error(
                        "Discovery: search failed for keyword '%s' page %d: %s",
                        keyword, page, exc,
                    )
                    break

                if not videos:
                    logger.info(
                        "Discovery: no more results for '%s' at page %d",
                        keyword, page,
                    )
                    break

                for video in videos:
                    total_videos_scanned += 1

                    # 过滤：发布时间≤DISCOVERY_VIDEO_DAYS天内
                    pt = video.publish_time
                    if pt.tzinfo is None:
                        pt = pt.replace(tzinfo=timezone.utc)
                    if pt < video_cutoff:
                        continue

                    # 过滤：评论数≥阈值（热度筛选）
                    if video.comment_count < settings.DISCOVERY_HIGH_THRESHOLD:
                        continue

                    high_count = await self._analyze_video_comments(
                        video, video_cutoff, llm_adapter
                    )

                    if high_count <= 0:
                        continue

                    # 积累到账号维度
                    account_uid = video.account_uid or ""
                    if not account_uid:
                        continue

                    if account_uid not in account_high_map:
                        account_high_map[account_uid] = {
                            "nickname": video.account_nickname or "",
                            "high_count": 0,
                        }
                    account_high_map[account_uid]["high_count"] += high_count

        # 筛选达到阈值的账号
        qualified = {
            uid: info
            for uid, info in account_high_map.items()
            if info["high_count"] >= settings.DISCOVERY_HIGH_THRESHOLD
        }
        logger.info(
            "Discovery: scanned %d keywords, %d videos, %d accounts qualified (threshold=%d)",
            total_keywords_scanned,
            total_videos_scanned,
            len(qualified),
            settings.DISCOVERY_HIGH_THRESHOLD,
        )

        if not qualified:
            return {
                "status": "ok",
                "keywords_scanned": total_keywords_scanned,
                "videos_scanned": total_videos_scanned,
                "accounts_qualified": 0,
                "new_accounts_added": 0,
            }

        # 去重：跳过已在监控池的账号
        existing_result = await db.execute(
            select(MonitorAccount.douyin_uid).where(
                MonitorAccount.status.in_(["active", "paused", "error"])
            )
        )
        existing_uids = {row[0] for row in existing_result.all()}

        new_accounts = {
            uid: info for uid, info in qualified.items() if uid not in existing_uids
        }

        # 也检查已"removed"的账号，如果重新达到阈值则恢复
        removed_result = await db.execute(
            select(MonitorAccount).where(
                MonitorAccount.status == "removed",
                MonitorAccount.douyin_uid.in_(list(new_accounts.keys())),
            )
        )
        restored_count = 0
        for account in removed_result.scalars().all():
            if account.douyin_uid in new_accounts:
                account.status = "active"
                account.last_high_intent_at = now
                account.total_high_count += new_accounts[account.douyin_uid]["high_count"]
                del new_accounts[account.douyin_uid]
                restored_count += 1

        # 池满淘汰策略
        pool_count_result = await db.execute(
            select(func.count()).select_from(MonitorAccount).where(
                MonitorAccount.status.in_(["active", "paused", "error"])
            )
        )
        current_pool_size = pool_count_result.scalar() or 0
        available_slots = settings.ACCOUNT_POOL_MAX - current_pool_size

        if len(new_accounts) > available_slots:
            evict_count = len(new_accounts) - available_slots
            await self._evict_oldest_accounts(db, evict_count)
            logger.info("Discovery: evicted %d oldest accounts to make room", evict_count)

        # 新账号入库
        added_count = 0
        for uid, info in new_accounts.items():
            monitor = MonitorAccount(
                douyin_url=f"https://www.douyin.com/user/{uid}",
                douyin_uid=uid,
                nickname=info["nickname"],
                status="active",
                poll_interval_min=30,
                created_by=None,
                source="discovered",
                last_high_intent_at=now,
                total_high_count=info["high_count"],
            )
            db.add(monitor)
            added_count += 1

        await db.flush()

        return {
            "status": "ok",
            "keywords_scanned": total_keywords_scanned,
            "videos_scanned": total_videos_scanned,
            "accounts_qualified": len(qualified),
            "new_accounts_added": added_count,
            "accounts_restored": restored_count,
        }

    async def _analyze_video_comments(
        self,
        video: VideoDTO,
        since_time: datetime,
        llm_adapter,
    ) -> int:
        """抓取单个视频的评论并AI分析，返回high意向评论数量"""
        adapter = get_sentiment_adapter()

        try:
            comments = await adapter.fetch_comments(video.video_id, since_time)
        except Exception as exc:
            logger.error(
                "Discovery: fetch_comments failed for video %s: %s",
                video.video_id, exc,
            )
            return 0

        if not comments:
            return 0

        # 批量AI分析
        high_count = 0
        for i in range(0, len(comments), _DISCOVERY_BATCH_SIZE):
            batch = comments[i:i + _DISCOVERY_BATCH_SIZE]
            llm_input = [
                {
                    "comment_id": c.comment_id,
                    "content": c.content,
                    "video_title": video.title,
                }
                for c in batch
            ]

            try:
                results = await llm_adapter.batch_analyze_intent(llm_input)
            except Exception as exc:
                logger.error(
                    "Discovery: LLM batch analysis failed for video %s: %s",
                    video.video_id, exc,
                )
                continue

            for r in results:
                if r.intent_level == IntentLevel.HIGH:
                    high_count += 1

        return high_count

    async def _evict_oldest_accounts(self, db: AsyncSession, count: int) -> int:
        """淘汰最久没有high评论的旧账号（软删除，标记status=removed）"""
        result = await db.execute(
            select(MonitorAccount)
            .where(MonitorAccount.status.in_(["active", "paused"]))
            .order_by(
                MonitorAccount.last_high_intent_at.asc().nullsfirst(),
                MonitorAccount.created_at.asc(),
            )
            .limit(count)
        )
        evicted = 0
        for account in result.scalars().all():
            account.status = "removed"
            evicted += 1

        await db.flush()
        return evicted

    async def clean_low_quality_accounts(self, db: AsyncSession) -> dict:
        """清洗低质账号

        查找所有 last_high_intent_at < now()-ACCOUNT_CLEAN_DAYS 或 为null 的账号
        标记 status="removed"（软删除，保留历史数据）
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=settings.ACCOUNT_CLEAN_DAYS)

        result = await db.execute(
            select(MonitorAccount).where(
                MonitorAccount.status.in_(["active", "paused"]),
                or_(
                    MonitorAccount.last_high_intent_at.is_(None),
                    MonitorAccount.last_high_intent_at < cutoff,
                ),
            )
        )
        accounts = list(result.scalars().all())

        for account in accounts:
            account.status = "removed"

        await db.flush()

        logger.info("Cleaning: removed %d low-quality accounts", len(accounts))

        return {
            "status": "ok",
            "removed_count": len(accounts),
            "clean_threshold_days": settings.ACCOUNT_CLEAN_DAYS,
        }

    async def get_discovery_stats(self, db: AsyncSession) -> dict:
        """获取全网发现统计"""
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        # 本周新发现数
        new_discovered_result = await db.execute(
            select(func.count()).select_from(MonitorAccount).where(
                MonitorAccount.source == "discovered",
                MonitorAccount.created_at >= week_ago,
            )
        )
        new_discovered = new_discovered_result.scalar() or 0

        # 累计被清洗数
        removed_result = await db.execute(
            select(func.count()).select_from(MonitorAccount).where(
                MonitorAccount.status == "removed",
            )
        )
        removed_count = removed_result.scalar() or 0

        # 本周被清洗数
        # 由于没有removed_at字段，这里统计总removed数
        # 累计发现总数(仍在池中)
        total_discovered_result = await db.execute(
            select(func.count()).select_from(MonitorAccount).where(
                MonitorAccount.source == "discovered",
                MonitorAccount.status != "removed",
            )
        )
        total_discovered = total_discovered_result.scalar() or 0

        # 池中活跃账号数
        active_count_result = await db.execute(
            select(func.count()).select_from(MonitorAccount).where(
                MonitorAccount.status.in_(["active", "paused", "error"])
            )
        )
        active_count = active_count_result.scalar() or 0

        # 手动导入数
        manual_count_result = await db.execute(
            select(func.count()).select_from(MonitorAccount).where(
                MonitorAccount.source == "manual",
                MonitorAccount.status != "removed",
            )
        )
        manual_count = manual_count_result.scalar() or 0

        return {
            "new_discovered_this_week": new_discovered,
            "removed_total": removed_count,
            "total_discovered_active": total_discovered,
            "total_manual_active": manual_count,
            "total_active_in_pool": active_count,
            "pool_max": settings.ACCOUNT_POOL_MAX,
            "pool_usage_pct": round(
                active_count / settings.ACCOUNT_POOL_MAX * 100, 1
            ) if settings.ACCOUNT_POOL_MAX > 0 else 0,
        }
