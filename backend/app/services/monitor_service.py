"""Monitor service — business logic for Douyin account monitoring."""

import io
import re
from typing import Optional, Tuple, List

from sqlalchemy import select, func as sa_func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitor import MonitorAccount
from app.schemas.monitor import MonitorAccountCreate, MonitorAccountUpdate, BatchImportResult


def parse_douyin_url(url: str) -> Tuple[str, str]:
    """Parse a Douyin URL and return (douyin_uid, original_url).

    Supported formats:
    - https://www.douyin.com/user/MS4wLjABAAAA...
    - https://v.douyin.com/xxxxx/
    - Direct UID string

    Returns (uid, stored_url).
    """
    url = url.strip()

    # Match /user/XXXX pattern
    user_match = re.search(r'/user/([A-Za-z0-9_\-]+)', url)
    if user_match:
        return user_match.group(1), url

    # Short link pattern — keep original URL, use last path segment as uid
    if 'v.douyin.com' in url or 'douyin.com' in url:
        # Extract last meaningful path segment
        cleaned = url.rstrip('/')
        parts = cleaned.split('/')
        uid = parts[-1] if parts else url
        return uid, url

    # Direct UID
    return url, url


async def create_monitor(
    db: AsyncSession, data: MonitorAccountCreate, created_by: Optional[int] = None
) -> MonitorAccount:
    """Create a new monitor account from a Douyin URL."""
    uid, stored_url = parse_douyin_url(data.douyin_url)

    monitor = MonitorAccount(
        douyin_url=stored_url,
        douyin_uid=uid,
        nickname="",
        poll_interval_min=data.poll_interval_min,
        created_by=created_by,
    )
    db.add(monitor)
    await db.flush()
    await db.refresh(monitor)
    return monitor


async def get_monitor_by_id(db: AsyncSession, monitor_id: int) -> Optional[MonitorAccount]:
    result = await db.execute(
        select(MonitorAccount).where(MonitorAccount.id == monitor_id)
    )
    return result.scalar_one_or_none()


async def get_monitor_by_uid(db: AsyncSession, uid: str) -> Optional[MonitorAccount]:
    result = await db.execute(
        select(MonitorAccount).where(MonitorAccount.douyin_uid == uid)
    )
    return result.scalar_one_or_none()


async def get_monitors(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
) -> Tuple[list, int]:
    """Return (list_of_monitors, total_count) with pagination and filters."""
    query = select(MonitorAccount).where(
        MonitorAccount.status.notin_(['deleted', 'removed'])
    )
    count_query = select(sa_func.count()).select_from(MonitorAccount).where(
        MonitorAccount.status.notin_(['deleted', 'removed'])
    )

    if status_filter:
        query = query.where(MonitorAccount.status == status_filter)
        count_query = count_query.where(MonitorAccount.status == status_filter)

    if search:
        like_pattern = f"%{search}%"
        query = query.where(
            or_(
                MonitorAccount.nickname.ilike(like_pattern),
                MonitorAccount.douyin_uid.ilike(like_pattern),
            )
        )
        count_query = count_query.where(
            or_(
                MonitorAccount.nickname.ilike(like_pattern),
                MonitorAccount.douyin_uid.ilike(like_pattern),
            )
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(MonitorAccount.id.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    monitors = list(result.scalars().all())

    return monitors, total


async def update_monitor(
    db: AsyncSession, monitor_id: int, data: MonitorAccountUpdate
) -> Optional[MonitorAccount]:
    monitor = await get_monitor_by_id(db, monitor_id)
    if monitor is None or monitor.status == 'deleted':
        return None
    if data.nickname is not None:
        monitor.nickname = data.nickname
    if data.status is not None:
        monitor.status = data.status
    if data.poll_interval_min is not None:
        monitor.poll_interval_min = data.poll_interval_min
    await db.flush()
    await db.refresh(monitor)
    return monitor


async def delete_monitor(db: AsyncSession, monitor_id: int) -> bool:
    """Soft delete by setting status to 'deleted'."""
    monitor = await get_monitor_by_id(db, monitor_id)
    if monitor is None:
        return False
    monitor.status = 'deleted'
    await db.flush()
    return True


async def toggle_status(db: AsyncSession, monitor_id: int) -> Optional[MonitorAccount]:
    """Toggle between active and paused."""
    monitor = await get_monitor_by_id(db, monitor_id)
    if monitor is None or monitor.status == 'deleted':
        return None
    monitor.status = 'paused' if monitor.status == 'active' else 'active'
    await db.flush()
    await db.refresh(monitor)
    return monitor


async def get_removed_monitors(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
) -> Tuple[list, int]:
    """Return (list_of_removed_monitors, total_count) with pagination."""
    query = select(MonitorAccount).where(MonitorAccount.status == 'removed')
    count_query = select(sa_func.count()).select_from(MonitorAccount).where(
        MonitorAccount.status == 'removed'
    )

    if search:
        like_pattern = f"%{search}%"
        query = query.where(
            or_(
                MonitorAccount.nickname.ilike(like_pattern),
                MonitorAccount.douyin_uid.ilike(like_pattern),
            )
        )
        count_query = count_query.where(
            or_(
                MonitorAccount.nickname.ilike(like_pattern),
                MonitorAccount.douyin_uid.ilike(like_pattern),
            )
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(MonitorAccount.id.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    monitors = list(result.scalars().all())

    return monitors, total


async def restore_monitor(db: AsyncSession, monitor_id: int) -> Optional[MonitorAccount]:
    """恢复被移出的账号（将status从removed改回active）"""
    monitor = await get_monitor_by_id(db, monitor_id)
    if monitor is None or monitor.status != 'removed':
        return None
    monitor.status = 'active'
    await db.flush()
    await db.refresh(monitor)
    return monitor


async def batch_import(
    db: AsyncSession, file_content: bytes, filename: str, created_by: Optional[int] = None
) -> BatchImportResult:
    """Parse CSV or Excel file and batch import monitor accounts."""
    result = BatchImportResult()
    urls: List[str] = []

    if filename.endswith('.csv'):
        text = file_content.decode('utf-8-sig')
        for line in text.splitlines():
            line = line.strip()
            if line:
                # Take the first column if CSV has multiple columns
                urls.append(line.split(',')[0].strip())
    elif filename.endswith('.xlsx') or filename.endswith('.xls'):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=1, max_col=1, values_only=True):
            val = row[0]
            if val and str(val).strip():
                urls.append(str(val).strip())
        wb.close()
    else:
        result.errors.append("不支持的文件格式，仅支持 .csv 和 .xlsx")
        return result

    for url in urls:
        try:
            uid, stored_url = parse_douyin_url(url)
            # Check for duplicate
            existing = await get_monitor_by_uid(db, uid)
            if existing:
                if existing.status == 'deleted':
                    existing.status = 'active'
                    result.success_count += 1
                else:
                    result.fail_count += 1
                    result.errors.append(f"UID {uid} 已存在")
                continue

            monitor = MonitorAccount(
                douyin_url=stored_url,
                douyin_uid=uid,
                nickname="",
                poll_interval_min=5,
                created_by=created_by,
            )
            db.add(monitor)
            await db.flush()
            result.success_count += 1
        except Exception as e:
            result.fail_count += 1
            result.errors.append(f"导入 {url} 失败: {str(e)}")

    return result
