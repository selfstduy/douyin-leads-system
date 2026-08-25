"""风控管理API — 举报拉黑率监控、熔断恢复、黑名单管理。"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user, require_admin
from app.schemas.common import ResponseModel, PageResponse
from app.services.risk_control_service import (
    risk_control_service,
    EVENT_REPORT,
    EVENT_BLOCK,
)

router = APIRouter(prefix="/risk", tags=["风控管理"])


# ── 请求模型 ─────────────────────────────────────────────────────────────────


class BlacklistRequest(BaseModel):
    user_uid: str = Field(..., description="抖音用户UID")
    reason: str = Field("manual", description="原因: blacklisted_by_user/reported/manual")


class ReportEventRequest(BaseModel):
    event_type: str = Field(
        ..., description="事件类型: sent/read/reply/report/block/wechat_added"
    )
    user_uid: Optional[str] = Field(None, description="关联用户UID(举报/拉黑时可选)")
    count: int = Field(1, ge=1, description="数量")


# ── 统计 & 状态 ───────────────────────────────────────────────────────────────


@router.get("/stats", response_model=ResponseModel)
async def get_risk_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """今日风控统计: 发送/已读/回复/举报/拉黑/加微/率值"""
    stats = await risk_control_service.get_today_stats(db)
    rate = (
        (stats.report_count + stats.block_count) / stats.sent_count
        if stats.sent_count
        else 0.0
    )
    return ResponseModel(data={
        "date": stats.date.isoformat() if stats.date else None,
        "sent_count": stats.sent_count,
        "read_count": stats.read_count,
        "reply_count": stats.reply_count,
        "report_count": stats.report_count,
        "block_count": stats.block_count,
        "wechat_added_count": stats.wechat_added_count,
        "report_rate": round(rate, 4),
        "report_rate_pct": f"{rate:.2%}",
    })


@router.get("/status", response_model=ResponseModel)
async def get_risk_status(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """当前风控状态: normal/warning/critical + 降量/暂停标记"""
    status = await risk_control_service.get_status(db)
    return ResponseModel(data=status)


# ── 熔断恢复 ─────────────────────────────────────────────────────────────────


@router.post("/resume", response_model=ResponseModel)
async def resume_sending(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """人工恢复发送(admin only) — 清除熔断暂停标记"""
    await risk_control_service.resume_sending(db)
    return ResponseModel(message="发送已恢复", data={"paused": False})


# ── 黑名单管理 ───────────────────────────────────────────────────────────────


@router.get("/blacklist", response_model=PageResponse)
async def get_blacklist(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """黑名单列表(分页)"""
    result = await risk_control_service.get_blacklist(db, page, page_size)
    return PageResponse(
        data=result["items"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.post("/blacklist", response_model=ResponseModel)
async def add_blacklist(
    req: BlacklistRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """添加黑名单"""
    entry = await risk_control_service.add_to_blacklist(
        db, req.user_uid, req.reason
    )
    return ResponseModel(
        message="已加入黑名单",
        data={
            "id": entry.id,
            "user_uid": entry.user_uid,
            "reason": entry.reason,
        },
    )


@router.delete("/blacklist/{user_uid}", response_model=ResponseModel)
async def remove_blacklist(
    user_uid: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """移出黑名单"""
    removed = await risk_control_service.remove_from_blacklist(db, user_uid)
    if not removed:
        return ResponseModel(code=404, message="该用户不在黑名单中")
    return ResponseModel(message="已移出黑名单", data={"user_uid": user_uid})


# ── 事件记录(webhook回调) ────────────────────────────────────────────────────


@router.post("/report-event", response_model=ResponseModel)
async def report_event(
    req: ReportEventRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """手动记录举报/拉黑等事件(供webhook回调或手动录入)

    事件类型: sent/read/reply/report/block/wechat_added
    如果是 report/block 事件且提供了 user_uid，会自动加入黑名单。
    """
    await risk_control_service.record_event(db, req.event_type, req.count)

    # 举报/拉黑事件自动加入黑名单
    if req.event_type in (EVENT_REPORT, EVENT_BLOCK) and req.user_uid:
        reason = "reported" if req.event_type == EVENT_REPORT else "blacklisted_by_user"
        await risk_control_service.add_to_blacklist(db, req.user_uid, reason)

    return ResponseModel(
        message="事件已记录",
        data={"event_type": req.event_type, "count": req.count},
    )
