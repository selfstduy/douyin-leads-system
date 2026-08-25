"""系统管理API — 配额监控、告警管理、API日志、参数配置"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user, require_admin
from app.schemas.common import ResponseModel, PageResponse
from app.services.quota_service import QuotaService
from app.services.alert_service import AlertService
from app.services.api_log_service import get_api_logs
from app.services.system_config_service import SystemConfigService

router = APIRouter(prefix="/system", tags=["系统管理"])


# ── Schemas ──────────────────────────────────────────────────────────────────────


class ConfigUpdateRequest(BaseModel):
    value: str


class ConfigBatchItem(BaseModel):
    key: str
    value: str


class ConfigBatchRequest(BaseModel):
    configs: list[ConfigBatchItem]


# ── 配额 ────────────────────────────────────────────────────────────────────────


@router.get("/quotas", response_model=ResponseModel)
async def get_quotas(
    current_user=Depends(get_current_user),
):
    """获取所有API配额使用情况"""
    quotas = await QuotaService.get_all_quotas()
    return ResponseModel(data=quotas)


# ── 告警 ────────────────────────────────────────────────────────────────────────


@router.get("/alerts", response_model=PageResponse)
async def get_alerts(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    level: Optional[str] = Query(None, description="告警级别: info/warning/critical"),
    unread_only: bool = Query(False, description="仅未读"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取告警列表(分页)"""
    result = await AlertService.get_alerts(db, page, page_size, level, unread_only)
    return PageResponse(
        data=result["items"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.put("/alerts/{alert_id}/read", response_model=ResponseModel)
async def mark_alert_read(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """标记告警已读"""
    success = await AlertService.mark_read(db, alert_id)
    if not success:
        return ResponseModel(code=404, message="告警不存在")
    return ResponseModel(data={"id": alert_id, "is_read": True})


@router.put("/alerts/read-all", response_model=ResponseModel)
async def mark_all_alerts_read(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """标记所有告警已读"""
    count = await AlertService.mark_all_read(db)
    return ResponseModel(data={"marked_count": count})


@router.get("/alerts/unread-count", response_model=ResponseModel)
async def get_unread_alert_count(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取未读告警数量"""
    count = await AlertService.get_unread_count(db)
    return ResponseModel(data={"unread_count": count})


# ── API调用日志 ──────────────────────────────────────────────────────────────────


@router.get("/api-logs", response_model=PageResponse)
async def get_api_call_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    api_type: Optional[str] = Query(None, description="API类型: comment_api/video_api/llm_api/openkf_api"),
    success: Optional[bool] = Query(None, description="成功/失败"),
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """查询API调用日志(分页+筛选)"""
    result = await get_api_logs(db, page, page_size, api_type, success, date)
    return PageResponse(
        data=result["items"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


# ── 系统配置 ────────────────────────────────────────────────────────────────────────


@router.get("/configs", response_model=ResponseModel)
async def get_system_configs(
    category: Optional[str] = Query(None, description="分类筛选: quota/dm/risk/crawler/discovery/ai"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取所有系统配置(可按分类筛选)"""
    configs = await SystemConfigService.get_all_configs(db, category)
    return ResponseModel(data=configs)


@router.put("/configs/batch", response_model=ResponseModel)
async def batch_update_system_configs(
    req: ConfigBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """批量更新系统配置(admin only)"""
    items = [{"key": c.key, "value": c.value} for c in req.configs]
    try:
        results = await SystemConfigService.batch_update(db, items, current_user.username)
        return ResponseModel(data={"updated": len(results), "details": results})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/configs/{key}", response_model=ResponseModel)
async def update_system_config(
    key: str,
    req: ConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """更新单个系统配置(admin only)"""
    try:
        result = await SystemConfigService.update_config(db, key, req.value, current_user.username)
        return ResponseModel(data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/config-logs", response_model=PageResponse)
async def get_config_change_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    key: Optional[str] = Query(None, description="配置项key筛选"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取配置变更日志(分页)"""
    result = await SystemConfigService.get_change_logs(db, page, page_size, key)
    return PageResponse(
        data=result["items"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )
