"""AI自动对话服务 — 线索创建后自动通过OpenKF发起AI对话并持续跟进。

业务流程：
    评论 → AI识别为高/中意向 → 创建线索 → 自动发起AI对话 → AI持续回复转化 → 销售监控

核心方法：
    - initiate_ai_conversation: 线索创建后自动发起AI对话（幂等）
    - handle_ai_reply: 处理Chatdoing AI的回复（从SPI send端点收到）
    - handle_user_reply: 处理用户的回复消息
"""
import logging
import random
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chat import ChatMessage
from app.models.comment import Comment
from app.models.lead import Lead, LeadFollowup
from app.models.video import Video
from app.models.monitor import DouyinChatAccount
from app.services.openkf_service import openkf_service
from app.services.risk_control_service import risk_control_service

logger = logging.getLogger(__name__)

# ── 红线关键词 ──────────────────────────────────────────────────────────────────

# 拒绝词：用户明确表示不想继续
_REJECT_KEYWORDS = [
    "不需要", "别发了", "不要再发", "别联系我", "滚", "骚扰", "举报你",
    "不要了", "别再发", "别骚扰", "拉黑你", "取消", "不用了",
]

# 愤怒/法律词：需要立即转人工
_ANGRY_LEGAL_KEYWORDS = [
    "投诉", "律师", "报警", "法院", "起诉", "骗子", "诈骗",
    "工商", "消协", "维权", "法律", "告你",
]


def detect_red_line(content: str) -> Optional[str]:
    """检测用户回复是否触发红线规则

    Returns:
        "reject" — 用户明确拒绝，停止对话并加黑名单
        "angry"  — 用户情绪激动/投诉/法律相关，立即转人工
        None     — 未触发红线
    """
    if not content:
        return None
    text = content.strip()

    # 优先检测愤怒/法律词（优先级高于拒绝）
    for kw in _ANGRY_LEGAL_KEYWORDS:
        if kw in text:
            return "angry"

    # 检测拒绝词
    for kw in _REJECT_KEYWORDS:
        if kw in text:
            return "reject"

    return None


