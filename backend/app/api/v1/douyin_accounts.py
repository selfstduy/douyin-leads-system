"""Douyin account management API routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user, require_admin
from app.schemas.chat import (
    DouyinAccountCreate,
    DouyinAccountOut,
    DouyinAccountAssign,
    DouyinAccountCookieUpdate,
)
from app.schemas.common import ResponseModel
from app.services import douyin_account_service

router = APIRouter(prefix="/douyin-accounts", tags=["抖音账号管理"])


@router.get("", response_model=ResponseModel)
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get account list. Admin sees all, sales sees only assigned."""
    is_admin = current_user.role == "admin"
    accounts = await douyin_account_service.get_accounts(
        db, user_id=current_user.id, is_admin=is_admin
    )
    return ResponseModel(data=accounts)


@router.post("", response_model=ResponseModel)
async def add_account(
    body: DouyinAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Add a new Douyin chat account (admin only)."""
    account = await douyin_account_service.add_account(
        db,
        douyin_uid=body.douyin_uid,
        nickname=body.nickname,
        cookie_data=body.cookie_data,
    )
    return ResponseModel(message="账号添加成功", data={"id": account.id})


@router.put("/{account_id}/assign", response_model=ResponseModel)
async def assign_account(
    account_id: int,
    body: DouyinAccountAssign,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Assign account to a user (admin only)."""
    success = await douyin_account_service.assign_account(db, account_id, body.user_id)
    if not success:
        raise HTTPException(status_code=400, detail="该用户已达账号绑定上限(10个)")
    return ResponseModel(message="分配成功")


@router.put("/{account_id}/unassign", response_model=ResponseModel)
async def unassign_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Remove account assignment (admin only)."""
    await douyin_account_service.unassign_account(db, account_id)
    return ResponseModel(message="已取消分配")


@router.put("/{account_id}/cookie", response_model=ResponseModel)
async def update_cookie(
    account_id: int,
    body: DouyinAccountCookieUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update cookie for an account."""
    account = await douyin_account_service.get_account_by_id(db, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    # Only admin or assigned user can update cookie
    if current_user.role != "admin" and account.assigned_to_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有权限操作此账号")
    await douyin_account_service.update_cookie(db, account_id, body.cookie_data)
    return ResponseModel(message="Cookie已更新")


@router.get("/{account_id}/status", response_model=ResponseModel)
async def check_status(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Check login status of an account."""
    result = await douyin_account_service.check_login_status(db, account_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="账号不存在")
    return ResponseModel(data=result)


@router.delete("/{account_id}", response_model=ResponseModel)
async def delete_account(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_admin),
):
    """Delete a Douyin chat account (admin only)."""
    success = await douyin_account_service.delete_account(db, account_id)
    if not success:
        raise HTTPException(status_code=404, detail="账号不存在")
    return ResponseModel(message="账号已删除")
