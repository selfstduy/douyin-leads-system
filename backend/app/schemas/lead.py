import datetime
from typing import Optional, List
from pydantic import BaseModel


# ── Request schemas ─────────────────────────────────────────────────────────────

class LeadListQuery(BaseModel):
    page: int = 1
    page_size: int = 20
    intent_level: Optional[str] = None  # high / medium / invalid
    status: Optional[str] = None  # pending / assigned / following / converted / closed
    assigned_to: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    search: Optional[str] = None  # 用户昵称模糊搜索


class LeadAssign(BaseModel):
    user_id: int


class BatchAssign(BaseModel):
    lead_ids: List[int]
    user_id: int


class LeadStatusUpdate(BaseModel):
    status: str  # assigned / following / converted / closed


class LeadFollowupCreate(BaseModel):
    action: str = "note"  # note / status_change / chat
    content: str = ""


class TransferToHuman(BaseModel):
    sales_user_id: int


# ── Legacy schemas (keep backward compat) ──────────────────────────────────────

class LeadUpdate(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[int] = None
    intent_level: Optional[str] = None


# ── Response schemas ────────────────────────────────────────────────────────────

class FollowupResponse(BaseModel):
    id: int
    lead_id: int
    operator_id: int
    operator_name: Optional[str] = None
    action: str
    content: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class LeadResponse(BaseModel):
    id: int
    comment_id: int
    video_id: int
    user_uid: str
    user_nickname: str
    user_avatar: str
    intent_level: str
    ai_reason: str
    status: str
    assigned_to: Optional[int]
    assigned_to_name: Optional[str] = None
    assigned_at: Optional[datetime.datetime]
    chat_status: int = 0  # 0=待处理, 1=人工服务, 2=AI托管
    created_at: datetime.datetime
    # 关联信息
    comment_content: Optional[str] = None
    video_title: Optional[str] = None

    class Config:
        from_attributes = True


class LeadDetailResponse(LeadResponse):
    """线索详情(含跟进记录)"""
    monitor_account_name: Optional[str] = None
    followups: List[FollowupResponse] = []


# Legacy alias
LeadOut = LeadResponse
LeadFollowupOut = FollowupResponse
