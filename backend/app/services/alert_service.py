"""告警服务 — 存入数据库 + 预留WebSocket推送"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert

logger = logging.getLogger(__name__)

# 告警级别
LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_CRITICAL = "critical"

# 告警来源
SOURCE_QUOTA = "quota"
SOURCE_CRAWLER = "crawler"
SOURCE_REPORT = "report"
SOURCE_SYSTEM = "system"

# Redis key for WebSocket notification (预留)
_ALERT_CHANNEL = "alert:notifications"

# 防止重复告警：记录已发送的告警 (source + title 去重, 1小时内不重复)
_ALERT_DEDUP_TTL = 3600  # 1小时


class AlertService:

    @staticmethod
    async def send_alert(
        db: AsyncSession,
        level: str,
        title: str,
        content: str,
        source: str = SOURCE_SYSTEM,
    ) -> Alert | None:
        """发送告警: 存入数据库 + 预留WebSocket推送

        Args:
            db: 异步数据库会话
            level: info / warning / critical
            title: 告警标题
            content: 告警内容
            source: quota / crawler / report / system
        """
        try:
            alert = Alert(
                level=level,
                title=title,
                content=content,
                source=source,
                is_read=False,
            )
            db.add(alert)
            await db.flush()

            logger.info(
                "Alert sent: [%s] %s (source=%s, id=%d)",
                level, title, source, alert.id,
            )

            # 预留: WebSocket推送通知
            # await _push_websocket_notification(alert)

            return alert
        except Exception as exc:
            logger.error("Failed to send alert: %s", exc)
            return None

    @staticmethod
    async def get_alerts(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        level: Optional[str] = None,
        unread_only: bool = False,
    ) -> dict:
        """获取告警列表(分页)"""
        # 构建查询条件
        conditions = []
        if level:
            conditions.append(Alert.level == level)
        if unread_only:
            conditions.append(Alert.is_read == False)  # noqa: E712

        # 查询总数
        count_stmt = select(func.count()).select_from(Alert)
        for cond in conditions:
            count_stmt = count_stmt.where(cond)
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0

        # 查询分页数据
        query = select(Alert).order_by(Alert.created_at.desc())
        for cond in conditions:
            query = query.where(cond)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await db.execute(query)
        alerts = result.scalars().all()

        return {
            "items": [AlertService._alert_to_dict(a) for a in alerts],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def mark_read(db: AsyncSession, alert_id: int) -> bool:
        """标记告警已读"""
        stmt = (
            update(Alert)
            .where(Alert.id == alert_id)
            .values(is_read=True)
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.rowcount > 0

    @staticmethod
    async def mark_all_read(db: AsyncSession) -> int:
        """标记所有未读告警为已读"""
        stmt = (
            update(Alert)
            .where(Alert.is_read == False)  # noqa: E712
            .values(is_read=True)
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.rowcount

    @staticmethod
    async def get_unread_count(db: AsyncSession) -> int:
        """获取未读告警数量"""
        result = await db.execute(
            select(func.count()).select_from(Alert).where(
                Alert.is_read == False  # noqa: E712
            )
        )
        return result.scalar() or 0

    @staticmethod
    def _alert_to_dict(alert: Alert) -> dict:
        """将Alert对象转为字典"""
        return {
            "id": alert.id,
            "level": alert.level,
            "title": alert.title,
            "content": alert.content,
            "source": alert.source,
            "is_read": alert.is_read,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        }
