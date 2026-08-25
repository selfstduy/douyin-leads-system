import datetime
import io
from typing import List, Optional

from sqlalchemy import select, func, and_, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.models.lead import Lead, LeadFollowup
from app.models.monitor import MonitorAccount
from app.models.user import User
from app.models.video import Video
from app.schemas.stats import (
    DashboardOverview,
    SalesPerformanceItem,
    MonitorStatsItem,
    TrendDataPoint,
    TrendResponse,
)


async def get_dashboard_overview(db: AsyncSession) -> DashboardOverview:
    """获取今日概览数据"""
    today = datetime.date.today()
    today_start = datetime.datetime(today.year, today.month, today.day, tzinfo=datetime.timezone.utc)
    tomorrow_start = today_start + datetime.timedelta(days=1)

    # 今日新线索数
    leads_today_q = select(func.count(Lead.id)).where(
        and_(Lead.created_at >= today_start, Lead.created_at < tomorrow_start)
    )
    today_leads = (await db.execute(leads_today_q)).scalar() or 0

    # 今日高意向数
    high_intent_today_q = select(func.count(Lead.id)).where(
        and_(
            Lead.created_at >= today_start,
            Lead.created_at < tomorrow_start,
            Lead.intent_level == "high",
        )
    )
    today_high_intent = (await db.execute(high_intent_today_q)).scalar() or 0

    # 今日已转化数 (status=converted, created today as proxy)
    converted_today_q = select(func.count(Lead.id)).where(
        and_(
            Lead.created_at >= today_start,
            Lead.created_at < tomorrow_start,
            Lead.status == "converted",
        )
    )
    today_converted = (await db.execute(converted_today_q)).scalar() or 0

    # 待跟进总数 (status in assigned/following)
    pending_q = select(func.count(Lead.id)).where(
        Lead.status.in_(["assigned", "following"])
    )
    pending_followup = (await db.execute(pending_q)).scalar() or 0

    # 今日新评论采集数
    comments_today_q = select(func.count(Comment.id)).where(
        and_(Comment.crawled_at >= today_start, Comment.crawled_at < tomorrow_start)
    )
    today_comments = (await db.execute(comments_today_q)).scalar() or 0

    return DashboardOverview(
        today_leads=today_leads,
        today_high_intent=today_high_intent,
        today_converted=today_converted,
        pending_followup=pending_followup,
        today_comments=today_comments,
    )


async def get_sales_performance(
    db: AsyncSession,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
) -> List[SalesPerformanceItem]:
    """销售业绩统计 - 按销售人员"""
    # Build date filter
    conditions = [Lead.assigned_to.isnot(None)]
    if start_date:
        conditions.append(Lead.created_at >= datetime.datetime(start_date.year, start_date.month, start_date.day, tzinfo=datetime.timezone.utc))
    if end_date:
        end_dt = datetime.datetime(end_date.year, end_date.month, end_date.day, tzinfo=datetime.timezone.utc) + datetime.timedelta(days=1)
        conditions.append(Lead.created_at < end_dt)

    # Get all sales users
    sales_q = select(User).where(User.role == "sales", User.status == "active")
    sales_result = await db.execute(sales_q)
    sales_users = sales_result.scalars().all()

    items: List[SalesPerformanceItem] = []
    for user in sales_users:
        user_cond = conditions + [Lead.assigned_to == user.id]

        total_q = select(func.count(Lead.id)).where(and_(*user_cond))
        total_leads = (await db.execute(total_q)).scalar() or 0

        high_q = select(func.count(Lead.id)).where(and_(*user_cond, Lead.intent_level == "high"))
        high_intent = (await db.execute(high_q)).scalar() or 0

        conv_q = select(func.count(Lead.id)).where(and_(*user_cond, Lead.status == "converted"))
        converted = (await db.execute(conv_q)).scalar() or 0

        conversion_rate = round(converted / total_leads * 100, 1) if total_leads > 0 else 0.0

        # 平均响应时长：assigned_at - created_at (hours)
        if total_leads > 0:
            avg_q = select(
                func.avg(func.extract("epoch", Lead.assigned_at) - func.extract("epoch", Lead.created_at))
            ).where(and_(*user_cond, Lead.assigned_at.isnot(None)))
            avg_seconds = (await db.execute(avg_q)).scalar()
            avg_response_hours = round((avg_seconds or 0) / 3600, 1)
        else:
            avg_response_hours = 0.0

        items.append(
            SalesPerformanceItem(
                user_id=user.id,
                username=user.username,
                total_leads=total_leads,
                high_intent=high_intent,
                converted=converted,
                conversion_rate=conversion_rate,
                avg_response_hours=avg_response_hours,
            )
        )

    return items


