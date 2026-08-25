"""User service — business logic separated from route handlers."""

from typing import Optional, Tuple

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password, get_password_hash
from app.models.user import User
from app.schemas.user import UserCreate


async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> Optional[User]:
    """Return the user if credentials are valid, else None."""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    """Create a new user and return it."""
    user = User(
        username=data.username,
        password_hash=get_password_hash(data.password),
        role=data.role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_users(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
) -> Tuple[list, int]:
    """Return (list_of_users, total_count) with pagination and optional search."""
    query = select(User)
    count_query = select(sa_func.count()).select_from(User)

    if search:
        like_pattern = f"%{search}%"
        query = query.where(User.username.ilike(like_pattern))
        count_query = count_query.where(User.username.ilike(like_pattern))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    users = list(result.scalars().all())

    return users, total


async def update_user(
    db: AsyncSession, user_id: int, role: Optional[str] = None, status: Optional[str] = None
) -> Optional[User]:
    user = await get_user_by_id(db, user_id)
    if user is None:
        return None
    if role is not None:
        user.role = role
    if status is not None:
        user.status = status
    await db.flush()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    user = await get_user_by_id(db, user_id)
    if user is None:
        return False
    await db.delete(user)
    await db.flush()
    return True


async def reset_user_password(
    db: AsyncSession, user_id: int, new_password: str
) -> Optional[User]:
    user = await get_user_by_id(db, user_id)
    if user is None:
        return None
    user.password_hash = get_password_hash(new_password)
    await db.flush()
    await db.refresh(user)
    return user
