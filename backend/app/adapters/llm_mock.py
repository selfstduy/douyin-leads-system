"""Mock LLM适配器 — 基于关键词规则模拟AI意向判断。"""
import asyncio
import random
import logging
from typing import List

from app.adapters.llm_base import BaseLLMAdapter, IntentLevel, IntentResult

logger = logging.getLogger(__name__)

# ── 关键词库 ───────────────────────────────────────────────────────────────────

_HIGH_INTENT_KEYWORDS = [
    "怎么买", "多少钱", "价格", "在哪买", "链接", "下单",
    "购买", "想要", "怎么联系", "怎么付款", "批发", "代购",
    "哪里有卖", "求链接", "想买", "加你微信", "私信我",
]

_MEDIUM_INTENT_KEYWORDS = [
    "好用吗", "效果怎么样", "推荐", "有用吗", "靠谱吗",
    "质量好不好", "适合新手吗", "有没有教程", "售后怎么样",
    "保质期多久", "成分是什么", "和", "比哪个好", "用过的来说说",
]

# 高意向理由模板
_HIGH_REASONS = [
    "评论包含明确的购买意向词汇"{kw}"，用户有强烈的消费意愿",
    "用户主动询问购买方式，关键词"{kw}"表明其已进入决策阶段",
    "评论中"{kw}"属于高转化信号，建议优先跟进",
]

_MEDIUM_REASONS = [
    "评论包含咨询性词汇"{kw}"，用户对产品有一定兴趣但尚未决策",
    "用户在了解产品详情，关键词"{kw}"表明存在潜在需求",
    "评论表现出犹豫态度，关键词"{kw}"提示需要进一步引导",
]

_INVALID_REASONS = [
    "评论未包含任何购买或咨询关键词，属于普通互动",
    "评论内容与购买意向无关，暂无跟进价值",
    "评论为一般性互动内容，不具备转化潜力",
]


def _match_keyword(text: str, keywords: list) -> str | None:
    """返回第一个命中的关键词，未命中返回None"""
    for kw in keywords:
        if kw in text:
            return kw
    return None


class MockLLMAdapter(BaseLLMAdapter):
    """基于关键词规则模拟AI意向判断，用于开发和测试"""

    async def analyze_intent(self, comment_text: str, context: dict = None) -> IntentResult:
        """单条评论意向分析"""
        # 模拟异步延迟 0.1-0.5秒
        await asyncio.sleep(random.uniform(0.1, 0.5))

        intent_level, reason, confidence = self._classify(comment_text)

        return IntentResult(
            comment_id="",
            intent_level=intent_level,
            reason=reason,
            confidence=confidence,
        )

    async def batch_analyze_intent(self, comments: List[dict]) -> List[IntentResult]:
        """批量评论意向分析"""
        results = []
        for comment in comments:
            # 模拟异步延迟，批量稍快一些
            await asyncio.sleep(random.uniform(0.05, 0.2))

            content = comment.get("content", "")
            comment_id = str(comment.get("comment_id", ""))

            intent_level, reason, confidence = self._classify(content)

            results.append(IntentResult(
                comment_id=comment_id,
                intent_level=intent_level,
                reason=reason,
                confidence=confidence,
            ))

        return results

    def _classify(self, text: str) -> tuple[IntentLevel, str, float]:
        """基于关键词和随机性进行分类"""
        # 检查高意向关键词
        high_kw = _match_keyword(text, _HIGH_INTENT_KEYWORDS)
        # 检查中意向关键词
        medium_kw = _match_keyword(text, _MEDIUM_INTENT_KEYWORDS)

        if high_kw:
            # 高意向有一定随机性：85%概率判为high，15%降为medium
            if random.random() < 0.85:
                reason = random.choice(_HIGH_REASONS).format(kw=high_kw)
                confidence = round(random.uniform(0.75, 0.95), 2)
                return IntentLevel.HIGH, reason, confidence
            else:
                reason = random.choice(_MEDIUM_REASONS).format(kw=high_kw)
                confidence = round(random.uniform(0.5, 0.7), 2)
                return IntentLevel.MEDIUM, reason, confidence

        if medium_kw:
            # 中意向：80%概率medium，10%升为high，10%降为invalid
            roll = random.random()
            if roll < 0.10:
                reason = random.choice(_HIGH_REASONS).format(kw=medium_kw)
                confidence = round(random.uniform(0.6, 0.8), 2)
                return IntentLevel.HIGH, reason, confidence
            elif roll < 0.90:
                reason = random.choice(_MEDIUM_REASONS).format(kw=medium_kw)
                confidence = round(random.uniform(0.5, 0.75), 2)
                return IntentLevel.MEDIUM, reason, confidence
            else:
                reason = random.choice(_INVALID_REASONS)
                confidence = round(random.uniform(0.3, 0.5), 2)
                return IntentLevel.INVALID, reason, confidence

        # 无关键词命中 → 无效
        reason = random.choice(_INVALID_REASONS)
        confidence = round(random.uniform(0.6, 0.9), 2)
        return IntentLevel.INVALID, reason, confidence
