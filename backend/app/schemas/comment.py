import datetime
from typing import Optional, List
from pydantic import BaseModel


class CommentOut(BaseModel):
    id: int
    video_id: int
    comment_id: str
    user_uid: str
    user_nickname: str
    content: str
    comment_time: Optional[datetime.datetime]
    crawled_at: datetime.datetime
    is_processed: bool

    class Config:
        from_attributes = True


class CommentResponse(BaseModel):
    """单条评论完整响应"""
    code: int = 200
    message: str = "success"
    data: CommentOut

    class Config:
        from_attributes = True


class CommentListResponse(BaseModel):
    """评论列表分页响应"""
    code: int = 200
    message: str = "success"
    data: List[CommentOut]
    total: int = 0
    page: int = 1
    page_size: int = 20


class CrawlStats(BaseModel):
    """采集统计"""
    total_today: int
    processed_today: int
    date: str


class CrawlStatsResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: CrawlStats


class CrawlResultResponse(BaseModel):
    """手动触发采集结果"""
    code: int = 200
    message: str = "success"
    data: dict
