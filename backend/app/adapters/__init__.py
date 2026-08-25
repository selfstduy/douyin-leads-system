import os

from app.adapters.base import BaseSentimentAdapter, CommentDTO, VideoDTO  # noqa: F401
from app.adapters.llm_base import BaseLLMAdapter, IntentLevel, IntentResult  # noqa: F401


def get_sentiment_adapter() -> BaseSentimentAdapter:
    """根据环境变量返回具体适配器，默认使用Mock"""
    adapter_type = os.environ.get("SENTIMENT_ADAPTER", "mock")

    if adapter_type == "api":
        from app.adapters.sentiment_api import SentimentAPIAdapter
        return SentimentAPIAdapter()

    # 默认返回Mock适配器
    from app.adapters.mock_adapter import MockSentimentAdapter
    return MockSentimentAdapter()


def get_llm_adapter() -> BaseLLMAdapter:
    """根据环境变量LLM_ADAPTER返回LLM适配器，默认使用Mock"""
    adapter_type = os.environ.get("LLM_ADAPTER", "mock")

    if adapter_type == "api":
        from app.adapters.llm_api import LLMAPIAdapter
        return LLMAPIAdapter()

    # 默认返回Mock LLM适配器
    from app.adapters.llm_mock import MockLLMAdapter
    return MockLLMAdapter()
