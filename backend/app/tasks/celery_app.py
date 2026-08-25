from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "douyin_leads",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.crawler_tasks",
        "app.tasks.intent_tasks",
        "app.tasks.quota_tasks",
        "app.tasks.discovery_tasks",
        "app.tasks.auto_chat_tasks",
        "app.tasks.risk_control_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
)

# ── Beat schedule ─────────────────────────────────────────────────────────────
celery_app.conf.beat_schedule = {
    "poll-all-monitors-periodic": {
        "task": "app.tasks.crawler_tasks.poll_all_monitors",
        "schedule": crontab(minute="*"),  # 每分钟检查一次需要采集的账号
        "args": (),
    },
    "poll-topic-monitors-periodic": {
        "task": "app.tasks.crawler_tasks.poll_topic_monitors",
        "schedule": crontab(minute="*"),  # 每分钟检查一次需要采集的话题
        "args": (),
    },
    "sync-account-videos-periodic": {
        "task": "app.tasks.crawler_tasks.sync_all_account_videos",
        "schedule": crontab(minute=0, hour=f"*/{settings.ACCOUNT_SYNC_INTERVAL_HOURS}"),  # 每6小时同步一次视频列表
        "args": (),
    },
    "poll-video-comments-smart": {
        "task": "app.tasks.crawler_tasks.poll_all_video_comments",
        "schedule": crontab(minute="*"),  # 每分钟检查，由should_poll_video决定是否实际执行
        "args": (),
    },
    "expire-old-videos-hourly": {
        "task": "app.tasks.crawler_tasks.expire_old_videos",
        "schedule": crontab(minute=30),  # 每小时第30分执行
        "args": (),
    },
    "aggregate-daily-stats": {
        "task": "app.tasks.crawl_tasks.aggregate_daily_stats",
        "schedule": crontab(hour=0, minute=5),
        "args": (),
    },
    "process-new-comments-intent": {
        "task": "app.tasks.intent_tasks.process_new_comments",
        "schedule": 30.0,  # 每30秒执行一次
        "args": (),
    },
    "process-dm-queue": {
        "task": "app.tasks.dm_queue_tasks.process_dm_queue",
        "schedule": crontab(minute="*"),  # 每分钟检查并发送
        "args": (),
    },
    "overflow-dm-queue-to-next-day": {
        "task": "app.tasks.dm_queue_tasks.overflow_to_next_day",
        "schedule": crontab(hour=23, minute=0),  # 每天23:00将当日未发送的pending移到明天
        "args": (),
    },
    "check-report-rate-periodic": {
        "task": "app.tasks.risk_control_tasks.check_report_rate",
        "schedule": crontab(minute="*/10"),  # 每10分钟检查举报拉黑率
        "args": (),
    },
}
