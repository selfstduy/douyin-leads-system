import logging
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import List

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import get_sentiment_adapter
from app.adapters.base import CommentDTO
from app.core.config import settings
from app.models.comment import Comment
from app.models.topic_monitor import TopicMonitor
from app.models.monitor import MonitorAccount
from app.models.video import Video
from app.services.quota_service import QuotaService
from app.services.api_log_service import log_api_call

logger = logging.getLogger(__name__)


# ── 无效评论过滤 ──────────────────────────────────────────────────────────────

# Emoji Unicode 范围正则
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001f926-\U0001f937"
    "\U00010000-\U0010ffff"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]+",
    flags=re.UNICODE,
)


def _is_only_emoji(text: str) -> bool:
    """判断文本是否只包含emoji"""
    stripped = _EMOJI_RE.sub("", text).strip()
    return len(stripped) == 0


def _is_only_punctuation(text: str) -> bool:
    """判断文本是否只包含标点符号"""
    for ch in text:
        cat = unicodedata.category(ch)
        if cat not in ("Po", "Pd", "Ps", "Pe", "Pc", "Pi", "Pf"):
            return False
    return True


def _is_valid_comment(content: str) -> bool:
    """判断评论是否有效（非垃圾）"""
    stripped = content.strip()
    if len(stripped) < 3:
        return False
    if _is_only_emoji(stripped):
        return False
    if _is_only_punctuation(stripped):
        return False
    return True


