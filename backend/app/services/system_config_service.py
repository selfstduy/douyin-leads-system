"""系统参数配置服务 — 动态配置管理、Redis缓存、变更日志"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import redis.asyncio as aioredis
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.system_config import SystemConfig, ConfigChangeLog

logger = logging.getLogger(__name__)

# Redis缓存key前缀与TTL
_CONFIG_CACHE_PREFIX = "config:"
_CONFIG_CACHE_TTL = 300  # 5分钟

# ── 默认配置清单 ────────────────────────────────────────────────────────────────

DEFAULT_CONFIGS: list[dict] = [
    # 配额类 (quota)
    {"key": "daily_max_comment_requests", "value": "60000", "value_type": "int", "category": "quota",
     "label": "评论接口每日请求上限", "description": "评论API每日最大请求次数"},
    {"key": "daily_max_video_requests", "value": "20000", "value_type": "int", "category": "quota",
     "label": "作品接口每日请求上限", "description": "作品API每日最大请求次数"},

    # 私信类 (dm)
    {"key": "dm_daily_global_limit", "value": "5000", "value_type": "int", "category": "dm",
     "label": "私信每日全局上限", "description": "所有账号每日私信总发送上限"},
    {"key": "dm_daily_safe_limit", "value": "4000", "value_type": "int", "category": "dm",
     "label": "私信每日安全线", "description": "私信每日安全运行线，预留20%缓冲"},
    {"key": "dm_account_daily_limit", "value": "100", "value_type": "int", "category": "dm",
     "label": "单账号每日私信上限", "description": "单个抖音账号每日私信发送上限"},
    {"key": "dm_send_window_start", "value": "8", "value_type": "int", "category": "dm",
     "label": "发送窗口开始(时)", "description": "每日私信发送窗口开始时间（24小时制）"},
    {"key": "dm_send_window_end", "value": "23", "value_type": "int", "category": "dm",
     "label": "发送窗口结束(时)", "description": "每日私信发送窗口结束时间（24小时制）"},
    {"key": "dm_user_dedup_days", "value": "7", "value_type": "int", "category": "dm",
     "label": "同一用户去重天数", "description": "同一用户在N天内不重复发送私信"},
    {"key": "dm_min_interval_sec", "value": "3", "value_type": "int", "category": "dm",
     "label": "最小发送间隔(秒)", "description": "两条私信之间最小间隔秒数"},
    {"key": "dm_max_interval_sec", "value": "8", "value_type": "int", "category": "dm",
     "label": "最大发送间隔(秒)", "description": "两条私信之间最大间隔秒数"},

    # 风控类 (risk)
    {"key": "report_rate_warning", "value": "0.007", "value_type": "float", "category": "risk",
     "label": "举报预警阈值", "description": "举报拉黑率达到此值时触发预警并降量"},
    {"key": "report_rate_critical", "value": "0.01", "value_type": "float", "category": "risk",
     "label": "举报熔断阈值", "description": "举报拉黑率达到此值时暂停私信发送"},
    {"key": "dm_throttle_ratio", "value": "0.5", "value_type": "float", "category": "risk",
     "label": "降量比例", "description": "触发风控预警后私信发送量降低的比例"},

    # 采集类 (crawler)
    {"key": "video_lifecycle_days", "value": "14", "value_type": "int", "category": "crawler",
     "label": "视频生命周期(天)", "description": "视频超过N天后停止轮询评论"},
    {"key": "high_heat_poll_interval", "value": "10", "value_type": "int", "category": "crawler",
     "label": "高热视频轮询间隔(分钟)", "description": "高热视频每隔N分钟轮询一次新评论"},
    {"key": "normal_poll_interval", "value": "20", "value_type": "int", "category": "crawler",
     "label": "普通视频轮询间隔(分钟)", "description": "普通视频每隔N分钟轮询一次新评论"},
    {"key": "high_heat_threshold", "value": "200", "value_type": "int", "category": "crawler",
     "label": "高热评论阈值", "description": "视频评论数达到此值视为高热视频"},
    {"key": "account_sync_interval_hours", "value": "6", "value_type": "int", "category": "crawler",
     "label": "账号同步间隔(小时)", "description": "账号作品列表同步间隔小时数"},
    {"key": "degradation_streak_double", "value": "3", "value_type": "int", "category": "crawler",
     "label": "降级翻倍阈值(次)", "description": "连续N次无新评论时，轮询间隔翻倍"},
    {"key": "degradation_streak_pause", "value": "6", "value_type": "int", "category": "crawler",
     "label": "降级暂停阈值(次)", "description": "连续N次无新评论时，暂停轮询该视频"},

    # 发现类 (discovery)
    {"key": "account_pool_max", "value": "1000", "value_type": "int", "category": "discovery",
     "label": "监控池上限", "description": "监控账号池最大容量"},
    {"key": "account_clean_days", "value": "14", "value_type": "int", "category": "discovery",
     "label": "低质清洗天数", "description": "N天内无高热评论的账号视为低质并清洗"},
    {"key": "discovery_max_pages", "value": "300", "value_type": "int", "category": "discovery",
     "label": "全网检索最大分页", "description": "全网账号检索时最大翻页数"},
    {"key": "discovery_high_threshold", "value": "30", "value_type": "int", "category": "discovery",
     "label": "新账号入选阈值", "description": "新发现账号需要≥N条高热评论才能入选监控池"},

    # AI类 (ai)
    {"key": "ai_max_rounds", "value": "5", "value_type": "int", "category": "ai",
     "label": "AI对话最大轮次", "description": "AI自动对话最大轮次，超过后强制转人工"},
    {"key": "llm_model", "value": "qwen-plus", "value_type": "str", "category": "ai",
     "label": "AI模型名称", "description": "调用LLM使用的模型名称"},
]


async def _get_redis() -> aioredis.Redis:
    """获取Redis连接"""
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _convert_value(raw: str, value_type: str) -> Any:
    """将字符串配置值按类型转换"""
    if value_type == "int":
        return int(raw)
    elif value_type == "float":
        return float(raw)
    elif value_type == "bool":
        return raw.lower() in ("true", "1", "yes")
    elif value_type == "json":
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw  # str


class SystemConfigService:

    @staticmethod
    async def get_all_configs(db: AsyncSession, category: Optional[str] = None) -> list[dict]:
        """获取所有配置(可按分类筛选)"""
        stmt = select(SystemConfig).order_by(SystemConfig.category, SystemConfig.key)
        if category:
            stmt = stmt.where(SystemConfig.category == category)
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "id": r.id,
                "key": r.key,
                "value": r.value,
                "value_type": r.value_type,
                "category": r.category,
                "label": r.label,
                "description": r.description,
                "updated_by": r.updated_by,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]

    @staticmethod
    async def get_config(db: AsyncSession, key: str) -> Any:
        """获取单个配置值(带类型转换)，优先读Redis缓存"""
        # 先查Redis缓存
        try:
            redis = await _get_redis()
            cached = await redis.get(f"{_CONFIG_CACHE_PREFIX}{key}")
            if cached is not None:
                # 缓存存的是JSON: {"value": "...", "type": "..."}
                data = json.loads(cached)
                await redis.close()
                return _convert_value(data["value"], data["type"])
            await redis.close()
        except Exception as exc:
            logger.warning("Redis cache read failed for key=%s: %s", key, exc)

        # 缓存未命中，查DB
        stmt = select(SystemConfig).where(SystemConfig.key == key)
        result = await db.execute(stmt)
        cfg = result.scalar_one_or_none()
        if cfg is None:
            return None

        # 写入Redis缓存
        try:
            redis = await _get_redis()
            await redis.setex(
                f"{_CONFIG_CACHE_PREFIX}{key}",
                _CONFIG_CACHE_TTL,
                json.dumps({"value": cfg.value, "type": cfg.value_type}),
            )
            await redis.close()
        except Exception as exc:
            logger.warning("Redis cache write failed for key=%s: %s", key, exc)

        return _convert_value(cfg.value, cfg.value_type)

    @staticmethod
    async def update_config(db: AsyncSession, key: str, value: str, username: str) -> dict:
        """更新配置 + 记录变更日志 + 清除Redis缓存"""
        stmt = select(SystemConfig).where(SystemConfig.key == key)
        result = await db.execute(stmt)
        cfg = result.scalar_one_or_none()
        if cfg is None:
            raise ValueError(f"配置项 '{key}' 不存在")

        old_value = cfg.value

        # 类型校验
        if cfg.value_type == "int":
            int(value)
        elif cfg.value_type == "float":
            float(value)
        elif cfg.value_type == "bool":
            if value.lower() not in ("true", "false", "1", "0", "yes", "no"):
                raise ValueError(f"布尔类型配置项只接受 true/false/1/0/yes/no")

        # 更新DB
        cfg.value = value
        cfg.updated_by = username
        cfg.updated_at = datetime.now(timezone.utc)

        # 记录变更日志
        if old_value != value:
            log = ConfigChangeLog(
                config_key=key,
                old_value=old_value,
                new_value=value,
                changed_by=username,
            )
            db.add(log)

        # 清除Redis缓存(即时生效)
        try:
            redis = await _get_redis()
            await redis.delete(f"{_CONFIG_CACHE_PREFIX}{key}")
            await redis.close()
        except Exception as exc:
            logger.warning("Redis cache delete failed for key=%s: %s", key, exc)

        return {"key": key, "old_value": old_value, "new_value": value}

    @staticmethod
    async def batch_update(db: AsyncSession, configs: list[dict], username: str) -> list[dict]:
        """批量更新配置"""
        results = []
        for item in configs:
            key = item.get("key")
            value = item.get("value")
            if not key or value is None:
                continue
            r = await SystemConfigService.update_config(db, key, str(value), username)
            results.append(r)
        return results

    @staticmethod
    async def get_change_logs(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 20,
        key: Optional[str] = None,
    ) -> dict:
        """获取变更日志(分页)"""
        base = select(ConfigChangeLog)
        count_base = select(sa_func.count(ConfigChangeLog.id))
        if key:
            base = base.where(ConfigChangeLog.config_key == key)
            count_base = count_base.where(ConfigChangeLog.config_key == key)

        # 总数
        total_result = await db.execute(count_base)
        total = total_result.scalar() or 0

        # 分页查询
        stmt = base.order_by(ConfigChangeLog.changed_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(stmt)
        rows = result.scalars().all()

        return {
            "items": [
                {
                    "id": r.id,
                    "config_key": r.config_key,
                    "old_value": r.old_value,
                    "new_value": r.new_value,
                    "changed_by": r.changed_by,
                    "changed_at": r.changed_at.isoformat() if r.changed_at else None,
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def init_default_configs(db: AsyncSession) -> int:
        """初始化默认配置(首次启动时)，已存在的不覆盖"""
        inserted = 0
        for item in DEFAULT_CONFIGS:
            stmt = select(SystemConfig).where(SystemConfig.key == item["key"])
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is None:
                cfg = SystemConfig(
                    key=item["key"],
                    value=item["value"],
                    value_type=item["value_type"],
                    category=item["category"],
                    label=item["label"],
                    description=item["description"],
                )
                db.add(cfg)
                inserted += 1
        if inserted > 0:
            await db.flush()
            logger.info("[SystemConfig] Inserted %d default config(s)", inserted)
        return inserted


# ── 全局辅助函数: 供各服务动态读取配置 ────────────────────────────────────────

async def get_dynamic_config(key: str, default: Any = None) -> Any:
    """
    动态读取系统配置，供各service调用。
    优先查Redis缓存，miss则查DB并写入缓存(TTL 5分钟)。
    """
    # 先查Redis
    try:
        redis = await _get_redis()
        cached = await redis.get(f"{_CONFIG_CACHE_PREFIX}{key}")
        if cached is not None:
            data = json.loads(cached)
            await redis.close()
            return _convert_value(data["value"], data["type"])
        await redis.close()
    except Exception as exc:
        logger.warning("get_dynamic_config Redis read failed for %s: %s", key, exc)

    # DB fallback
    from app.core.deps import async_session_factory
    async with async_session_factory() as session:
        stmt = select(SystemConfig).where(SystemConfig.key == key)
        result = await session.execute(stmt)
        cfg = result.scalar_one_or_none()
        if cfg is None:
            return default

        # 写缓存
        try:
            redis = await _get_redis()
            await redis.setex(
                f"{_CONFIG_CACHE_PREFIX}{key}",
                _CONFIG_CACHE_TTL,
                json.dumps({"value": cfg.value, "type": cfg.value_type}),
            )
            await redis.close()
        except Exception as exc:
            logger.warning("get_dynamic_config Redis write failed for %s: %s", key, exc)

        return _convert_value(cfg.value, cfg.value_type)
