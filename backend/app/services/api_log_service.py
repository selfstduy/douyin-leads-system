"""API调用日志服务 — 异步写入, 不阻塞主流程"""
import json
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import async_session_factory
from app.models.api_log import ApiCallLog

logger = logging.getLogger(__name__)


async def log_api_call(
    api_type: str,
    endpoint: str,
    params: dict | str | None,
    status_code: int,
    response_time_ms: int,
    success: bool,
    error: str | None = None,
):
    """记录API调用日志 — 异步写入, 不阻塞主流程。

    使用独立的db session, 内部commit, 即使主流程回滚也不影响日志。
    """
    async def _write():
        async with async_session_factory() as db:
            try:
                # params统一转为JSON字符串
                if params is None:
                    params_str = ""
                elif isinstance(params, str):
                    params_str = params
                else:
                    params_str = json.dumps(params, ensure_ascii=False, default=str)

                log = ApiCallLog(
                    api_type=api_type,
                    endpoint=endpoint[:512],  # 截断防超长
                    params=params_str,
                    status_code=status_code,
                    response_time_ms=response_time_ms,
                    success=success,
                    error_message=error[:10000] if error else None,
                )
                db.add(log)
                await db.commit()
            except Exception as exc:
                logger.error("Failed to write api log: %s", exc)
                await db.rollback()

    # 用 fire-and-forget 模式启动独立任务
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_write())
    except RuntimeError:
        # 无event loop时直接执行
        await _write()


async def get_api_logs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    api_type: Optional[str] = None,
    success: Optional[bool] = None,
    date: Optional[str] = None,
) -> dict:
    """查询API调用日志(分页+筛选)

    Args:
        api_type: 按API类型筛选(comment_api/video_api/llm_api/openkf_api)
        success: 按成功/失败筛选
        date: 按日期筛选(YYYY-MM-DD, 使用CST时区)
    """
    conditions = []
    if api_type:
        conditions.append(ApiCallLog.api_type == api_type)
    if success is not None:
        conditions.append(ApiCallLog.success == success)
    if date:
        try:
            d = datetime.fromisoformat(date)
            # CST当天0点到次日0点
            start = d.replace(hour=0, minute=0, second=0, microsecond=0)
            end = d.replace(hour=23, minute=59, second=59, microsecond=999999)
            conditions.append(ApiCallLog.created_at >= start)
            conditions.append(ApiCallLog.created_at <= end)
        except (ValueError, TypeError):
            pass

    # 查询总数
    count_stmt = select(func.count()).select_from(ApiCallLog)
    for cond in conditions:
        count_stmt = count_stmt.where(cond)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # 查询分页数据
    query = select(ApiCallLog).order_by(ApiCallLog.created_at.desc())
    for cond in conditions:
        query = query.where(cond)
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "items": [_log_to_dict(l) for l in logs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _log_to_dict(log: ApiCallLog) -> dict:
    """将ApiCallLog对象转为字典"""
    return {
        "id": log.id,
        "api_type": log.api_type,
        "endpoint": log.endpoint,
        "params": log.params,
        "status_code": log.status_code,
        "response_time_ms": log.response_time_ms,
        "success": log.success,
        "error_message": log.error_message,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }
