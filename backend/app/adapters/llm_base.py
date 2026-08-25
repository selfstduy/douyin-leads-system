"""LLM意向分析适配器基类与数据结构。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List
from enum import Enum


class IntentLevel(str, Enum):
    """评论意向等级"""
    HIGH = "high"
    MEDIUM = "medium"
    INVALID = "invalid"


@dataclass
class IntentResult:
    """单条评论的意向分析结果"""
    comment_id: str
    intent_level: IntentLevel
    reason: str  # AI分析理由
    confidence: float = 0.0  # 置信度 0-1


class BaseLLMAdapter(ABC):
    """LLM意向分析适配器抽象基类"""

    @abstractmethod
    async def analyze_intent(self, comment_text: str, context: dict = None) -> IntentResult:
        """单条评论意向分析

        Args:
            comment_text: 评论文本内容
            context: 可选上下文信息, 如 video_title 等

        Returns:
            IntentResult: 意向分析结果
        """
        ...

    @abstractmethod
    async def batch_analyze_intent(self, comments: List[dict]) -> List[IntentResult]:
        """批量评论意向分析(降低API调用成本)

        Args:
            comments: 评论列表, 每项包含 comment_id, content, 以及可选的 video_title 等上下文

        Returns:
            List[IntentResult]: 每条评论的分析结果
        """
        ...
