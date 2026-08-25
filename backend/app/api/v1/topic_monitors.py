from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user, require_admin
from app.schemas.topic_monitor import TopicMonitorCreate, TopicMonitorUpdate, TopicMonitorOut
from app.schemas.common import ResponseModel, PageResponse
from app.services import topic_monitor_service

router = APIRouter(prefix="/topic-monitors", tags=["话题监控"])


@router.get("/", response_model=PageResponse)
async def list_topic_monitors(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取话题监控列表（分页+筛选状态+搜索话题）"""
    monitors, total = await topic_monitor_service.get_topic_monitors(
        db, page=page, page_size=page_size, status_filter=status_filter, search=search
    )
    data = [TopicMonitorOut.model_validate(m).model_dump() for m in monitors]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("/", response_model=ResponseModel)
async def create_topic_monitor(
    body: TopicMonitorCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """创建话题监控"""
    monitor = await topic_monitor_service.create_topic_monitor(
        db, body, created_by=current_user.id
    )
    return ResponseModel(
        message="创建成功",
        data=TopicMonitorOut.model_validate(monitor).model_dump(),
    )


@router.put("/{monitor_id}", response_model=ResponseModel)
async def update_topic_monitor(
    monitor_id: int,
    body: TopicMonitorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """更新话题监控"""
    monitor = await topic_monitor_service.update_topic_monitor(db, monitor_id, body)
    if monitor is None:
        raise HTTPException(status_code=404, detail="话题监控不存在")
    return ResponseModel(
        message="更新成功",
        data=TopicMonitorOut.model_validate(monitor).model_dump(),
    )


@router.delete("/{monitor_id}", response_model=ResponseModel)
async def delete_topic_monitor(
    monitor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """删除话题监控"""
    deleted = await topic_monitor_service.delete_topic_monitor(db, monitor_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="话题监控不存在")
    return ResponseModel(message="删除成功")


@router.post("/{monitor_id}/toggle", response_model=ResponseModel)
async def toggle_topic_monitor(
    monitor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """启停切换话题监控"""
    monitor = await topic_monitor_service.toggle_topic_monitor(db, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="话题监控不存在")
    return ResponseModel(
        message="操作成功",
        data=TopicMonitorOut.model_validate(monitor).model_dump(),
    )
