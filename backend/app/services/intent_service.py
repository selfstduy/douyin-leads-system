"""意向识别服务 — 批量分析评论并自动创建线索。"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import get_llm_adapter
from app.adapters.llm_base import IntentLevel, IntentResult
from app.models.comment import Comment
from app.models.lead import Lead
from app.models.monitor import MonitorAccount
from app.models.video import Video

logger = logging.getLogger(__name__)

# 每批处理的最大评论数
BATCH_SIZE = 50


async def process_unanalyzed_comments(db: AsyncSession, limit: int = BATCH_SIZE) -> dict:
    """
    处理未分析的评论:
    1. 查询is_processed=False的评论
    2. 批量调用LLM适配器分析
    3. high/medium → 创建Lead; invalid → 仅标记已处理
    4. 更新comment.is_processed = True
    5. 去重: 同一user_uid + 同一video_id只创建一条线索
    """
    # 查询未处理的评论
    stmt = (
        select(Comment)
        .where(Comment.is_processed == False)  # noqa: E712
        .limit(limit)
    )
    result = await db.execute(stmt)
    comments = list(result.scalars().all())

    if not comments:
        return {"processed": 0, "leads_created": 0, "lead_ids": []}

    # 预加载视频标题信息 (video_id → title)
    video_ids = list({c.video_id for c in comments})
    video_map: dict[int, str] = {}
    if video_ids:
        vresult = await db.execute(select(Video.id, Video.title).where(Video.id.in_(video_ids)))
        for row in vresult.all():
            video_map[row[0]] = row[1]

    # 构造LLM输入
    llm_comments = []
    for c in comments:
        llm_comments.append({
            "comment_id": str(c.id),
            "content": c.content,
            "video_title": video_map.get(c.video_id, ""),
        })

    # 调用LLM批量分析
    adapter = get_llm_adapter()
    try:
        intent_results = await adapter.batch_analyze_intent(llm_comments)
    except Exception as exc:
        logger.error("LLM batch analysis failed: %s, marking all as invalid", exc)
        intent_results = [
            IntentResult(
                comment_id=str(c.id),
                intent_level=IntentLevel.INVALID,
                reason="AI分析服务异常，自动标记为无效",
                confidence=0.0,
            )
            for c in comments
        ]

    # 构建comment.id → IntentResult映射
    result_map: dict[int, IntentResult] = {}
    for ir in intent_results:
        try:
            result_map[int(ir.comment_id)] = ir
        except (ValueError, TypeError):
            logger.warning("Invalid comment_id in IntentResult: %s", ir.comment_id)

    # 查询已存在的线索用于去重 (user_uid + video_id)
    existing_leads = await _get_existing_lead_keys(db, comments)

    leads_created = 0
    lead_ids_created: list[int] = []
    for comment in comments:
        ir = result_map.get(comment.id)
        if ir is None:
            # 未返回结果的，标记invalid
            comment.is_processed = True
            continue

        # 标记为已处理
        comment.is_processed = True

        # high/medium → 创建线索(去重)
        if ir.intent_level in (IntentLevel.HIGH, IntentLevel.MEDIUM):
            dedup_key = (comment.user_uid, comment.video_id)
            if dedup_key not in existing_leads:
                lead = await create_lead_from_intent(db, comment, ir)
                if lead:
                    existing_leads.add(dedup_key)
                    leads_created += 1
                    lead_ids_created.append(lead.id)

    await db.flush()

    logger.info(
        "Intent analysis complete: processed=%d, leads_created=%d",
        len(comments), leads_created,
    )
    return {
        "processed": len(comments),
        "leads_created": leads_created,
        "lead_ids": lead_ids_created,
    }


async def analyze_single_comment(db: AsyncSession, comment_id: int) -> Optional[dict]:
    """重新分析单条评论(管理员手动触发)"""
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    if not comment:
        return None

    # 获取视频标题
    vresult = await db.execute(select(Video.title).where(Video.id == comment.video_id))
    video_title = vresult.scalar_one_or_none() or ""

    adapter = get_llm_adapter()
    try:
        ir = await adapter.analyze_intent(
            comment.content,
            context={"comment_id": str(comment.id), "video_title": video_title},
        )
    except Exception as exc:
        logger.error("LLM single analysis failed for comment %d: %s", comment_id, exc)
        return {"error": f"AI分析失败: {exc}"}

    # 删除旧线索(如果有)
    await db.execute(
        select(Lead).where(and_(
            Lead.comment_id == comment.id,
            Lead.video_id == comment.video_id,
        ))
    )
    # 检查是否存在旧线索
    old_result = await db.execute(
        select(Lead).where(and_(
            Lead.comment_id == comment.id,
            Lead.video_id == comment.video_id,
        ))
    )
    old_lead = old_result.scalar_one_or_none()
    if old_lead:
        await db.delete(old_lead)

    # 去重检查
    existing_leads = await _get_existing_lead_keys(db, [comment])
    dedup_key = (comment.user_uid, comment.video_id)

    lead = None
    if ir.intent_level in (IntentLevel.HIGH, IntentLevel.MEDIUM):
        if dedup_key not in existing_leads:
            lead = await create_lead_from_intent(db, comment, ir)
        else:
            # 已存在同用户+同视频的线索，更新原线索
            existing_result = await db.execute(
                select(Lead).where(and_(
                    Lead.user_uid == comment.user_uid,
                    Lead.video_id == comment.video_id,
                )).limit(1)
            )
            existing_lead = existing_result.scalar_one_or_none()
            if existing_lead:
                existing_lead.intent_level = ir.intent_level.value
                existing_lead.ai_reason = ir.reason
                lead = existing_lead

    comment.is_processed = True
    await db.flush()

    return {
        "comment_id": comment.id,
        "intent_level": ir.intent_level.value,
        "reason": ir.reason,
        "confidence": ir.confidence,
        "lead_created": lead is not None,
        "lead_id": lead.id if lead else None,
    }


async def create_lead_from_intent(
    db: AsyncSession,
    comment: Comment,
    intent_result: IntentResult,
) -> Optional[Lead]:
    """根据意向分析结果创建Lead记录"""
    lead = Lead(
        comment_id=comment.id,
        video_id=comment.video_id,
        user_uid=comment.user_uid,
        user_nickname=comment.user_nickname,
        user_avatar="",
        intent_level=intent_result.intent_level.value,
        ai_reason=intent_result.reason,
        status="pending",
    )
    db.add(lead)
    await db.flush()

    # high意向时同步更新对应monitor_account的统计
    if intent_result.intent_level == IntentLevel.HIGH:
        await _update_monitor_account_high_stats(db, comment.video_id)

    return lead


async def _update_monitor_account_high_stats(db: AsyncSession, video_id: int):
    """更新对应monitor_account的high评论统计

    通过 comment.video_id -> Video.monitor_account_id -> MonitorAccount 追溯
    """
    vresult = await db.execute(select(Video).where(Video.id == video_id))
    video = vresult.scalar_one_or_none()
    if not video or not video.monitor_account_id:
        return

    mresult = await db.execute(
        select(MonitorAccount).where(MonitorAccount.id == video.monitor_account_id)
    )
    account = mresult.scalar_one_or_none()
    if not account:
        return

    account.last_high_intent_at = datetime.now(timezone.utc)
    account.total_high_count += 1
    await db.flush()


async def _get_existing_lead_keys(db: AsyncSession, comments: List[Comment]) -> set:
    """查询已存在的线索，返回 (user_uid, video_id) 集合用于去重"""
    if not comments:
        return set()

    # 构建去重条件
    dedup_keys = list({(c.user_uid, c.video_id) for c in comments})
    conditions = [
        and_(Lead.user_uid == uid, Lead.video_id == vid)
        for uid, vid in dedup_keys
    ]

    result = await db.execute(
        select(Lead.user_uid, Lead.video_id).where(
            # 使用or_组合条件
            conditions[0] if len(conditions) == 1 else or_(*conditions)
        )
    )
    return {(row[0], row[1]) for row in result.all()}


async def get_intent_stats(db: AsyncSession) -> dict:
    """获取意向统计(各级别数量)"""
    # 按intent_level分组统计
    result = await db.execute(
        select(Lead.intent_level, func.count(Lead.id))
        .group_by(Lead.intent_level)
    )
    stats = {row[0]: row[1] for row in result.all()}

    # 确保三个级别都有
    return {
        "high": stats.get("high", 0),
        "medium": stats.get("medium", 0),
        "invalid": stats.get("invalid", 0),
        "total": sum(stats.values()),
    }
