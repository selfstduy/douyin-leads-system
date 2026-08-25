"""私信队列API — 队列统计、列表、暂停/恢复。"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.schemas.common import ResponseModel, PageResponse
from app.services.dm_queue_service import dm_queue_service

router = APIRouter(prefix="/dm-queue", tags=["私信队列"])


@router.get("/stats", response_model=ResponseModel)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """队列统计：待发送、今日已发、溢出待明日"""
    stats = await dm_queue_service.get_queue_stats(db)
    return ResponseModel(data=stats)


@router.get("/list", response_model=PageResponse)
async def get_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    status: Optional[str] = Query(
        None, description="状态筛选: pending/sent/failed/skipped/overflow"
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """队列列表(分页，状态筛选)"""
    result = await dm_queue_service.get_queue_list(db, page, page_size, status)
    return PageResponse(
        data=result["items"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.post("/pause", response_model=ResponseModel)
async def pause_queue(
    current_user=Depends(get_current_user),
):
    """暂停队列发送"""
    await dm_queue_service.pause()
    return ResponseModel(message="队列已暂停", data={"paused": True})


@router.post("/resume", response_model=ResponseModel)
async def resume_queue(
    current_user=Depends(get_current_user),
):
    """恢复队列发送"""
    await dm_queue_service.resume()
    return ResponseModel(message="队列已恢复", data={"paused": False})
