"""HTTP LLM适配器 — 通过HTTP请求调用大模型API进行意向分析。"""
import json
import logging
from typing import List

import httpx

from app.adapters.llm_base import BaseLLMAdapter, IntentLevel, IntentResult
from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Prompt模板 ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "你是一个专业的抖音视频评论意向分析助手。请分析用户评论是否有购买/咨询/合作意向。\n\n"
    "判断标准：\n"
    "- high(高意向)：明确表达购买意愿、询问价格、询问购买方式、要求联系方式、表示想要/需要\n"
    "- medium(中意向)：询问产品效果、表示感兴趣、询问详情、犹豫对比\n"
    "- invalid(无效)：纯闲聊、表情、吐槽、无关内容、广告\n\n"
    "请以JSON格式返回：\n"
    '{"intent_level": "high/medium/invalid", "reason": "简要分析理由(20字以内)"}'
)

_SINGLE_PROMPT = """评论内容: {comment_text}
视频标题: {video_title}"""

# ── 私信对话 System Prompt 模板 ──────────────────────────────────────────────────

_DM_SYSTEM_PROMPTS = {
    1: (
        "你是情感咨询接待顾问，和抖音私信用户对话。\n"
        "规则：\n"
        "1、先拿到【用户原始评论内容】作为背景，回复要贴合用户实际处境，不要通用套话。\n"
        "2、优先共情，不要上来就推销服务，不要承诺一定挽回、保证修复、多少天复合，严禁夸大效果。\n"
        "3、不要输出长篇大论，口语简短，像真人聊天，避免AI书面感。\n"
        "4、目标：了解更多现状，判断用户真实情况，适度引导，如果用户愿意深入沟通，可以引导到企业微信进一步沟通。\n"
        "5、红线：\n"
        "- 不许承诺结果、不许说成功率、不许保证帮你挽回；\n"
        "- 用户情绪激动、质问、投诉、提出法律相关问题，立刻转人工；\n"
        "- 用户明确表示不需要、别再发消息，立刻停止对话。\n"
        "执行流程：\n"
        "①第一轮（首次私信）：基于用户原始评论共情，简单提问1个问题，了解现状。\n"
        "②用户回复之后：继续共情，挖掘关键信息（发现多久、目前状态、有没有拉扯）。\n"
        "③当用户主动问“怎么处理、怎么办、你们怎么帮我”，再介绍可以提供咨询分析服务，顺势引导企微。\n"
        "④如果用户表现抗拒、拒绝，马上停止推销，不纠缠。\n"
        "输出：直接输出对话回复文本，不要多余标签。"
    ),
    2: (
        "你是一位温暖贴心的情感咨询小姐姐，和抖音私信用户聊天。\n"
        "规则：\n"
        "1、称呼用户为“姐妹”，语气柔和温暖，像闺蜜聊天一样。\n"
        "2、先了解用户的【原始评论内容】，从这里切入共情，不要通用套话。\n"
        "3、不要急于推销，先关心姐妹的感受和现状，让人感受到真诚。\n"
        "4、简短口语化，不要长篇大论，不要有AI书面感。\n"
        "5、红线：\n"
        "- 不许承诺结果、不许说成功率、不许保证帮你挽回；\n"
        "- 用户情绪激动、质问、投诉、法律相关，立刻转人工；\n"
        "- 用户说不要了、别再发了，立刻停止。\n"
        "执行流程：\n"
        "①第一轮：基于评论共情，温柔地问一个了解现状的问题。\n"
        "②后续：继续关心姐妹的处境，挖掘关键信息。\n"
        "③当姐妹主动问怎么办，再介绍咨询分析服务，引导到企微。\n"
        "④用户抗拒就停下，不纠缠。\n"
        "输出：直接输出对话文本，不要多余标签。"
    ),
    3: (
        "你是一名专业的情感咨询师，在抖音私信中与用户沟通。\n"
        "规则：\n"
        "1、风格专业冷静，有理有据，体现咨询师的专业感。\n"
        "2、以用户【原始评论内容】为背景，针对性回复，不用模板化套话。\n"
        "3、先倾听、后分析，不要上来就给建议或推销服务。\n"
        "4、语言简洁，口语化但不失专业感，避免冗长。\n"
        "5、红线：\n"
        "- 不许承诺结果、不许说成功率、不许保证效果；\n"
        "- 用户情绪激动、投诉、法律相关问题，立刻转人工；\n"
        "- 用户明确拒绝，立刻停止对话。\n"
        "执行流程：\n"
        "①第一轮：从评论切入，专业地提出一个了解情况的问题。\n"
        "②后续：逐步了解情况，分析用户状态。\n"
        "③用户主动求助时，介绍专业咨询服务，引导企微。\n"
        "④用户抗拒即停止。\n"
        "输出：直接输出对话文本，不要多余标签。"
    ),
}

# 请求超时(秒)
_REQUEST_TIMEOUT = 30.0

# 私信对话请求超时(秒)
_DM_REQUEST_TIMEOUT = 60.0


