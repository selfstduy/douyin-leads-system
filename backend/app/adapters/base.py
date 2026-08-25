from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CommentDTO:
    """评论数据传输对象"""
    comment_id: str
    video_id: str
    user_uid: str
    user_nickname: str
    content: str
    comment_time: datetime


@dataclass
class VideoDTO:
    """视频数据传输对象"""
    video_id: str
    title: str
    publish_time: datetime
    account_uid: Optional[str] = None  # 所属账号UID（全网搜索时需要）
    account_nickname: Optional[str] = None
    comment_count: int = 0  # 视频评论总数，用于热度判断


class BaseSentimentAdapter(ABC):
    """舆情数据采集适配器抽象基类"""

    @abstractmethod
    async def fetch_comments(self, video_id: str, since_time: datetime) -> List[CommentDTO]:
        """获取指定视频从since_time之后的评论"""
        ...

    @abstractmethod
    async def get_video_list(self, account_uid: str) -> List[VideoDTO]:
        """获取账号的视频列表"""
        ...

    @abstractmethod
    async def fetch_topic_comments(self, topic: str, industry: str, since_time: datetime) -> List[CommentDTO]:
        """按话题/行业范围采集全网评论(不做关键词过滤，采集该领域的所有评论)"""
        ...

    @abstractmethod
    async def search_videos_by_keyword(self, keyword: str, page: int, page_size: int) -> List[VideoDTO]:
        """按关键词搜索全网视频"""
        ...
