from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user, require_admin
from app.schemas.monitor import MonitorAccountCreate, MonitorAccountUpdate, MonitorAccountOut
from app.schemas.common import ResponseModel, PageResponse
from app.services import monitor_service
from app.services.account_discovery_service import AccountDiscoveryService

router = APIRouter(prefix="/monitors", tags=["监控账号"])


@router.get("/", response_model=PageResponse)
async def list_monitors(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取监控账号列表（分页+筛选状态+搜索昵称）"""
    monitors, total = await monitor_service.get_monitors(
        db, page=page, page_size=page_size, status_filter=status_filter, search=search
    )
    data = [MonitorAccountOut.model_validate(m).model_dump() for m in monitors]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.post("/", response_model=ResponseModel)
async def create_monitor(
    body: MonitorAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """创建监控账号"""
    # Parse UID to check for duplicates
    uid, _ = monitor_service.parse_douyin_url(body.douyin_url)
    existing = await monitor_service.get_monitor_by_uid(db, uid)
    if existing and existing.status != 'deleted':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"抖音UID {uid} 已存在",
        )
    monitor = await monitor_service.create_monitor(db, body, created_by=current_user.id)
    return ResponseModel(
        message="创建成功",
        data=MonitorAccountOut.model_validate(monitor).model_dump(),
    )


@router.post("/batch-import", response_model=ResponseModel)
async def batch_import(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """批量导入监控账号（CSV/Excel）"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="请上传文件")
    allowed = ('.csv', '.xlsx', '.xls')
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(status_code=400, detail="仅支持 .csv 和 .xlsx 格式")

    content = await file.read()
    result = await monitor_service.batch_import(db, content, file.filename, created_by=current_user.id)
    return ResponseModel(
        message=f"导入完成：成功 {result.success_count}，失败 {result.fail_count}",
        data=result.model_dump(),
    )


@router.post("/run-discovery", response_model=ResponseModel)
async def run_discovery(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """手动触发全网账号发现（异步执行，不阻塞）"""
    from app.tasks.discovery_tasks import daily_account_discovery

    task = daily_account_discovery.delay()
    return ResponseModel(
        message="全网发现任务已提交，将在后台异步执行",
        data={"task_id": task.id},
    )


@router.post("/run-cleaning", response_model=ResponseModel)
async def run_cleaning(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """手动触发低质账号清洗"""
    from app.tasks.discovery_tasks import weekly_account_cleaning

    task = weekly_account_cleaning.delay()
    return ResponseModel(
        message="账号清洗任务已提交，将在后台异步执行",
        data={"task_id": task.id},
    )


@router.get("/discovery-stats", response_model=ResponseModel)
async def get_discovery_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取全网发现统计"""
    service = AccountDiscoveryService()
    stats = await service.get_discovery_stats(db)
    return ResponseModel(data=stats)


@router.get("/removed", response_model=PageResponse)
async def list_removed_monitors(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取被移出的账号列表（支持恢复）"""
    monitors, total = await monitor_service.get_removed_monitors(
        db, page=page, page_size=page_size, search=search
    )
    data = [MonitorAccountOut.model_validate(m).model_dump() for m in monitors]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.get("/{monitor_id}", response_model=ResponseModel)
async def get_monitor(
    monitor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取监控账号详情"""
    monitor = await monitor_service.get_monitor_by_id(db, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="监控账号不存在")
    return ResponseModel(data=MonitorAccountOut.model_validate(monitor).model_dump())


@router.put("/{monitor_id}", response_model=ResponseModel)
async def update_monitor(
    monitor_id: int,
    body: MonitorAccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """更新监控账号"""
    monitor = await monitor_service.update_monitor(db, monitor_id, body)
    if monitor is None:
        raise HTTPException(status_code=404, detail="监控账号不存在")
    return ResponseModel(
        message="更新成功",
        data=MonitorAccountOut.model_validate(monitor).model_dump(),
    )


@router.delete("/{monitor_id}", response_model=ResponseModel)
async def delete_monitor(
    monitor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """删除监控账号（软删除）"""
    deleted = await monitor_service.delete_monitor(db, monitor_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="监控账号不存在")
    return ResponseModel(message="删除成功")


@router.post("/{monitor_id}/toggle", response_model=ResponseModel)
async def toggle_monitor(
    monitor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """启停切换监控账号"""
    monitor = await monitor_service.toggle_status(db, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="监控账号不存在")
    return ResponseModel(
        message="操作成功",
        data=MonitorAccountOut.model_validate(monitor).model_dump(),
    )


@router.post("/{monitor_id}/restore", response_model=ResponseModel)
async def restore_monitor(
    monitor_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """恢复被移出的账号"""
    monitor = await monitor_service.restore_monitor(db, monitor_id)
    if monitor is None:
        raise HTTPException(status_code=404, detail="账号不存在或未被移出")
    return ResponseModel(
        message="账号已恢复",
        data=MonitorAccountOut.model_validate(monitor).model_dump(),
    )
