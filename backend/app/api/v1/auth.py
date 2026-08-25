from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, TokenResponse, UserOut
from app.schemas.common import ResponseModel
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=ResponseModel)
async def login(
    body: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """用户登录，返回JWT令牌"""
    user = await user_service.authenticate_user(db, body.username, body.password)
    if user is None:
        return ResponseModel(code=401, message="用户名或密码错误")
    if user.status != "active":
        return ResponseModel(code=403, message="账号已被禁用")

    token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return ResponseModel(
        data={
            "token": token,
            "user": UserOut.model_validate(user).model_dump(),
        }
    )


@router.post("/register", response_model=ResponseModel)
async def register(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """管理员注册新用户（仅admin）"""
    if current_user.role != "admin":
        return ResponseModel(code=403, message="需要管理员权限")

    existing = await user_service.get_user_by_username(db, body.username)
    if existing:
        return ResponseModel(code=400, message="用户名已存在")

    user = await user_service.create_user(db, body)
    return ResponseModel(message="注册成功", data=UserOut.model_validate(user).model_dump())


@router.get("/me", response_model=ResponseModel)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return ResponseModel(data=UserOut.model_validate(current_user).model_dump())


@router.post("/refresh", response_model=ResponseModel)
async def refresh_token(current_user: User = Depends(get_current_user)):
    """刷新令牌"""
    token = create_access_token(data={"sub": str(current_user.id), "role": current_user.role})
    return ResponseModel(data=TokenResponse(access_token=token).model_dump())


@router.post("/logout", response_model=ResponseModel)
async def logout():
    """登出（前端清除token即可，此接口仅做兼容）"""
    return ResponseModel(message="已登出")
