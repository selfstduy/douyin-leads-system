import datetime
from typing import Optional, List, Any
from pydantic import BaseModel


class ChatMessageCreate(BaseModel):
    lead_id: int
    content: str
    msg_type: str = "text"
    douyin_account_id: Optional[int] = None


class ChatMessageOut(BaseModel):
    id: int
    lead_id: int
    douyin_account_id: int
    direction: str
    content: str
    msg_type: str
    sent_at: datetime.datetime
    status: str

    class Config:
        from_attributes = True


class ChatSessionOut(BaseModel):
    lead_id: int
    lead_nickname: str
    lead_uid: str
    last_message: Optional[str] = None
    last_message_at: Optional[datetime.datetime] = None
    unread_count: int = 0
    intent_level: str = ""
    chat_status: int = 0  # 0=待处理, 1=人工服务, 2=AI托管
    chat_id: Optional[str] = None

    class Config:
        from_attributes = True


class DouyinAccountCreate(BaseModel):
    douyin_uid: str
    nickname: str
    cookie_data: str


class DouyinAccountOut(BaseModel):
    id: int
    douyin_uid: str
    nickname: str
    login_status: str
    assigned_to_user_id: Optional[int] = None
    assigned_to_username: Optional[str] = None
    last_active_at: Optional[datetime.datetime] = None
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class DouyinAccountAssign(BaseModel):
    user_id: int


class DouyinAccountCookieUpdate(BaseModel):
    cookie_data: str
