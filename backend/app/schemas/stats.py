from typing import List, Optional
from pydantic import BaseModel


class DashboardOverview(BaseModel):
    today_leads: int = 0
    today_high_intent: int = 0
    today_converted: int = 0
    pending_followup: int = 0
    today_comments: int = 0


class SalesPerformanceItem(BaseModel):
    user_id: int
    username: str
    total_leads: int = 0
    high_intent: int = 0
    converted: int = 0
    conversion_rate: float = 0.0
    avg_response_hours: float = 0.0


class MonitorStatsItem(BaseModel):
    monitor_id: int
    nickname: str
    total_comments: int = 0
    total_leads: int = 0
    lead_rate: float = 0.0


class TrendDataPoint(BaseModel):
    date: str
    comments: int = 0
    leads: int = 0
    high_intent: int = 0
    converted: int = 0


class TrendResponse(BaseModel):
    data: List[TrendDataPoint]
