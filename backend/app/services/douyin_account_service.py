"""Douyin chat account management service."""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitor import DouyinChatAccount
from app.models.user import User
from app.core.config import settings
from app.services.douyin_automation import automation


async def add_account(
    db: AsyncSession,
    douyin_uid: str,
    nickname: str,
    cookie_data: str,
    assigned_to: Optional[int] = None,
) -> DouyinChatAccount:
    """Add a new Douyin chat account."""
    account = DouyinChatAccount(
        douyin_uid=douyin_uid,
        nickname=nickname,
        cookie_data=cookie_data,
        assigned_to_user_id=assigned_to,
        login_status="offline",
    )
    db.add(account)
    await db.flush()
    return account


async def get_accounts(
    db: AsyncSession,
    user_id: Optional[int] = None,
    is_admin: bool = False,
) -> List[dict]:
    """Get account list. Admin sees all, sales sees only assigned."""
    stmt = select(DouyinChatAccount, User.username).outerjoin(
        User, User.id == DouyinChatAccount.assigned_to_user_id
    )
    if not is_admin and user_id is not None:
        stmt = stmt.where(DouyinChatAccount.assigned_to_user_id == user_id)
    stmt = stmt.order_by(DouyinChatAccount.id.desc())

    result = await db.execute(stmt)
    rows = result.all()

    accounts = []
    for account, username in rows:
        accounts.append({
            "id": account.id,
            "douyin_uid": account.douyin_uid,
            "nickname": account.nickname,
            "login_status": account.login_status,
            "assigned_to_user_id": account.assigned_to_user_id,
            "assigned_to_username": username,
            "last_active_at": account.last_active_at,
            "created_at": account.created_at,
        })
    return accounts


async def get_account_by_id(db: AsyncSession, account_id: int) -> Optional[DouyinChatAccount]:
    result = await db.execute(
        select(DouyinChatAccount).where(DouyinChatAccount.id == account_id)
    )
    return result.scalar_one_or_none()


async def assign_account(db: AsyncSession, account_id: int, user_id: int) -> bool:
    """Assign account to a user, respecting the per-user limit."""
    # Check per-user limit
    count = await get_user_account_count(db, user_id)
    if count >= settings.MAX_ACCOUNTS_PER_USER:
        return False

    await db.execute(
        update(DouyinChatAccount)
        .where(DouyinChatAccount.id == account_id)
        .values(assigned_to_user_id=user_id)
    )
    await db.flush()
    return True


async def unassign_account(db: AsyncSession, account_id: int) -> None:
    """Remove account assignment."""
    await db.execute(
        update(DouyinChatAccount)
        .where(DouyinChatAccount.id == account_id)
        .values(assigned_to_user_id=None)
    )
    await db.flush()


async def update_cookie(db: AsyncSession, account_id: int, cookie_data: str) -> None:
    """Update cookie data for an account."""
    await db.execute(
        update(DouyinChatAccount)
        .where(DouyinChatAccount.id == account_id)
        .values(cookie_data=cookie_data, login_status="offline")
    )
    await db.flush()


async def check_login_status(db: AsyncSession, account_id: int) -> dict:
    """Check login validity via automation and update status."""
    account = await get_account_by_id(db, account_id)
    if not account:
        return {"status": "not_found"}

    is_valid = await automation.check_session_valid(account.cookie_data)
    new_status = "online" if is_valid else "expired"
    account.login_status = new_status
    account.last_active_at = datetime.now(timezone.utc)
    await db.flush()

    return {"status": new_status, "douyin_uid": account.douyin_uid}


async def get_user_account_count(db: AsyncSession, user_id: int) -> int:
    """Get number of accounts assigned to a user."""
    result = await db.execute(
        select(func.count(DouyinChatAccount.id)).where(
            DouyinChatAccount.assigned_to_user_id == user_id
        )
    )
    return result.scalar() or 0


async def delete_account(db: AsyncSession, account_id: int) -> bool:
    """Delete an account."""
    result = await db.execute(
        delete(DouyinChatAccount).where(DouyinChatAccount.id == account_id)
    )
    await db.flush()
    return result.rowcount > 0


async def get_user_available_accounts(db: AsyncSession, user_id: int) -> List[DouyinChatAccount]:
    """Get accounts available for a user to send messages."""
    result = await db.execute(
        select(DouyinChatAccount).where(
            DouyinChatAccount.assigned_to_user_id == user_id,
            DouyinChatAccount.login_status != "expired",
        )
    )
    return list(result.scalars().all())
