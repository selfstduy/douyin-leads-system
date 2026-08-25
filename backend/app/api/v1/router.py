from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.monitors import router as monitors_router
from app.api.v1.topic_monitors import router as topic_monitors_router
from app.api.v1.leads import router as leads_router
from app.api.v1.chat import router as chat_router
from app.api.v1.stats import router as stats_router
from app.api.v1.users import router as users_router
from app.api.v1.comments import router as comments_router
from app.api.v1.douyin_accounts import router as douyin_accounts_router
from app.api.v1.system import router as system_router
from app.api.v1.dm_queue import router as dm_queue_router
from app.api.v1.risk import router as risk_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(monitors_router)
api_router.include_router(topic_monitors_router)
api_router.include_router(leads_router)
api_router.include_router(chat_router)
api_router.include_router(stats_router)
api_router.include_router(users_router)
api_router.include_router(comments_router)
api_router.include_router(douyin_accounts_router)
api_router.include_router(system_router)
api_router.include_router(dm_queue_router)
api_router.include_router(risk_router)
