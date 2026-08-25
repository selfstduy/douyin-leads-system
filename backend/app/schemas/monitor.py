import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class MonitorAccountCreate(BaseModel):
    douyin_url: str = Field(..., description="抖音用户链接或UID")
    poll_interval_min: int = Field(5, ge=1, description="拉取间隔(分钟)")


class MonitorAccountUpdate(BaseModel):
    nickname: Optional[str] = None
    status: Optional[str] = None
    poll_interval_min: Optional[int] = Field(None, ge=1)


class MonitorAccountOut(BaseModel):
    id: int
    douyin_url: str
    douyin_uid: str
    nickname: str
    avatar: str
    status: str
    poll_interval_min: int
    created_by: Optional[int]
    created_at: datetime.datetime
    source: str = "manual"
    last_high_intent_at: Optional[datetime.datetime] = None
    total_high_count: int = 0

    class Config:
        from_attributes = True


class MonitorAccountList(BaseModel):
    code: int = 200
    message: str = "success"
    data: List[MonitorAccountOut] = []
    total: int = 0
    page: int = 1
    page_size: int = 20


class BatchImportResult(BaseModel):
    success_count: int = 0
    fail_count: int = 0
    errors: List[str] = []
