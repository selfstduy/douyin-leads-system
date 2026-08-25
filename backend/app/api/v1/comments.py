from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.models.comment import Comment
from app.models.video import Video
from app.models.monitor import MonitorAccount
from app.schemas.comment import (
    CommentOut,
    CommentListResponse,
    CrawlStatsResponse,
    CrawlStats,
    CrawlResultResponse,
)
from app.services.crawler_service import crawl_account_comments, get_crawl_stats

router = APIRouter(prefix="/comments", tags=["comments"])


@router.get("", response_model=CommentListResponse)
async def get_comments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    video_id: Optional[int] = Query(None, description="按视频ID筛选"),
    monitor_id: Optional[int] = Query(None, description="按监控账号ID筛选"),
    db: AsyncSession = Depends(get_db),
):
    """评论列表（分页，可按视频/监控账号筛选）"""
    query = select(Comment)
    count_query = select(func.count()).select_from(Comment)

    if video_id is not None:
        query = query.where(Comment.video_id == video_id)
        count_query = count_query.where(Comment.video_id == video_id)

    if monitor_id is not None:
        # 通过关联Video表筛选
        query = query.join(Video, Comment.video_id == Video.id).where(
            Video.monitor_account_id == monitor_id
        )
        count_query = count_query.join(Video, Comment.video_id == Video.id).where(
            Video.monitor_account_id == monitor_id
        )

    # 总数
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页查询
    offset = (page - 1) * page_size
    query = query.order_by(Comment.crawled_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    comments = result.scalars().all()

    return CommentListResponse(
        data=[CommentOut.model_validate(c) for c in comments],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=CrawlStatsResponse)
async def get_crawl_statistics(db: AsyncSession = Depends(get_db)):
    """获取今日采集统计"""
    stats = await get_crawl_stats(db)
    return CrawlStatsResponse(data=CrawlStats(**stats))


@router.post("/manual-crawl/{monitor_id}", response_model=CrawlResultResponse)
async def manual_crawl(monitor_id: int, db: AsyncSession = Depends(get_db)):
    """手动触发一次采集"""
    # 先检查账号是否存在
    result = await db.execute(
        select(MonitorAccount).where(MonitorAccount.id == monitor_id)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="监控账号不存在")

    # 同步执行采集（手动触发时即时返回结果）
    try:
        crawl_result = await crawl_account_comments(db, monitor_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"采集失败: {str(exc)}")

    return CrawlResultResponse(data=crawl_result)