class LLMAPIAdapter(BaseLLMAdapter):
    """通过HTTP请求调用大模型API进行意向分析"""

    def __init__(self):
        self.api_key = settings.LLM_API_KEY
        # 通义千问兼容OpenAI格式，URL已是完整地址，无需拼接
        self.api_url = settings.LLM_API_URL.rstrip("/") if settings.LLM_API_URL else ""
        self.model = settings.LLM_MODEL

    async def analyze_intent(self, comment_text: str, context: dict = None) -> IntentResult:
        """单条评论意向分析"""
        context = context or {}
        video_title = context.get("video_title", "")

        prompt = _SINGLE_PROMPT.format(
            comment_text=comment_text,
            video_title=video_title,
        )

        try:
            response_text = await self._call_llm(prompt)
            data = self._parse_json(response_text)

            level_str = data.get("intent_level", "invalid")
            try:
                intent_level = IntentLevel(level_str)
            except ValueError:
                logger.warning("LLM returned unknown intent_level: %s, fallback to invalid", level_str)
                intent_level = IntentLevel.INVALID

            reason = data.get("reason", "AI分析完成")
            # 置信度基于返回结果估算
            confidence = {"high": 0.85, "medium": 0.65, "invalid": 0.80}.get(intent_level.value, 0.5)

            return IntentResult(
                comment_id=context.get("comment_id", ""),
                intent_level=intent_level,
                reason=reason,
                confidence=confidence,
            )
        except Exception as exc:
            logger.error("LLM API single analysis failed: %s", exc)
            return self._fallback_result(context.get("comment_id", ""))

    async def batch_analyze_intent(self, comments: List[dict]) -> List[IntentResult]:
        """批量评论意向分析 —— 逐条请求，通义千问token充足且单条更准确"""
        if not comments:
            return []

        results: List[IntentResult] = []
        for c in comments:
            cid = str(c.get("comment_id", ""))
            content = c.get("content", "")
            vtitle = c.get("video_title", "")
            try:
                result = await self.analyze_intent(
                    content,
                    context={"comment_id": cid, "video_title": vtitle},
                )
                result.comment_id = cid
                results.append(result)
            except Exception:
                results.append(self._fallback_result(cid))
        return results

    async def generate_dm_reply(
        self,
        original_comment: str,
        chat_history: list,
        template_id: int,
    ) -> str:
        """生成私信回复（多轮对话）

        Args:
            original_comment: 用户的原始评论内容
            chat_history: 历史消息列表 [{"role": "user"/"assistant", "content": "..."}]
            template_id: 话术模板编号 (1-3)

        Returns:
            AI生成的回复文本
        """
        system_prompt = _DM_SYSTEM_PROMPTS.get(template_id, _DM_SYSTEM_PROMPTS[1])

        # 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]

        # 添加原始评论作为背景上下文
        context_msg = f"【用户原始评论内容】：{original_comment}"
        messages.append({"role": "system", "content": context_msg})

        # 添加历史消息（限制最近10条避免token过长）
        recent_history = chat_history[-10:] if len(chat_history) > 10 else chat_history
        for h in recent_history:
            messages.append({"role": h["role"], "content": h["content"]})

        try:
            reply = await self._call_llm_chat(messages)
            return reply.strip()
        except Exception as exc:
            logger.error("generate_dm_reply failed (template=%d): %s", template_id, exc)
            raise

    async def generate_first_dm(
        self, original_comment: str, template_id: int
    ) -> str:
        """生成个性化首条私信（基于用户评论）

        Args:
            original_comment: 用户的原始评论内容
            template_id: 话术模板编号 (1-3)

        Returns:
            AI生成的首条私信文本
        """
        system_prompt = _DM_SYSTEM_PROMPTS.get(template_id, _DM_SYSTEM_PROMPTS[1])

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": f"【用户原始评论内容】：{original_comment}"},
            {"role": "user", "content": "请基于以上用户评论，生成一条个性化的首次私信消息。"},
        ]

        try:
            reply = await self._call_llm_chat(messages)
            return reply.strip()
        except Exception as exc:
            logger.error("generate_first_dm failed (template=%d): %s", template_id, exc)
            raise

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    async def _call_llm_chat(self, messages: list) -> str:
        """调用通义千问 LLM API 进行对话（私信回复用）"""
        if not self.api_url or not self.api_key:
            raise RuntimeError("LLM_API_URL or LLM_API_KEY not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=_DM_REQUEST_TIMEOUT) as client:
            response = await client.post(
                self.api_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        return content.strip()

    async def _call_llm(self, prompt: str) -> str:
        """调用通义千问 LLM API (兼容OpenAI格式)"""
        if not self.api_url or not self.api_key:
            raise RuntimeError("LLM_API_URL or LLM_API_KEY not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            # 通义千问兼容地址已是完整URL，直接POST
            response = await client.post(
                self.api_url,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        # 提取回复内容(与OpenAI响应格式一致)
        content = data["choices"][0]["message"]["content"]
        return content.strip()

    def _parse_json(self, text: str):
        """从LLM返回的文本中提取JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从markdown code block中提取
        if "```" in text:
            for block in text.split("```"):
                block = block.strip()
                if block.startswith("json"):
                    block = block[4:].strip()
                try:
                    return json.loads(block)
                except json.JSONDecodeError:
                    continue

        # 尝试查找 { 或 [ 开头的子串
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    continue

        raise ValueError(f"Cannot parse JSON from LLM response: {text[:200]}")

    @staticmethod
    def _fallback_result(comment_id: str) -> IntentResult:
        """降级结果: 标记为invalid"""
        return IntentResult(
            comment_id=comment_id,
            intent_level=IntentLevel.INVALID,
            reason="AI分析异常，自动标记为无效，请人工复核",
            confidence=0.0,
        )
