import logging
from datetime import datetime
from typing import List

import httpx

from app.adapters.base import BaseSentimentAdapter, CommentDTO, VideoDTO
from app.core.config import settings

logger = logging.getLogger(__name__)


class SentimentAPIAdapter(BaseSentimentAdapter):
    """通用HTTP舆情API适配器（预留实现，等确定供应商后完善）"""

    def __init__(self):
        self.api_key = settings.SENTIMENT_API_KEY
        self.api_url = settings.SENTIMENT_API_URL.rstrip("/")

    async def fetch_comments(self, video_id: str, since_time: datetime) -> List[CommentDTO]:
        """从舆情API获取指定视频的评论"""
        if not self.api_url or not self.api_key:
            logger.warning("SENTIMENT_API_URL or SENTIMENT_API_KEY not configured, returning empty list")
            return []

        # TODO: 确定供应商后替换为实际请求格式
        url = f"{self.api_url}/comments"
        params = {
            "video_id": video_id,
            "since_time": since_time.isoformat(),
            # TODO: 添加分页参数、排序参数等
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # TODO: 添加供应商要求的其他Header
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                logger.error("Failed to fetch comments from sentiment API: %s", exc)
                return []

        # TODO: 根据供应商响应格式解析数据，以下为示例结构
        comments = []
        for item in data.get("comments", []):
            comments.append(CommentDTO(
                comment_id=item.get("id", ""),
                video_id=video_id,
                user_uid=item.get("user_id", ""),
                user_nickname=item.get("nickname", ""),
                content=item.get("text", ""),
                comment_time=datetime.fromisoformat(item.get("created_at", datetime.now().isoformat())),
            ))
        return comments

    async def get_video_list(self, account_uid: str) -> List[VideoDTO]:
        """从舆情API获取账号的视频列表"""
        if not self.api_url or not self.api_key:
            logger.warning("SENTIMENT_API_URL or SENTIMENT_API_KEY not configured, returning empty list")
            return []

        # TODO: 确定供应商后替换为实际请求格式
        url = f"{self.api_url}/videos"
        params = {
            "account_uid": account_uid,
            # TODO: 添加分页参数等
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                logger.error("Failed to fetch video list from sentiment API: %s", exc)
                return []

        # TODO: 根据供应商响应格式解析数据
        videos = []
        for item in data.get("videos", []):
            videos.append(VideoDTO(
                video_id=item.get("id", ""),
                title=item.get("title", ""),
                publish_time=datetime.fromisoformat(item.get("publish_time", datetime.now().isoformat())),
                comment_count=item.get("comment_count", 0),
            ))
        return videos

    async def fetch_topic_comments(self, topic: str, industry: str, since_time: datetime) -> List[CommentDTO]:
        """按话题/行业范围采集全网评论(不做关键词过滤，采集该领域的所有评论)"""
        if not self.api_url or not self.api_key:
            logger.warning("SENTIMENT_API_URL or SENTIMENT_API_KEY not configured, returning empty list")
            return []

        # TODO: 确定供应商后替换为实际请求格式
        url = f"{self.api_url}/comments/search"
        params = {
            "topic": topic,
            "industry": industry,
            "since_time": since_time.isoformat(),
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                logger.error("Failed to fetch topic comments from sentiment API: %s", exc)
                return []

        comments = []
        for item in data.get("comments", []):
            comments.append(CommentDTO(
                comment_id=item.get("id", ""),
                video_id=item.get("video_id", ""),
                user_uid=item.get("user_id", ""),
                user_nickname=item.get("nickname", ""),
                content=item.get("text", ""),
                comment_time=datetime.fromisoformat(item.get("created_at", datetime.now().isoformat())),
            ))
        return comments

    async def search_videos_by_keyword(self, keyword: str, page: int, page_size: int) -> List[VideoDTO]:
        """从舆情API按关键词搜索全网视频"""
        if not self.api_url or not self.api_key:
            logger.warning("SENTIMENT_API_URL or SENTIMENT_API_KEY not configured, returning empty list")
            return []

        url = f"{self.api_url}/videos/search"
        params = {
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as exc:
                logger.error("Failed to search videos by keyword '%s': %s", keyword, exc)
                return []

        videos = []
        for item in data.get("videos", []):
            videos.append(VideoDTO(
                video_id=item.get("id", ""),
                title=item.get("title", ""),
                publish_time=datetime.fromisoformat(item.get("publish_time", datetime.now().isoformat())),
                account_uid=item.get("account_uid", ""),
                account_nickname=item.get("account_nickname", ""),
                comment_count=item.get("comment_count", 0),
            ))
        return videos
