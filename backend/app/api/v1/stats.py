import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user, require_admin
from app.schemas.common import ResponseModel
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["统计"])


@router.get("/dashboard", response_model=ResponseModel)
async def dashboard(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """今日概览数据"""
    data = await stats_service.get_dashboard_overview(db)
    return ResponseModel(data=data.model_dump())


@router.get("/sales-performance", response_model=ResponseModel)
async def sales_performance(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """销售业绩统计（仅admin）"""
    sd = datetime.date.fromisoformat(start_date) if start_date else None
    ed = datetime.date.fromisoformat(end_date) if end_date else None
    items = await stats_service.get_sales_performance(db, sd, ed)
    return ResponseModel(data=[i.model_dump() for i in items])


@router.get("/monitor-stats", response_model=ResponseModel)
async def monitor_stats(
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """监控效果统计"""
    sd = datetime.date.fromisoformat(start_date) if start_date else None
    ed = datetime.date.fromisoformat(end_date) if end_date else None
    items = await stats_service.get_monitor_stats(db, sd, ed)
    return ResponseModel(data=[i.model_dump() for i in items])


@router.get("/trend", response_model=ResponseModel)
async def trend(
    days: int = Query(7, ge=1, le=90, description="天数"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """时间趋势数据"""
    result = await stats_service.get_trend_data(db, days)
    return ResponseModel(data=result.model_dump())


@router.get("/export")
async def export_leads(
    status: Optional[str] = Query(None),
    intent_level: Optional[str] = Query(None),
    assigned_to: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """导出线索数据Excel（仅admin）"""
    filters = {}
    if status:
        filters["status"] = status
    if intent_level:
        filters["intent_level"] = intent_level
    if assigned_to:
        filters["assigned_to"] = assigned_to
    if start_date:
        filters["start_date"] = start_date
    if end_date:
        filters["end_date"] = end_date

    buf = await stats_service.export_leads_excel(db, filters)
    filename = f"leads_export_{datetime.date.today().isoformat()}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
