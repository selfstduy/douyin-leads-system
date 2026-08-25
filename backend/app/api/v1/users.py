from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin
from app.schemas.user import UserOut, UserUpdate, PasswordReset
from app.schemas.common import ResponseModel, PageResponse
from app.services import user_service

router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("/", response_model=PageResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="按用户名搜索"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """获取用户列表（分页+搜索）"""
    users, total = await user_service.get_users(
        db, page=page, page_size=page_size, search=search or None
    )
    data = [UserOut.model_validate(u).model_dump() for u in users]
    return PageResponse(data=data, total=total, page=page, page_size=page_size)


@router.get("/{user_id}", response_model=ResponseModel)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """获取用户详情"""
    user = await user_service.get_user_by_id(db, user_id)
    if user is None:
        return ResponseModel(code=404, message="用户不存在")
    return ResponseModel(data=UserOut.model_validate(user).model_dump())


@router.put("/{user_id}", response_model=ResponseModel)
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """修改用户角色/状态"""
    user = await user_service.update_user(db, user_id, role=body.role, status=body.status)
    if user is None:
        return ResponseModel(code=404, message="用户不存在")
    return ResponseModel(message="更新成功", data=UserOut.model_validate(user).model_dump())


@router.delete("/{user_id}", response_model=ResponseModel)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """删除用户"""
    if user_id == current_user.id:
        return ResponseModel(code=400, message="不能删除自己")
    ok = await user_service.delete_user(db, user_id)
    if not ok:
        return ResponseModel(code=404, message="用户不存在")
    return ResponseModel(message="删除成功")


@router.post("/{user_id}/reset-password", response_model=ResponseModel)
async def reset_password(
    user_id: int,
    body: PasswordReset,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """重置用户密码"""
    if len(body.new_password) < 6:
        return ResponseModel(code=400, message="密码长度不能少于6位")
    user = await user_service.reset_user_password(db, user_id, body.new_password)
    if user is None:
        return ResponseModel(code=404, message="用户不存在")
    return ResponseModel(message="密码重置成功")