def filter_comments(comments: List[CommentDTO], since_minutes: int) -> List[CommentDTO]:
    """
    过滤评论：
    1. 时间窗口过滤：只保留since_minutes分钟内的评论
    2. 无效过滤：纯emoji、内容太短(<3字符)、纯标点
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=since_minutes)

    filtered = []
    for c in comments:
        # 确保时区感知
        ct = c.comment_time
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)

        # 时间窗口过滤
        if ct < cutoff:
            continue

        # 无效过滤
        if not _is_valid_comment(c.content):
            continue

        filtered.append(c)

    return filtered


# ── 采集服务 ──────────────────────────────────────────────────────────────────

async def crawl_account_comments(db: AsyncSession, monitor_account_id: int) -> dict:
    """
    对指定监控账号执行一次完整的评论采集流程：
    1. 获取监控账号信息
    2. 调用适配器获取视频列表，更新videos表
    3. 对每个视频调用fetch_comments
    4. 执行过滤逻辑
    5. 存入comments表（去重）
    """
    # 1. 获取监控账号
    result = await db.execute(
        select(MonitorAccount).where(MonitorAccount.id == monitor_account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        logger.warning("MonitorAccount id=%d not found, skip", monitor_account_id)
        return {"status": "not_found", "monitor_id": monitor_account_id}

    if account.status != "active":
        logger.info("MonitorAccount id=%d status=%s, skip", monitor_account_id, account.status)
        return {"status": "skipped", "reason": f"status={account.status}"}

    adapter = get_sentiment_adapter()
    now = datetime.now(timezone.utc)
    since_time = now - timedelta(minutes=account.poll_interval_min)

    # 2. 检查作品接口配额
    video_available, video_rate = await QuotaService.check_quota("video_api")
    if not video_available:
        logger.warning("Video API quota exceeded (%.1f%%), skip crawl for account %d", video_rate, monitor_account_id)
        return {"status": "quota_exceeded", "api_type": "video_api", "usage_rate": video_rate}

    # 3. 获取视频列表并更新videos表
    try:
        t0 = time.monotonic()
        video_dtos = await adapter.get_video_list(account.douyin_uid)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await QuotaService.increment_api_call("video_api")
        await log_api_call("video_api", "get_video_list", {"account_uid": account.douyin_uid}, 200, elapsed_ms, True)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await QuotaService.increment_api_call("video_api")
        await log_api_call("video_api", "get_video_list", {"account_uid": account.douyin_uid}, 500, elapsed_ms, False, str(exc))
        logger.error("Failed to get video list for account %d: %s", monitor_account_id, exc)
        return {"status": "error", "error": str(exc)}

    video_db_ids = {}  # video_id(str) -> db.id(int)
    for vd in video_dtos:
        existing = await db.execute(
            select(Video).where(Video.video_id == vd.video_id)
        )
        video_obj = existing.scalar_one_or_none()
        if video_obj is None:
            video_obj = Video(
                monitor_account_id=account.id,
                video_id=vd.video_id,
                title=vd.title,
                publish_time=vd.publish_time,
            )
            db.add(video_obj)
            await db.flush()
        else:
            video_obj.title = vd.title
            video_obj.publish_time = vd.publish_time

        video_obj.last_crawled_at = now
        video_db_ids[vd.video_id] = video_obj.id

    await db.flush()

    # 3 & 4 & 5. 对每个视频抓取评论、过滤、入库
    total_fetched = 0
    total_saved = 0
    total_duplicate = 0

    for vd in video_dtos:
        # 检查评论接口配额
        comment_available, comment_rate = await QuotaService.check_quota("comment_api")
        if not comment_available:
            logger.warning("Comment API quota exceeded (%.1f%%), skip remaining videos", comment_rate)
            break

        try:
            t0 = time.monotonic()
            raw_comments = await adapter.fetch_comments(vd.video_id, since_time)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            await QuotaService.increment_api_call("comment_api")
            await log_api_call("comment_api", "fetch_comments", {"video_id": vd.video_id}, 200, elapsed_ms, True)
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            await QuotaService.increment_api_call("comment_api")
            await log_api_call("comment_api", "fetch_comments", {"video_id": vd.video_id}, 500, elapsed_ms, False, str(exc))
            logger.error("Failed to fetch comments for video %s: %s", vd.video_id, exc)
            continue

        total_fetched += len(raw_comments)

        # 过滤
        valid_comments = filter_comments(raw_comments, account.poll_interval_min)

        # 获取已存在的comment_id用于去重
        if valid_comments:
            cid_list = [c.comment_id for c in valid_comments]
            existing_result = await db.execute(
                select(Comment.comment_id).where(Comment.comment_id.in_(cid_list))
            )
            existing_cids = set(row[0] for row in existing_result.all())
        else:
            existing_cids = set()

        video_db_id = video_db_ids.get(vd.video_id)
        for c in valid_comments:
            if c.comment_id in existing_cids:
                total_duplicate += 1
                continue
            comment_obj = Comment(
                video_id=video_db_id,
                comment_id=c.comment_id,
                user_uid=c.user_uid,
                user_nickname=c.user_nickname,
                content=c.content,
                comment_time=c.comment_time,
            )
            db.add(comment_obj)
            total_saved += 1

    await db.flush()

    result_info = {
        "status": "ok",
        "monitor_id": monitor_account_id,
        "videos_found": len(video_dtos),
        "total_fetched": total_fetched,
        "total_saved": total_saved,
        "total_duplicate": total_duplicate,
    }
    logger.info("Crawl result for account %d: %s", monitor_account_id, result_info)
    return result_info


async def get_crawl_stats(db: AsyncSession) -> dict:
    """获取今日采集统计"""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # 今日采集总数
    total_result = await db.execute(
        select(func.count()).select_from(Comment).where(Comment.crawled_at >= today_start)
    )
    total_today = total_result.scalar() or 0

    # 今日已处理（有效）数
    processed_result = await db.execute(
        select(func.count()).select_from(Comment).where(
            Comment.crawled_at >= today_start,
            Comment.is_processed == True,  # noqa: E712
        )
    )
    processed_today = processed_result.scalar() or 0

    return {
        "total_today": total_today,
        "processed_today": processed_today,
        "date": today_start.date().isoformat(),
    }


async def crawl_topic_comments(db: AsyncSession, topic_monitor_id: int) -> dict:
    """
    对指定话题监控执行一次完整的评论采集流程：
    1. 获取话题配置
    2. 调用适配器 fetch_topic_comments 采集该领域评论
    3. 去重 + 存入comments表(source_type="topic")
    4. 不做任何关键词过滤！所有评论直接存入，后续统一由AI意向识别处理
    """
    # 1. 获取话题监控
    result = await db.execute(
        select(TopicMonitor).where(TopicMonitor.id == topic_monitor_id)
    )
    topic_monitor = result.scalar_one_or_none()
    if not topic_monitor:
        logger.warning("TopicMonitor id=%d not found, skip", topic_monitor_id)
        return {"status": "not_found", "topic_monitor_id": topic_monitor_id}

    if topic_monitor.status != "active":
        logger.info("TopicMonitor id=%d status=%s, skip", topic_monitor_id, topic_monitor.status)
        return {"status": "skipped", "reason": f"status={topic_monitor.status}"}

    adapter = get_sentiment_adapter()
    now = datetime.now(timezone.utc)
    since_time = now - timedelta(minutes=topic_monitor.poll_interval_min)

    # 2. 检查评论接口配额
    comment_available, comment_rate = await QuotaService.check_quota("comment_api")
    if not comment_available:
        logger.warning("Comment API quota exceeded (%.1f%%), skip topic crawl '%s'", comment_rate, topic_monitor.topic)
        return {"status": "quota_exceeded", "api_type": "comment_api", "usage_rate": comment_rate}

    # 3. 调用适配器按话题/行业范围采集评论（不做关键词过滤）
    try:
        t0 = time.monotonic()
        raw_comments = await adapter.fetch_topic_comments(
            topic_monitor.topic, topic_monitor.industry, since_time
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await QuotaService.increment_api_call("comment_api")
        await log_api_call("comment_api", "fetch_topic_comments",
                           {"topic": topic_monitor.topic, "industry": topic_monitor.industry},
                           200, elapsed_ms, True)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await QuotaService.increment_api_call("comment_api")
        await log_api_call("comment_api", "fetch_topic_comments",
                           {"topic": topic_monitor.topic, "industry": topic_monitor.industry},
                           500, elapsed_ms, False, str(exc))
        logger.error("Failed to fetch topic comments for '%s': %s", topic_monitor.topic, exc)
        return {"status": "error", "error": str(exc)}

    total_fetched = len(raw_comments)

    # 3. 过滤（仅过滤无效评论：纯emoji、太短、纯标点）
    valid_comments = filter_comments(raw_comments, topic_monitor.poll_interval_min)

    # 4. 去重+入库，不做任何关键词过滤，全量存储交给AI判断
    if valid_comments:
        cid_list = [c.comment_id for c in valid_comments]
        existing_result = await db.execute(
            select(Comment.comment_id).where(Comment.comment_id.in_(cid_list))
        )
        existing_cids = set(row[0] for row in existing_result.all())
    else:
        existing_cids = set()

    total_saved = 0
    total_duplicate = 0

    for c in valid_comments:
        if c.comment_id in existing_cids:
            total_duplicate += 1
            continue
        comment_obj = Comment(
            video_id=None,  # 话题监控没有关联视频
            comment_id=c.comment_id,
            user_uid=c.user_uid,
            user_nickname=c.user_nickname,
            content=c.content,
            comment_time=c.comment_time,
            source_type="topic",
            source_topic_id=topic_monitor.id,
        )
        db.add(comment_obj)
        total_saved += 1

    await db.flush()

    result_info = {
        "status": "ok",
        "topic_monitor_id": topic_monitor_id,
        "topic": topic_monitor.topic,
        "total_fetched": total_fetched,
        "total_saved": total_saved,
        "total_duplicate": total_duplicate,
    }
    logger.info("Topic crawl result for '%s': %s", topic_monitor.topic, result_info)
    return result_info


# ── 视频生命周期管理与智能轮询 ────────────────────────────────────────────


async def sync_account_videos(db: AsyncSession, monitor_account_id: int) -> dict:
    """
    拉取账号视频列表，维护视频生命周期：
    - 只保存 VIDEO_LIFECYCLE_DAYS 天内的视频，超过则标记 expired
    - 根据评论数判断 heat_level（>= HIGH_HEAT_THRESHOLD 为 high）
    - 新视频 status=active
    - 已暂停视频若评论数增长，自动恢复 status=active
    """
    # 1. 获取监控账号
    result = await db.execute(
        select(MonitorAccount).where(MonitorAccount.id == monitor_account_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        logger.warning("sync_account_videos: MonitorAccount id=%d not found, skip", monitor_account_id)
        return {"status": "not_found", "monitor_id": monitor_account_id}

    if account.status != "active":
        logger.info("sync_account_videos: MonitorAccount id=%d status=%s, skip", monitor_account_id, account.status)
        return {"status": "skipped", "reason": f"status={account.status}"}

    adapter = get_sentiment_adapter()
    now = datetime.now(timezone.utc)
    lifecycle_cutoff = now - timedelta(days=settings.VIDEO_LIFECYCLE_DAYS)

    # 2. 检查作品接口配额
    video_available, video_rate = await QuotaService.check_quota("video_api")
    if not video_available:
        logger.warning("Video API quota exceeded (%.1f%%), skip sync for account %d", video_rate, monitor_account_id)
        return {"status": "quota_exceeded", "api_type": "video_api", "usage_rate": video_rate}

    # 3. 拉取视频列表
    try:
        t0 = time.monotonic()
        video_dtos = await adapter.get_video_list(account.douyin_uid)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await QuotaService.increment_api_call("video_api")
        await log_api_call("video_api", "get_video_list", {"account_uid": account.douyin_uid}, 200, elapsed_ms, True)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await QuotaService.increment_api_call("video_api")
        await log_api_call("video_api", "get_video_list", {"account_uid": account.douyin_uid}, 500, elapsed_ms, False, str(exc))
        logger.error("sync_account_videos: Failed to get video list for account %d: %s", monitor_account_id, exc)
        return {"status": "error", "error": str(exc)}

    synced_count = 0
    expired_count = 0
    resumed_count = 0

    for vd in video_dtos:
        # 确保 publish_time 时区感知
        pub_time = vd.publish_time
        if pub_time and pub_time.tzinfo is None:
            pub_time = pub_time.replace(tzinfo=timezone.utc)

        # 判断是否在生命周期内
        is_within_lifecycle = pub_time and pub_time > lifecycle_cutoff

        # 确定热度等级
        heat = "high" if vd.comment_count >= settings.HIGH_HEAT_THRESHOLD else "normal"

        # 查找或创建视频记录
        existing = await db.execute(
            select(Video).where(Video.video_id == vd.video_id)
        )
        video_obj = existing.scalar_one_or_none()

        if video_obj is None:
            if not is_within_lifecycle:
                # 超过生命周期的新视频不入库
                expired_count += 1
                continue
            video_obj = Video(
                monitor_account_id=account.id,
                video_id=vd.video_id,
                title=vd.title,
                publish_time=pub_time,
                heat_level=heat,
                status="active",
                last_comment_count=vd.comment_count,
            )
            db.add(video_obj)
            synced_count += 1
        else:
            # 更新已有视频
            video_obj.title = vd.title
            video_obj.publish_time = pub_time
            video_obj.heat_level = heat  # 动态更新热度

            if not is_within_lifecycle:
                if video_obj.status != "expired":
                    video_obj.status = "expired"
                    expired_count += 1
            else:
                # 视频恢复机制：已暂停视频评论数增长 -> 恢复active
                if video_obj.status == "paused" and vd.comment_count > video_obj.last_comment_count:
                    video_obj.status = "active"
                    video_obj.zero_comment_streak = 0
                    resumed_count += 1
                    logger.info(
                        "Video %s resumed: comment_count grew from %d to %d",
                        vd.video_id, video_obj.last_comment_count, vd.comment_count,
                    )

                # 确保非过期的 active/paused 视频保持正确状态
                if video_obj.status == "expired" and is_within_lifecycle:
                    video_obj.status = "active"

            video_obj.last_comment_count = vd.comment_count

    await db.flush()

    # 3. 将本账号下超出生命周期的旧视频标记 expired
    old_videos_result = await db.execute(
        select(Video).where(
            Video.monitor_account_id == monitor_account_id,
            Video.status != "expired",
            Video.publish_time < lifecycle_cutoff,
        )
    )
    for old_video in old_videos_result.scalars().all():
        old_video.status = "expired"
        expired_count += 1
    await db.flush()

    result_info = {
        "status": "ok",
        "monitor_id": monitor_account_id,
        "synced": synced_count,
        "expired": expired_count,
        "resumed": resumed_count,
        "total_videos": len(video_dtos),
    }
    logger.info("sync_account_videos result for account %d: %s", monitor_account_id, result_info)
    return result_info


def should_poll_video(video: Video) -> bool:
    """
    判断视频是否到了该轮询的时间。
    根据 heat_level 和降级状态计算下次轮询时间。
    """
    if video.status != "active":
        return False

    now = datetime.now(timezone.utc)

    # 基础轮询间隔
    if video.heat_level == "high":
        base_interval_min = settings.HIGH_HEAT_POLL_INTERVAL
    else:
        base_interval_min = settings.NORMAL_POLL_INTERVAL

    # 降级逻辑：连续无新评论次数越多，间隔越长
    streak = video.zero_comment_streak
    if streak >= settings.DEGRADATION_STREAK_PAUSE:
        # 应该被暂停了，这里做个容错检查
        return False
    elif streak >= settings.DEGRADATION_STREAK_DOUBLE:
        # 间隔翻倍
        base_interval_min *= 2

    # 如果从未轮询过，立即轮询
    if video.last_poll_time is None:
        return True

    last_poll = video.last_poll_time
    if last_poll.tzinfo is None:
        last_poll = last_poll.replace(tzinfo=timezone.utc)

    elapsed = (now - last_poll).total_seconds()
    return elapsed >= base_interval_min * 60


async def poll_video_comments(db: AsyncSession, video_db_id: int) -> dict:
    """
    对单个视频执行评论轮询，包含生命周期检查和智能降级：
    - 检查视频是否过期（发布超 VIDEO_LIFECYCLE_DAYS 天 → 标记 expired, 跳过）
    - 检查视频 status 是否 active
    - 只拉取第一页最新评论 (page_size=80)
    - 只保留 COMMENT_VALIDITY_WINDOW_MIN 分钟以内的评论
    - 对比评论数实现降级逻辑
    """
    # 1. 获取视频记录
    result = await db.execute(
        select(Video).where(Video.id == video_db_id)
    )
    video = result.scalar_one_or_none()
    if not video:
        logger.warning("poll_video_comments: Video id=%d not found, skip", video_db_id)
        return {"status": "not_found", "video_id": video_db_id}

    now = datetime.now(timezone.utc)

    # 2. 生命周期检查：发布超期 → 标记 expired
    lifecycle_cutoff = now - timedelta(days=settings.VIDEO_LIFECYCLE_DAYS)
    if video.publish_time:
        pub_time = video.publish_time
        if pub_time.tzinfo is None:
            pub_time = pub_time.replace(tzinfo=timezone.utc)
        if pub_time < lifecycle_cutoff:
            video.status = "expired"
            await db.flush()
            logger.info("Video %s expired (published %s)", video.video_id, pub_time)
            return {"status": "expired", "video_id": video.video_id}

    # 3. 状态检查
    if video.status != "active":
        return {"status": "skipped", "video_id": video.video_id, "reason": f"status={video.status}"}

    # 4. 检查是否到了轮询时间
    if not should_poll_video(video):
        return {"status": "not_due", "video_id": video.video_id}

    # 5. 检查评论接口配额
    comment_available, comment_rate = await QuotaService.check_quota("comment_api")
    if not comment_available:
        logger.warning("Comment API quota exceeded (%.1f%%), skip poll for video %s", comment_rate, video.video_id)
        return {"status": "quota_exceeded", "video_id": video.video_id, "api_type": "comment_api", "usage_rate": comment_rate}

    # 6. 拉取评论
    adapter = get_sentiment_adapter()
    since_time = now - timedelta(minutes=settings.COMMENT_VALIDITY_WINDOW_MIN)

    try:
        t0 = time.monotonic()
        raw_comments = await adapter.fetch_comments(video.video_id, since_time)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await QuotaService.increment_api_call("comment_api")
        await log_api_call("comment_api", "fetch_comments", {"video_id": video.video_id}, 200, elapsed_ms, True)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await QuotaService.increment_api_call("comment_api")
        await log_api_call("comment_api", "fetch_comments", {"video_id": video.video_id}, 500, elapsed_ms, False, str(exc))
        logger.error("poll_video_comments: Failed to fetch comments for video %s: %s", video.video_id, exc)
        return {"status": "error", "video_id": video.video_id, "error": str(exc)}

    # 6. 过滤：时间窗口 + 无效评论
    valid_comments = filter_comments(raw_comments, settings.COMMENT_VALIDITY_WINDOW_MIN)

    # 7. 去重入库
    if valid_comments:
        cid_list = [c.comment_id for c in valid_comments]
        existing_result = await db.execute(
            select(Comment.comment_id).where(Comment.comment_id.in_(cid_list))
        )
        existing_cids = set(row[0] for row in existing_result.all())
    else:
        existing_cids = set()

    new_saved = 0
    for c in valid_comments:
        if c.comment_id in existing_cids:
            continue
        comment_obj = Comment(
            video_id=video.id,
            comment_id=c.comment_id,
            user_uid=c.user_uid,
            user_nickname=c.user_nickname,
            content=c.content,
            comment_time=c.comment_time,
        )
        db.add(comment_obj)
        new_saved += 1

    await db.flush()

    # 8. 评论数对比 & 降级逻辑
    #    用新增保存数来判断是否有新评论（比用 last_comment_count 更可靠，因为采集的是时间窗口内的）
    if new_saved > 0:
        # 有新增评论：重置连续无新评论计数
        video.zero_comment_streak = 0
    else:
        # 无新增评论：连续计数 +1
        video.zero_comment_streak += 1

    # 9. 降级状态更新
    if video.zero_comment_streak >= settings.DEGRADATION_STREAK_PAUSE:
        video.status = "paused"
        logger.info(
            "Video %s paused: zero_comment_streak=%d >= %d",
            video.video_id, video.zero_comment_streak, settings.DEGRADATION_STREAK_PAUSE,
        )
    elif video.zero_comment_streak >= settings.DEGRADATION_STREAK_DOUBLE:
        logger.debug(
            "Video %s degraded: zero_comment_streak=%d, poll interval doubled",
            video.video_id, video.zero_comment_streak,
        )

    # 10. 更新轮询时间
    video.last_poll_time = now
    video.last_crawled_at = now
    await db.flush()

    result_info = {
        "status": "ok",
        "video_id": video.video_id,
        "fetched": len(raw_comments),
        "saved": new_saved,
        "zero_streak": video.zero_comment_streak,
        "heat_level": video.heat_level,
        "video_status": video.status,
    }
    logger.info("poll_video_comments result for video %s: %s", video.video_id, result_info)
    return result_info
