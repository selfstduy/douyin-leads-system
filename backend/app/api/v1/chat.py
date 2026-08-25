"""Chat API routes and WebSocket endpoint."""
import json
import logging
from typing import Dict, List

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, get_current_user
from app.schemas.chat import ChatMessageCreate, ChatMessageOut
from app.schemas.common import ResponseModel, PageResponse
from app.services import chat_service, douyin_account_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["聊天"])


# ── WebSocket Connection Manager ──────────────────────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections per user."""

    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            self.active_connections[user_id] = [
                ws for ws in self.active_connections[user_id] if ws != websocket
            ]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

    async def send_to_user(self, user_id: int, message: dict):
        if user_id in self.active_connections:
            for ws in self.active_connections[user_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    pass

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected users (for unassigned AI conversations)."""
        for user_id, connections in self.active_connections.items():
            for ws in connections:
                try:
                    await ws.send_json(message)
                except Exception:
                    pass


manager = ConnectionManager()


# ── WebSocket endpoint ─────────────────────────────────────────────────────────

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive, listen for client pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception:
        manager.disconnect(websocket, user_id)


# ── REST endpoints ─────────────────────────────────────────────────────────────

@router.get("/sessions", response_model=ResponseModel)
async def get_sessions(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get my chat sessions with last message preview."""
    sessions = await chat_service.get_chat_sessions(db, current_user.id)
    return ResponseModel(data=sessions)


@router.get("/messages/{lead_id}", response_model=PageResponse)
async def get_messages(
    lead_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get paginated message history for a lead."""
    result = await chat_service.get_messages(db, lead_id, page, page_size)
    return PageResponse(
        data=result["messages"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.post("/send", response_model=ResponseModel)
async def send_message(
    body: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Send a chat message to a lead."""
    # Determine which douyin account to use
    account_id = body.douyin_account_id
    if not account_id:
        # Use first available account
        accounts = await douyin_account_service.get_user_available_accounts(
            db, current_user.id
        )
        if not accounts:
            return ResponseModel(code=400, message="没有可用的抖音账号，请联系管理员分配")
        account_id = accounts[0].id

    result = await chat_service.send_message(
        db,
        lead_id=body.lead_id,
        douyin_account_id=account_id,
        content=body.content,
    )

    if not result["success"]:
        return ResponseModel(code=400, message=result.get("error", "发送失败"))

    # Push via WebSocket to the user
    await manager.send_to_user(current_user.id, {
        "type": "new_message",
        "data": {
            "id": result.get("message_id"),
            "lead_id": body.lead_id,
            "direction": "outbound",
            "content": body.content,
            "status": "sent",
        }
    })

    resp_data = {
        "message_id": result.get("message_id"),
        "remaining": result.get("remaining"),
    }
    if result.get("work_hours_warning"):
        resp_data["warning"] = "当前为非工作时间，请注意发送频率"

    return ResponseModel(message="消息已发送", data=resp_data)


@router.get("/accounts", response_model=ResponseModel)
async def get_available_accounts(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get my available Douyin accounts for sending messages."""
    accounts = await douyin_account_service.get_user_available_accounts(db, current_user.id)
    return ResponseModel(data=[
        {
            "id": acc.id,
            "douyin_uid": acc.douyin_uid,
            "nickname": acc.nickname,
            "login_status": acc.login_status,
        }
        for acc in accounts
    ])


@router.get("/{lead_id}/messages", response_model=PageResponse)
async def get_messages_legacy(
    lead_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get chat messages (legacy path)."""
    result = await chat_service.get_messages(db, lead_id, page, page_size)
    return PageResponse(
        data=result["messages"],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )
