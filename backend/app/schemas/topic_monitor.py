import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TopicMonitorCreate(BaseModel):
    topic: str = Field(..., description="监控话题/行业", min_length=1, max_length=128)
    description: str = Field("", description="话题描述(可选)", max_length=512)
    industry: str = Field("", description="行业分类", max_length=64)
    poll_interval_min: int = Field(5, ge=1, description="拉取间隔(分钟)")


class TopicMonitorUpdate(BaseModel):
    topic: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=512)
    industry: Optional[str] = Field(None, max_length=64)
    poll_interval_min: Optional[int] = Field(None, ge=1)


class TopicMonitorOut(BaseModel):
    id: int
    topic: str
    description: str
    industry: str
    status: str
    poll_interval_min: int
    created_by: Optional[int]
    created_at: datetime.datetime

    class Config:
        from_attributes = True