async def get_monitor_stats(
    db: AsyncSession,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
) -> List[MonitorStatsItem]:
    """监控效果统计 - 按监控账号"""
    # Date conditions on comments
    comment_date_conds = []
    if start_date:
        comment_date_conds.append(Comment.crawled_at >= datetime.datetime(start_date.year, start_date.month, start_date.day, tzinfo=datetime.timezone.utc))
    if end_date:
        end_dt = datetime.datetime(end_date.year, end_date.month, end_date.day, tzinfo=datetime.timezone.utc) + datetime.timedelta(days=1)
        comment_date_conds.append(Comment.crawled_at < end_dt)

    # Get all monitor accounts
    monitors_q = select(MonitorAccount)
    monitors_result = await db.execute(monitors_q)
    monitors = monitors_result.scalars().all()

    items: List[MonitorStatsItem] = []
    for monitor in monitors:
        # Count comments for this monitor's videos
        comment_cond = [Video.monitor_account_id == monitor.id] + comment_date_conds
        comments_q = (
            select(func.count(Comment.id))
            .join(Video, Comment.video_id == Video.id)
            .where(and_(*comment_cond))
        )
        total_comments = (await db.execute(comments_q)).scalar() or 0

        # Count leads from those comments
        lead_cond = [Video.monitor_account_id == monitor.id] + comment_date_conds
        leads_q = (
            select(func.count(Lead.id))
            .join(Comment, Lead.comment_id == Comment.id)
            .join(Video, Comment.video_id == Video.id)
            .where(and_(*lead_cond))
        )
        total_leads = (await db.execute(leads_q)).scalar() or 0

        lead_rate = round(total_leads / total_comments * 100, 1) if total_comments > 0 else 0.0

        items.append(
            MonitorStatsItem(
                monitor_id=monitor.id,
                nickname=monitor.nickname,
                total_comments=total_comments,
                total_leads=total_leads,
                lead_rate=lead_rate,
            )
        )

    # Sort by lead_rate desc
    items.sort(key=lambda x: x.lead_rate, reverse=True)
    return items


async def get_trend_data(db: AsyncSession, days: int = 7) -> TrendResponse:
    """时间趋势数据 - 从数据库实时查询"""
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days - 1)
    start_dt = datetime.datetime(start.year, start.month, start.day, tzinfo=datetime.timezone.utc)

    # 每天评论数
    comments_q = (
        select(
            cast(Comment.crawled_at, Date).label("d"),
            func.count(Comment.id).label("cnt"),
        )
        .where(Comment.crawled_at >= start_dt)
        .group_by(cast(Comment.crawled_at, Date))
    )
    comments_result = await db.execute(comments_q)
    comments_map = {row.d: row.cnt for row in comments_result}

    # 每天线索数
    leads_q = (
        select(
            cast(Lead.created_at, Date).label("d"),
            func.count(Lead.id).label("cnt"),
        )
        .where(Lead.created_at >= start_dt)
        .group_by(cast(Lead.created_at, Date))
    )
    leads_result = await db.execute(leads_q)
    leads_map = {row.d: row.cnt for row in leads_result}

    # 每天高意向数
    high_q = (
        select(
            cast(Lead.created_at, Date).label("d"),
            func.count(Lead.id).label("cnt"),
        )
        .where(Lead.created_at >= start_dt, Lead.intent_level == "high")
        .group_by(cast(Lead.created_at, Date))
    )
    high_result = await db.execute(high_q)
    high_map = {row.d: row.cnt for row in high_result}

    # 每天转化数
    conv_q = (
        select(
            cast(Lead.created_at, Date).label("d"),
            func.count(Lead.id).label("cnt"),
        )
        .where(Lead.created_at >= start_dt, Lead.status == "converted")
        .group_by(cast(Lead.created_at, Date))
    )
    conv_result = await db.execute(conv_q)
    conv_map = {row.d: row.cnt for row in conv_result}

    # Build daily points
    data: List[TrendDataPoint] = []
    for i in range(days):
        d = start + datetime.timedelta(days=i)
        data.append(
            TrendDataPoint(
                date=d.isoformat(),
                comments=comments_map.get(d, 0),
                leads=leads_map.get(d, 0),
                high_intent=high_map.get(d, 0),
                converted=conv_map.get(d, 0),
            )
        )

    return TrendResponse(data=data)


async def export_leads_excel(
    db: AsyncSession,
    filters: Optional[dict] = None,
) -> io.BytesIO:
    """导出线索数据为Excel"""
    from openpyxl import Workbook

    filters = filters or {}
    conditions = []
    if filters.get("status"):
        conditions.append(Lead.status == filters["status"])
    if filters.get("intent_level"):
        conditions.append(Lead.intent_level == filters["intent_level"])
    if filters.get("assigned_to"):
        conditions.append(Lead.assigned_to == int(filters["assigned_to"]))
    if filters.get("start_date"):
        sd = datetime.date.fromisoformat(filters["start_date"])
        conditions.append(Lead.created_at >= datetime.datetime(sd.year, sd.month, sd.day, tzinfo=datetime.timezone.utc))
    if filters.get("end_date"):
        ed = datetime.date.fromisoformat(filters["end_date"])
        conditions.append(Lead.created_at < datetime.datetime(ed.year, ed.month, ed.day, tzinfo=datetime.timezone.utc) + datetime.timedelta(days=1))

    q = select(Lead).where(and_(*conditions)).order_by(Lead.created_at.desc()).limit(10000)
    result = await db.execute(q)
    leads = result.scalars().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "线索数据"

    headers = ["ID", "用户昵称", "意向等级", "状态", "AI分析原因", "分配人ID", "创建时间"]
    ws.append(headers)

    status_map = {"pending": "待处理", "assigned": "已分配", "following": "跟进中", "converted": "已转化", "closed": "已关闭"}
    intent_map = {"high": "高", "medium": "中", "low": "低"}

    for lead in leads:
        ws.append([
            lead.id,
            lead.user_nickname,
            intent_map.get(lead.intent_level, lead.intent_level),
            status_map.get(lead.status, lead.status),
            lead.ai_reason,
            lead.assigned_to or "",
            lead.created_at.strftime("%Y-%m-%d %H:%M:%S") if lead.created_at else "",
        ])

    # Auto-width
    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter
        for cell in col:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[col_letter].width = min(max_length + 4, 40)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
