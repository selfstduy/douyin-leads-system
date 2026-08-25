"""OpenKF SPI business service.

Handles inbound SPI calls from chatdoing and outbound callback pushes.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Optional, Tuple

import httpx
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.chat import ChatMessage
from app.models.lead import Lead
from app.services.openkf_crypto import (
    OpenKFCrypto, OpenKFCryptoError,
    H_DIRECTION, H_REQUEST_ID,
)

logger = logging.getLogger(__name__)

# ── Redis helpers ─────────────────────────────────────────────────────────────

_redis: Optional[aioredis.Redis] = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


async def _is_duplicate(key: str, ttl: int = 86400) -> bool:
    """Redis SETNX-based dedup. Returns True if key already existed."""
    r = await _get_redis()
    was_set = await r.set(key, "1", nx=True, ex=ttl)
    return was_set is None  # None means key already existed


async def _nonce_seen(app_id: str, nonce: str) -> bool:
    """Check/set nonce for replay protection (TTL 10 min)."""
    r = await _get_redis()
    key = f"openkf:nonce:{app_id}:{nonce}"
    was_set = await r.set(key, "1", nx=True, ex=600)
    return was_set is None


# ── Crypto singleton ──────────────────────────────────────────────────────────

_crypto: Optional[OpenKFCrypto] = None


def get_crypto() -> OpenKFCrypto:
    global _crypto
    if _crypto is None:
        if not settings.OPENKF_KEY:
            raise RuntimeError("OPENKF_KEY is not configured")
        _crypto = OpenKFCrypto(
            app_id=settings.OPENKF_APPID,
            key_id=settings.OPENKF_KEY_ID,
            key_base64=settings.OPENKF_KEY,
        )
    return _crypto


# ── msg_type mapping ──────────────────────────────────────────────────────────

_MSG_TYPE_MAP = {
    0: "text",
    1: "image",
    2: "voice",
    3: "file",
    4: "video",
    7: "location",
    9: "link",
}


# ── OpenKF Service ────────────────────────────────────────────────────────────

class OpenKFService:
    """Business logic for OpenKF SPI endpoints and callbacks."""

    # ── Inbound handlers (chatdoing → us) ────────────────────────────────────

    async def handle_send_message(self, db: AsyncSession, decrypted_body: dict) -> dict:
        """Process an inbound message from chatdoing.

        When chatdoing sends a message via SPI /messages/send, it could be:
        - AI reply (sender_type=2): AI generated a response to forward to the user
        - User reply (sender_type=1): User replied on Douyin, chatdoing forwards it

        Delegates to auto_chat_service for storage and WebSocket push.
        """
        msg_id = decrypted_body.get("msg_id", "")
        chat_id = decrypted_body.get("chat_id", "")
        msg_type_int = decrypted_body.get("msg_type", 0)
        content = decrypted_body.get("content", "")
        sender_type = decrypted_body.get("sender_type", 1)
        sender_id = decrypted_body.get("sender_id", "")

        # Dedup by msg_id
        if msg_id and await _is_duplicate(f"openkf:msg:{msg_id}"):
            logger.info("Duplicate message ignored: msg_id=%s", msg_id)
            return {"duplicate": True}

        # Delegate to auto_chat_service based on sender_type
        from app.services.auto_chat_service import auto_chat_service

        if sender_type == 2:
            # AI reply (customer service → user) — direction=outbound
            await auto_chat_service.handle_ai_reply(
                chat_id=chat_id,
                content=content,
                msg_type=msg_type_int,
                db=db,
                external_msg_id=msg_id,
            )
        else:
            # User reply (user → us) — direction=inbound
            await auto_chat_service.handle_user_reply(
                chat_id=chat_id,
                sender_id=sender_id,
                content=content,
                msg_type=msg_type_int,
                db=db,
                external_msg_id=msg_id,
            )

        logger.info(
            "Processed SPI message: msg_id=%s chat_id=%s sender_type=%s",
            msg_id, chat_id, sender_type,
        )
        return {"duplicate": False}

    async def handle_transfer(self, db: AsyncSession, decrypted_body: dict) -> dict:
        """Handle a transfer-to-human request from chatdoing."""
        chat_id = decrypted_body.get("chat_id", "")
        logger.info("Transfer-to-human requested for chat_id=%s", chat_id)

        lead = await self._resolve_lead_by_chat_id(db, chat_id)
        if lead:
            lead.chat_status = 1  # 人工服务
            if lead.status == "pending":
                lead.status = "assigned"
            await db.flush()

        return {"duplicate": False}

    async def handle_contact_query(self, db: AsyncSession, decrypted_body: dict) -> dict:
        """Query visitor info from our leads table."""
        chat_id = decrypted_body.get("chat_id", "")
        sender_id = decrypted_body.get("sender_id", "")

        lead = await self._resolve_lead_by_chat_id(db, chat_id)
        if not lead:
            # Try by sender_id (user_uid)
            result = await db.execute(
                select(Lead).where(Lead.user_uid == sender_id).limit(1)
            )
            lead = result.scalar_one_or_none()

        if lead:
            return {
                "duplicate": False,
                "data": {
                    "sender_id": lead.user_uid,
                    "nickname": lead.user_nickname,
                    "avatar": lead.user_avatar,
                    "gender": 0,
                    "unionid": "",
                },
            }

        return {
            "duplicate": False,
            "data": {
                "sender_id": sender_id,
                "nickname": "",
                "avatar": "",
                "gender": 0,
                "unionid": "",
            },
        }

    # ── Outbound callback (us → chatdoing) ───────────────────────────────────

    # Retry configuration
    _MAX_RETRIES = 3
    _BACKOFF_DELAYS = [0.1, 0.2]  # 100ms, 200ms between retries

    async def push_message_to_chatdoing(
        self,
        chat_id: str,
        sender_id: str,
        content: str,
        msg_type: int = 0,
        chat_status: int = 1,
    ) -> Tuple[bool, str]:
        """Push a customer-reply event to chatdoing callback endpoint.

        Called when a sales agent sends a message via our platform,
        or when AI initiates/replies to a conversation.

        Args:
            chat_status: 1=human service, 2=AI managed

        Flow:
            1. Build event JSON plaintext
            2. Encrypt with AES-256-GCM (via OpenKFCrypto)
            3. POST encrypted body to chatdoing callback URL
            4. Decrypt & validate response
            5. Retry up to 3 times on failure (same request_id, new nonce/IV/ts)

        Returns:
            (success: bool, msg_id: str) – msg_id is the generated partner
            message ID so callers can persist it.
        """
        crypto = get_crypto()
        local_app_id = settings.OPENKF_LOCAL_APP_ID or settings.OPENKF_APPID
        callback_url = settings.OPENKF_CALLBACK_URL.rstrip("/")
        path = f"/go-im-center/open_customer_service/callback/v1/events/{local_app_id}"
        full_url = f"{callback_url}{path}"

        # 1. Build event payload
        msg_id = f"partner-{uuid.uuid4().hex[:12]}"
        event_payload = {
            "event_type": "event.msg",
            "msg_id": msg_id,
            "chat_id": chat_id,
            "chat_type": 0,
            "chat_status": chat_status,
            "sender_id": sender_id,
            "sender_type": 1,
            "send_time": int(time.time() * 1000),
            "msg_type": msg_type,
            "content": content,
        }
        plaintext = json.dumps(event_payload, ensure_ascii=False).encode("utf-8")

        # Fixed request_id for all retry attempts
        request_id = str(uuid.uuid4())
        last_error: Optional[Exception] = None

        for attempt in range(self._MAX_RETRIES):
            if attempt > 0:
                delay = self._BACKOFF_DELAYS[min(attempt - 1, len(self._BACKOFF_DELAYS) - 1)]
                logger.info(
                    "Retry attempt %d/%d for chat_id=%s (delay=%.1fs, request_id=%s)",
                    attempt + 1, self._MAX_RETRIES, chat_id, delay, request_id,
                )
                await asyncio.sleep(delay)

            try:
                # 2. Encrypt (new nonce/IV/timestamp each attempt, same request_id)
                ciphertext, headers = crypto.encrypt_request(
                    "POST", path, plaintext, request_id=request_id,
                )

                # 3. Send POST request
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        full_url,
                        content=ciphertext,
                        headers={
                            **headers,
                            "Content-Type": "application/octet-stream",
                        },
                    )

                if resp.status_code != 200:
                    logger.warning(
                        "Callback push attempt %d: HTTP %s body=%s",
                        attempt + 1, resp.status_code, resp.text[:200],
                    )
                    last_error = RuntimeError(f"HTTP {resp.status_code}")
                    continue

                # 4. Decrypt & validate response
                resp_headers = dict(resp.headers)
                try:
                    self._validate_response_headers(resp_headers, request_id)
                except OpenKFCryptoError as exc:
                    logger.warning(
                        "Response header validation failed on attempt %d: %s",
                        attempt + 1, exc.message,
                    )
                    last_error = exc
                    continue

                try:
                    resp_plaintext = crypto.decrypt_response(
                        "POST", path, resp_headers, resp.content,
                    )
                except OpenKFCryptoError as exc:
                    logger.warning(
                        "Response decryption failed on attempt %d: %s",
                        attempt + 1, exc.message,
                    )
                    last_error = exc
                    continue

                # 5. Parse response JSON and check code
                try:
                    resp_data = json.loads(resp_plaintext)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Response JSON parse failed on attempt %d: %s",
                        attempt + 1, exc,
                    )
                    last_error = exc
                    continue

                resp_code = resp_data.get("code", -1)
                if resp_code == 0:
                    logger.info(
                        "Callback push success: chat_id=%s request_id=%s",
                        chat_id, request_id,
                    )
                    return True, msg_id
                else:
                    logger.warning(
                        "Callback push attempt %d: business code=%s msg=%s",
                        attempt + 1, resp_code, resp_data.get("msg", ""),
                    )
                    last_error = RuntimeError(
                        f"Business error code={resp_code}: {resp_data.get('msg', '')}"
                    )
                    continue

            except httpx.RequestError as exc:
                logger.warning(
                    "Callback push attempt %d network error: %s", attempt + 1, exc,
                )
                last_error = exc
                continue
            except Exception as exc:
                logger.error(
                    "Callback push attempt %d unexpected error: %s", attempt + 1, exc,
                )
                last_error = exc
                continue

        # All retries exhausted
        logger.error(
            "Callback push failed after %d attempts: chat_id=%s request_id=%s last_error=%s",
            self._MAX_RETRIES, chat_id, request_id, last_error,
        )
        return False, msg_id

    @staticmethod
    def _validate_response_headers(
        resp_headers: dict, expected_request_id: str,
    ) -> None:
        """Validate response headers: direction=response and request_id matches."""
        direction = resp_headers.get(H_DIRECTION, "")
        if direction != "response":
            raise OpenKFCryptoError(
                40001, f"Expected direction=response, got '{direction}'",
            )
        resp_request_id = resp_headers.get(H_REQUEST_ID, "")
        if resp_request_id != expected_request_id:
            raise OpenKFCryptoError(
                40001,
                f"Request ID mismatch: sent={expected_request_id}, "
                f"received={resp_request_id}",
            )

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _resolve_lead_by_chat_id(
        self, db: AsyncSession, chat_id: str
    ) -> Optional[Lead]:
        """Find a Lead by OpenKF chat_id. Checks lead.chat_id first, then chat_messages."""
        if not chat_id:
            return None
        # 1. Check lead.chat_id field (fast path)
        result = await db.execute(
            select(Lead).where(Lead.chat_id == chat_id).limit(1)
        )
        lead = result.scalar_one_or_none()
        if lead:
            return lead

        # 2. Fallback: look up via chat_messages table
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

    async def _get_account_id_for_lead(self, db: AsyncSession, lead_id: int) -> int:
        """Get the douyin_account_id most recently used for a lead."""
        result = await db.execute(
            select(ChatMessage.douyin_account_id)
            .where(ChatMessage.lead_id == lead_id)
            .where(ChatMessage.douyin_account_id > 0)
            .order_by(ChatMessage.sent_at.desc())
            .limit(1)
        )
        row = result.first()
        return row[0] if row else 0


# ── Module-level singleton ────────────────────────────────────────────────────

openkf_service = OpenKFService()
