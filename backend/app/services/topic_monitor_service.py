"""Topic monitor service — business logic for topic-based monitoring."""

from typing import Optional, Tuple

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.topic_monitor import TopicMonitor
from app.schemas.topic_monitor import TopicMonitorCreate, TopicMonitorUpdate


async def create_topic_monitor(
    db: AsyncSession, data: TopicMonitorCreate, created_by: Optional[int] = None
) -> TopicMonitor:
    """创建话题监控"""
    monitor = TopicMonitor(
        topic=data.topic,
        description=data.description,
        industry=data.industry,
        poll_interval_min=data.poll_interval_min,
        created_by=created_by,
    )
    db.add(monitor)
    await db.flush()
    await db.refresh(monitor)
    return monitor


async def get_topic_monitor_by_id(db: AsyncSession, monitor_id: int) -> Optional[TopicMonitor]:
    result = await db.execute(
        select(TopicMonitor).where(TopicMonitor.id == monitor_id)
    )
    return result.scalar_one_or_none()


async def get_topic_monitors(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> Tuple[list, int]:
    """返回(列表, 总数)带分页和筛选"""
    query = select(TopicMonitor)
    count_query = select(sa_func.count()).select_from(TopicMonitor)

    if status_filter:
        query = query.where(TopicMonitor.status == status_filter)
        count_query = count_query.where(TopicMonitor.status == status_filter)

    if search:
        like_pattern = f"%{search}%"
        query = query.where(TopicMonitor.topic.ilike(like_pattern))
        count_query = count_query.where(TopicMonitor.topic.ilike(like_pattern))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(TopicMonitor.id.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    monitors = list(result.scalars().all())

    return monitors, total


async def update_topic_monitor(
    db: AsyncSession, monitor_id: int, data: TopicMonitorUpdate
) -> Optional[TopicMonitor]:
    monitor = await get_topic_monitor_by_id(db, monitor_id)
    if monitor is None:
        return None
    if data.topic is not None:
        monitor.topic = data.topic
    if data.description is not None:
        monitor.description = data.description
    if data.industry is not None:
        monitor.industry = data.industry
    if data.poll_interval_min is not None:
        monitor.poll_interval_min = data.poll_interval_min
    await db.flush()
    await db.refresh(monitor)
    return monitor


async def delete_topic_monitor(db: AsyncSession, monitor_id: int) -> bool:
    """删除话题监控（硬删除）"""
    monitor = await get_topic_monitor_by_id(db, monitor_id)
    if monitor is None:
        return False
    await db.delete(monitor)
    await db.flush()
    return True


async def toggle_topic_monitor(db: AsyncSession, monitor_id: int) -> Optional[TopicMonitor]:
    """启停切换"""
    monitor = await get_topic_monitor_by_id(db, monitor_id)
    if monitor is None:
        return None
    monitor.status = 'paused' if monitor.status == 'active' else 'active'
    await db.flush()
    await db.refresh(monitor)
    return monitor