class AutoChatService:
    """AI自动对话服务 - 线索创建后自动发起AI对话"""

    async def initiate_ai_conversation(
        self, lead_id: int, db: AsyncSession
    ) -> Optional[dict]:
        """
        线索创建后自动发起AI对话

        流程：
        1. 获取线索信息（评论内容、用户UID、视频标题）
        2. 生成唯一chat_id：f"lead-{lead_id}"
        3. 幂等检查：如果lead已有chat_id则跳过
        4. 随机分配话术模板编号(template_id)
        5. 调用LLM生成个性化首条私信（基于用户评论）
        6. 通过OpenKF回调推送event.msg给Chatdoing
        7. 更新Lead: chat_id, chat_status=2(AI托管), template_id
        8. 保存消息记录到chat_messages
        9. WebSocket通知前端有新对话
        """
        # 1. 获取线索信息
        lead_result = await db.execute(select(Lead).where(Lead.id == lead_id))
        lead = lead_result.scalar_one_or_none()
        if not lead:
            logger.warning("initiate_ai_conversation: lead %d not found", lead_id)
            return None

        # 3. 幂等检查：如果lead已有chat_id则跳过
        if lead.chat_id:
            logger.info(
                "initiate_ai_conversation: lead %d already has chat_id=%s, skipping",
                lead_id, lead.chat_id,
            )
            return {"lead_id": lead_id, "chat_id": lead.chat_id, "skipped": True}

        # 获取评论内容
        comment_content = ""
        if lead.comment_id:
            c_result = await db.execute(
                select(Comment.content).where(Comment.id == lead.comment_id)
            )
            comment_content = c_result.scalar_one_or_none() or ""

        video_title = ""
        if lead.video_id:
            v_result = await db.execute(
                select(Video.title).where(Video.id == lead.video_id)
            )
            video_title = v_result.scalar_one_or_none() or ""

        # 4. 随机分配话术模板编号
        template_id = random.randint(1, settings.AI_CHAT_TEMPLATES_COUNT)
        lead.template_id = template_id

        # 5. 调用LLM生成个性化首条私信
        push_content = ""
        if comment_content:
            try:
                from app.adapters.llm_api import LLMAPIAdapter
                llm = LLMAPIAdapter()
                push_content = await llm.generate_first_dm(comment_content, template_id)
                logger.info(
                    "initiate_ai_conversation: LLM generated first DM for lead %d (template=%d)",
                    lead_id, template_id,
                )
            except Exception as exc:
                logger.error(
                    "initiate_ai_conversation: LLM first DM failed for lead %d: %s",
                    lead_id, exc,
                )

        # LLM失败或无评论内容时使用降级内容
        if not push_content:
            push_content = comment_content if comment_content else ""
        if not push_content:
            push_content = f"用户对视频「{video_title}」感兴趣，请跟进"

        # 2. 生成唯一chat_id
        chat_id = f"lead-{lead_id}"

        # 6. 通过OpenKF回调推送event.msg给Chatdoing
        push_ok = False
        ext_msg_id = ""
        if settings.OPENKF_CALLBACK_URL:
            push_ok, ext_msg_id = await openkf_service.push_message_to_chatdoing(
                chat_id=chat_id,
                sender_id=lead.user_uid,
                content=push_content,
                msg_type=0,
                chat_status=2,  # AI托管
            )
        else:
            logger.warning(
                "initiate_ai_conversation: OPENKF_CALLBACK_URL not configured, "
                "message will be stored locally only"
            )

        # 7. 更新Lead
        lead.chat_id = chat_id
        lead.chat_status = 2  # AI托管
        lead.round_count = 1  # 首条私信算第1轮

        # 8. 保存消息记录到chat_messages
        account_id = await self._get_default_account_id(db)
        msg = None
        if account_id > 0:
            msg = ChatMessage(
                lead_id=lead_id,
                douyin_account_id=account_id,
                chat_id=chat_id,
                external_msg_id=ext_msg_id,
                direction="outbound",  # 我方发出的首条私信
                content=push_content,
                msg_type="text",
                status="delivered" if push_ok else "pending",
            )
            db.add(msg)
        else:
            logger.warning(
                "initiate_ai_conversation: no douyin account found, "
                "message will not be persisted to chat_messages"
            )

        # 记录跟进日志
        followup = LeadFollowup(
            lead_id=lead_id,
            operator_id=1,  # 系统操作
            action="chat",
            content=f"AI自动发起对话(模板{template_id})，个性化私信: {push_content[:50]}...",
        )
        db.add(followup)

        await db.flush()

        # 9. WebSocket通知前端有新对话
        if msg:
            await self._notify_frontend_new_conversation(lead, msg)

        logger.info(
            "initiate_ai_conversation: lead_id=%d chat_id=%s push_ok=%s template=%d",
            lead_id, chat_id, push_ok, template_id,
        )
        return {
            "lead_id": lead_id,
            "chat_id": chat_id,
            "push_ok": push_ok,
            "message_id": msg.id if msg else None,
            "template_id": template_id,
        }

    async def handle_ai_reply(
        self,
        chat_id: str,
        content: str,
        msg_type: int,
        db: AsyncSession,
        external_msg_id: str = "",
    ) -> Optional[dict]:
        """
        处理Chatdoing AI的回复（从SPI send端点收到）

        1. 根据chat_id找到对应的lead
        2. 保存AI回复到chat_messages (direction=out, 因为是我方发出去给用户的)
        3. 更新round_count
        4. WebSocket推送给前端（销售可实时看到AI在聊什么）
        5. 记录跟进日志
        """
        lead = await self._resolve_lead_by_chat_id(db, chat_id)
        if not lead:
            logger.warning(
                "handle_ai_reply: no lead found for chat_id=%s", chat_id
            )
            return None

        account_id = await self._get_account_id_for_lead(db, lead.id)

        msg_type_str = self._msg_type_int_to_str(msg_type)

        msg = None
        if account_id > 0:
            msg = ChatMessage(
                lead_id=lead.id,
                douyin_account_id=account_id,
                chat_id=chat_id,
                external_msg_id=external_msg_id,
                direction="outbound",  # AI回复发给用户，方向为出站
                content=content,
                msg_type=msg_type_str,
                status="delivered",
            )
            db.add(msg)
            await db.flush()
        else:
            logger.warning(
                "handle_ai_reply: no account found for lead %d, "
                "message will not be persisted", lead.id,
            )

        # 记录跟进日志
        followup = LeadFollowup(
            lead_id=lead.id,
            operator_id=1,  # 系统操作
            action="chat",
            content=f"AI自动回复: {content[:50]}...",
        )
        db.add(followup)
        await db.flush()

        # WebSocket推送给前端
        if msg:
            await self._notify_frontend_message(lead, msg, is_ai_reply=True)

        logger.info(
            "handle_ai_reply: chat_id=%s lead_id=%d content=%s...",
            chat_id, lead.id, content[:30],
        )
        return {
            "lead_id": lead.id,
            "message_id": msg.id if msg else None,
            "direction": "outbound",
        }

    async def handle_user_reply(
        self,
        chat_id: str,
        sender_id: str,
        content: str,
        msg_type: int,
        db: AsyncSession,
        external_msg_id: str = "",
    ) -> Optional[dict]:
        """
        处理用户的回复消息（通过用户在抖音端回复私信，chatdoing再转发给我们）

        1. 根据chat_id找到对应的lead
        2. 保存用户回复到chat_messages (direction=inbound)
        3. 红线检测：拒绝词→停止对话+黑名单，愤怒/法律→转人工
        4. 轮次检测：round_count >= AI_MAX_ROUNDS → 强制转人工
        5. 更新round_count
        6. 如果仍在AI托管且未触发红线，调用LLM生成回复并推送
        7. WebSocket推送给前端
        """
        lead = await self._resolve_lead_by_chat_id(db, chat_id)
        if not lead:
            logger.warning(
                "handle_user_reply: no lead found for chat_id=%s sender_id=%s",
                chat_id, sender_id,
            )
            return None

        account_id = await self._get_account_id_for_lead(db, lead.id)
        msg_type_str = self._msg_type_int_to_str(msg_type)

        # 保存用户回复
        msg = None
        if account_id > 0:
            msg = ChatMessage(
                lead_id=lead.id,
                douyin_account_id=account_id,
                chat_id=chat_id,
                external_msg_id=external_msg_id,
                direction="inbound",  # 用户的回复，方向为入站
                content=content,
                msg_type=msg_type_str,
                status="delivered",
            )
            db.add(msg)
            await db.flush()

        # WebSocket推送给前端
        if msg:
            await self._notify_frontend_message(lead, msg, is_ai_reply=False)

        # ── 红线检测 ──
        red_line = detect_red_line(content)

        if red_line == "reject":
            # 用户明确拒绝 → 停止对话 + 加黑名单
            logger.info(
                "handle_user_reply: REJECT detected for lead %d, stopping AI and blacklisting",
                lead.id,
            )
            lead.chat_status = 0  # 停止AI
            followup = LeadFollowup(
                lead_id=lead.id,
                operator_id=1,
                action="status_change",
                content=f"用户触发拒绝红线，AI停止对话。用户原话: {content[:100]}",
            )
            db.add(followup)
            await db.flush()
            # 加入风控黑名单，后续不再向该用户发送私信
            try:
                await risk_control_service.add_to_blacklist(
                    db, sender_id, reason="blacklisted_by_user"
                )
            except Exception as exc:
                logger.error("handle_user_reply: blacklist failed: %s", exc)
            await self._notify_frontend_transfer(lead, "用户明确拒绝，AI已停止对话")

        elif red_line == "angry":
            # 用户情绪激动/法律相关 → 立即转人工
            logger.info(
                "handle_user_reply: ANGRY/LEGAL detected for lead %d, transferring to human",
                lead.id,
            )
            await self._transfer_to_human(db, lead, f"用户触发红线(愤怒/法律)，自动转人工。用户原话: {content[:100]}")

        elif lead.chat_status == 2:
            # 仍在AI托管状态 — 检查轮次
            lead.round_count = (lead.round_count or 0) + 1

            if lead.round_count >= settings.AI_MAX_ROUNDS:
                # 超过最大轮次 → 强制转人工
                logger.info(
                    "handle_user_reply: MAX_ROUNDS(%d) reached for lead %d, transferring to human",
                    settings.AI_MAX_ROUNDS, lead.id,
                )
                await self._transfer_to_human(
                    db, lead,
                    f"AI对话已达{settings.AI_MAX_ROUNDS}轮上限，强制转人工",
                )
            else:
                # 正常多轮回复：调用LLM生成回复
                await self._generate_and_send_ai_reply(db, lead, chat_id, account_id)

        await db.flush()

        logger.info(
            "handle_user_reply: chat_id=%s lead_id=%d sender_id=%s content=%s... red_line=%s rounds=%d",
            chat_id, lead.id, sender_id, content[:30], red_line, lead.round_count,
        )
        return {
            "lead_id": lead.id,
            "message_id": msg.id if msg else None,
            "direction": "inbound",
            "red_line": red_line,
            "round_count": lead.round_count,
        }

    # ── AI回复生成 ────────────────────────────────────────────────────────────

    async def _generate_and_send_ai_reply(
        self, db: AsyncSession, lead: Lead, chat_id: str, account_id: int
    ):
        """基于对话历史调用LLM生成回复并通过OpenKF推送给用户"""
        try:
            # 获取原始评论内容
            comment_content = ""
            if lead.comment_id:
                c_result = await db.execute(
                    select(Comment.content).where(Comment.id == lead.comment_id)
                )
                comment_content = c_result.scalar_one_or_none() or ""

            # 获取对话历史
            chat_history = await self._get_chat_history(db, lead.id)

            # 调用LLM生成回复
            from app.adapters.llm_api import LLMAPIAdapter
            llm = LLMAPIAdapter()
            reply_text = await llm.generate_dm_reply(
                original_comment=comment_content,
                chat_history=chat_history,
                template_id=lead.template_id or 1,
            )

            if not reply_text:
                logger.warning(
                    "_generate_and_send_ai_reply: LLM returned empty reply for lead %d",
                    lead.id,
                )
                return

            # 通过OpenKF推送回复
            push_ok = False
            ext_msg_id = ""
            if settings.OPENKF_CALLBACK_URL:
                push_ok, ext_msg_id = await openkf_service.push_message_to_chatdoing(
                    chat_id=chat_id,
                    sender_id=lead.user_uid,
                    content=reply_text,
                    msg_type=0,
                    chat_status=2,
                )

            # 保存AI回复到chat_messages
            if account_id > 0:
                ai_msg = ChatMessage(
                    lead_id=lead.id,
                    douyin_account_id=account_id,
                    chat_id=chat_id,
                    external_msg_id=ext_msg_id,
                    direction="outbound",
                    content=reply_text,
                    msg_type="text",
                    status="delivered" if push_ok else "pending",
                )
                db.add(ai_msg)

            # 跟进日志
            followup = LeadFollowup(
                lead_id=lead.id,
                operator_id=1,
                action="chat",
                content=f"AI多轮回复(第{lead.round_count}轮/模板{lead.template_id}): {reply_text[:50]}...",
            )
            db.add(followup)
            await db.flush()

            # WebSocket通知
            if account_id > 0:
                await self._notify_frontend_message(lead, ai_msg, is_ai_reply=True)

            logger.info(
                "_generate_and_send_ai_reply: lead=%d round=%d reply=%s...",
                lead.id, lead.round_count, reply_text[:30],
            )

        except Exception as exc:
            logger.error(
                "_generate_and_send_ai_reply: failed for lead %d: %s",
                lead.id, exc,
            )
            # 不崩溃，记录错误后跳过本次回复

    # ── 转人工 ────────────────────────────────────────────────────────────────

    async def _transfer_to_human(
        self, db: AsyncSession, lead: Lead, reason: str
    ):
        """将对话从AI托管转为人工服务，并通知前端"""
        lead.chat_status = 1  # 人工服务

        followup = LeadFollowup(
            lead_id=lead.id,
            operator_id=1,
            action="status_change",
            content=reason,
        )
        db.add(followup)
        await db.flush()

        await self._notify_frontend_transfer(lead, reason)

        logger.info(
            "_transfer_to_human: lead %d transferred. reason: %s",
            lead.id, reason,
        )

    # ── 对话历史 ──────────────────────────────────────────────────────────────

    async def _get_chat_history(self, db: AsyncSession, lead_id: int) -> list:
        """获取对话历史，构造messages数组（最近10条）"""
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.lead_id == lead_id)
            .order_by(ChatMessage.sent_at.asc())
        )
        messages = result.scalars().all()

        # 转换为 role/content 格式，限制最近10条
        history = []
        for m in messages[-10:]:
            role = "assistant" if m.direction == "outbound" else "user"
            history.append({"role": role, "content": m.content})

        return history

    # ── 内部辅助方法 ──────────────────────────────────────────────────────────

    @staticmethod
    def _msg_type_int_to_str(msg_type: int) -> str:
        """将数字msg_type转换为字符串"""
        _map = {0: "text", 1: "image", 2: "voice", 3: "file", 4: "video", 7: "location", 9: "link"}
        return _map.get(msg_type, "text")

    async def _resolve_lead_by_chat_id(
        self, db: AsyncSession, chat_id: str
    ) -> Optional[Lead]:
        """根据chat_id查找Lead（优先从lead.chat_id查找，其次从chat_messages查找）"""
        if not chat_id:
            return None

        # 优先从lead.chat_id字段查找
        result = await db.execute(
            select(Lead).where(Lead.chat_id == chat_id).limit(1)
        )
        lead = result.scalar_one_or_none()
        if lead:
            return lead

        # 回退：从chat_messages表查找
        msg_result = await db.execute(
            select(ChatMessage.lead_id)
            .where(ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.sent_at.desc())
            .limit(1)
        )
        row = msg_result.first()
        if not row or row[0] == 0:
            return None
        lead_result = await db.execute(select(Lead).where(Lead.id == row[0]))
        return lead_result.scalar_one_or_none()

    async def _get_default_account_id(self, db: AsyncSession) -> int:
        """获取默认的抖音账号ID"""
        result = await db.execute(
            select(DouyinChatAccount.id).limit(1)
        )
        row = result.first()
        return row[0] if row else 0

    async def _get_account_id_for_lead(self, db: AsyncSession, lead_id: int) -> int:
        """获取线索关联的抖音账号ID"""
        result = await db.execute(
            select(ChatMessage.douyin_account_id)
            .where(ChatMessage.lead_id == lead_id)
            .where(ChatMessage.douyin_account_id > 0)
            .order_by(ChatMessage.sent_at.desc())
            .limit(1)
        )
        row = result.first()
        if row and row[0] > 0:
            return row[0]
        return await self._get_default_account_id(db)

    async def _notify_frontend_new_conversation(self, lead: Lead, msg: ChatMessage):
        """WebSocket通知前端有新对话"""
        try:
            from app.api.v1.chat import manager
            notify_data = {
                "type": "new_conversation",
                "data": {
                    "lead_id": lead.id,
                    "chat_id": lead.chat_id,
                    "chat_status": lead.chat_status,
                    "message": {
                        "id": msg.id,
                        "lead_id": lead.id,
                        "direction": msg.direction,
                        "content": msg.content,
                        "msg_type": msg.msg_type,
                        "status": msg.status,
                    },
                },
            }
            # 如果有分配的销售，发给该销售
            if lead.assigned_to:
                await manager.send_to_user(lead.assigned_to, notify_data)
            else:
                # 没有分配，广播给所有在线用户
                await manager.broadcast(notify_data)
        except Exception as exc:
            logger.warning("WebSocket new conversation notify failed: %s", exc)

    async def _notify_frontend_message(
        self, lead: Lead, msg: ChatMessage, is_ai_reply: bool = False
    ):
        """WebSocket推送消息给前端"""
        try:
            from app.api.v1.chat import manager
            notify_data = {
                "type": "new_message",
                "data": {
                    "id": msg.id,
                    "lead_id": lead.id,
                    "chat_id": msg.chat_id,
                    "direction": msg.direction,
                    "content": msg.content,
                    "msg_type": msg.msg_type,
                    "status": msg.status,
                    "is_ai": is_ai_reply,
                    "chat_status": lead.chat_status,
                },
            }
            if lead.assigned_to:
                await manager.send_to_user(lead.assigned_to, notify_data)
            else:
                await manager.broadcast(notify_data)
        except Exception as exc:
            logger.warning("WebSocket message notify failed: %s", exc)

    async def _notify_frontend_transfer(self, lead: Lead, reason: str):
        """WebSocket通知前端对话已转人工"""
        try:
            from app.api.v1.chat import manager
            notify_data = {
                "type": "chat_transferred",
                "data": {
                    "lead_id": lead.id,
                    "chat_id": lead.chat_id,
                    "chat_status": lead.chat_status,
                    "reason": reason,
                },
            }
            if lead.assigned_to:
                await manager.send_to_user(lead.assigned_to, notify_data)
            else:
                await manager.broadcast(notify_data)
        except Exception as exc:
            logger.warning("WebSocket transfer notify failed: %s", exc)


# ── 模块级单例 ────────────────────────────────────────────────────────────────

auto_chat_service = AutoChatService()
