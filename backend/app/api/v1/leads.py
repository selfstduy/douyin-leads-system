from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user, require_admin, async_session_factory
from app.schemas.lead import (
    LeadAssign, BatchAssign, LeadStatusUpdate,
    LeadFollowupCreate, TransferToHuman,
)
from app.schemas.common import ResponseModel, PageResponse
from app.services.intent_service import analyze_single_comment, get_intent_stats
from app.services import lead_service

router = APIRouter(prefix="/leads", tags=["线索管理"])


# ── 静态路由必须放在 /{lead_id} 之前 ────────────────────────────────────────

@router.get("/intent-stats", response_model=ResponseModel)
async def intent_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取意向统计(各级别数量)"""
    stats = await get_intent_stats(db)
    return ResponseModel(data=stats)


@router.post("/reanalyze/{comment_id}", response_model=ResponseModel)
async def reanalyze_comment(
    comment_id: int,
    current_user=Depends(require_admin),
):
    """重新分析单条评论的意向(admin)"""
    # 使用独立session以便在触发AI对话前commit
    async with async_session_factory() as db:
        try:
            result = await analyze_single_comment(db, comment_id)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            raise exc

    if result is None:
        return ResponseModel(code=404, message="评论不存在", data=None)

    # 线索创建后异步触发AI对话（commit已完成）
    if result.get("lead_created") and result.get("lead_id"):
        try:
            from app.tasks.auto_chat_tasks import trigger_ai_conversation
            trigger_ai_conversation.delay(result["lead_id"])
        except Exception:
            pass

    return ResponseModel(data=result)


@router.post("/batch-assign", response_model=ResponseModel)
async def batch_assign(
    body: BatchAssign,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """批量分配线索给销售(admin)"""
    result = await lead_service.batch_assign_leads(
        db, body.lead_ids, body.user_id, current_user.id
    )
    if "error" in result:
        return ResponseModel(code=400, message=result["error"])
    return ResponseModel(data=result, message=f"成功分配 {result['assigned_count']} 条线索")


@router.post("/auto-assign", response_model=ResponseModel)
async def auto_assign(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """自动轮询分配(admin)"""
    result = await lead_service.auto_assign_leads(db, current_user.id)
    if "error" in result and result.get("assigned_count", 0) == 0:
        return ResponseModel(code=400, message=result["error"])
    return ResponseModel(
        data=result,
        message=f"自动分配完成，共分配 {result['assigned_count']} 条线索",
    )


# ── 列表 ────────────────────────────────────────────────────────────────────────

@router.get("/", response_model=PageResponse)
async def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    intent_level: str | None = None,
    status: str | None = None,
    assigned_to: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取线索列表（分页+多条件筛选）"""
    result = await lead_service.get_leads(
        db,
        page=page,
        page_size=page_size,
        intent_level=intent_level,
        status=status,
        assigned_to=assigned_to,
        start_date=start_date,
        end_date=end_date,
        search=search,
        current_user=current_user,
    )
    return PageResponse(
        data=result["data"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


# ── 动态路由 ──────────────────────────────────────────────────────────────────

@router.get("/{lead_id}", response_model=ResponseModel)
async def get_lead(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取线索详情(含评论、视频、跟进记录)"""
    detail = await lead_service.get_lead_detail(db, lead_id)
    if detail is None:
        return ResponseModel(code=404, message="线索不存在")
    return ResponseModel(data=detail)


@router.post("/{lead_id}/assign", response_model=ResponseModel)
async def assign_lead(
    lead_id: int,
    body: LeadAssign,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """分配线索给销售(admin)"""
    result = await lead_service.assign_lead(db, lead_id, body.user_id, current_user.id)
    if result is None:
        return ResponseModel(code=404, message="线索不存在")
    if "error" in result:
        return ResponseModel(code=400, message=result["error"])
    return ResponseModel(data=result, message="分配成功")


@router.put("/{lead_id}/status", response_model=ResponseModel)
async def update_lead_status(
    lead_id: int,
    body: LeadStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """更新线索状态"""
    is_admin = current_user.role == "admin"
    result = await lead_service.update_lead_status(
        db, lead_id, body.status, current_user.id, is_admin=is_admin
    )
    if result is None:
        return ResponseModel(code=404, message="线索不存在")
    if "error" in result:
        return ResponseModel(code=400, message=result["error"])
    return ResponseModel(data=result, message="状态已更新")


@router.post("/{lead_id}/followup", response_model=ResponseModel)
async def create_followup(
    lead_id: int,
    body: LeadFollowupCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """添加跟进记录"""
    result = await lead_service.add_followup(
        db, lead_id, current_user.id, action=body.action, content=body.content
    )
    if result is None:
        return ResponseModel(code=404, message="线索不存在")
    return ResponseModel(data=result, message="跟进已添加")


@router.get("/{lead_id}/followups", response_model=ResponseModel)
async def get_followups(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取跟进历史"""
    followups = await lead_service.get_followups(db, lead_id)
    return ResponseModel(data=followups)


@router.post("/{lead_id}/transfer-to-human", response_model=ResponseModel)
async def transfer_to_human(
    lead_id: int,
    body: TransferToHuman,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """将线索转为人工服务"""
    result = await lead_service.transfer_to_human(
        db, lead_id, body.sales_user_id, current_user.id
    )
    if result is None:
        return ResponseModel(code=404, message="线索不存在")
    if "error" in result:
        return ResponseModel(code=400, message=result["error"])
    return ResponseModel(data=result, message="已转为人工服务")


@router.post("/{lead_id}/mark-invalid", response_model=ResponseModel)
async def mark_invalid(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """将线索标记为无效"""
    result = await lead_service.mark_as_invalid(db, lead_id, current_user.id)
    if result is None:
        return ResponseModel(code=404, message="线索不存在")
    return ResponseModel(data=result, message="已标记为无效")
