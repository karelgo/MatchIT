import asyncio
import contextlib
import uuid
from typing import Annotated

import jwt as pyjwt
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import CurrentUser, DbSession
from app.core.security import decode_access_token
from app.models import User
from app.schemas.api import ConversationResponse, MessageCreateRequest, MessageResponse
from app.services.chat import ChatService, ConversationAccessError

router = APIRouter(tags=["chat"])


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(user: CurrentUser, db: DbSession, chat: ChatServiceDep):
    return await chat.list_for_user(db, user)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    chat: ChatServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    try:
        conversation = await chat.get_for_user(db, conversation_id, user)
    except ConversationAccessError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found") from None
    return await chat.list_messages(db, conversation, limit=limit)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: uuid.UUID,
    body: MessageCreateRequest,
    user: CurrentUser,
    db: DbSession,
    chat: ChatServiceDep,
):
    try:
        conversation = await chat.get_for_user(db, conversation_id, user)
    except ConversationAccessError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found") from None
    return await chat.send_message(db, conversation, user, body.content)


async def _authenticate_ws(websocket: WebSocket, db: AsyncSession) -> User | None:
    token = websocket.query_params.get("token", "")
    try:
        payload = decode_access_token(websocket.app.state.settings, token)
    except pyjwt.PyJWTError:
        return None
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        return None
    return user


@router.websocket("/ws/conversations/{conversation_id}")
async def chat_socket(websocket: WebSocket, conversation_id: uuid.UUID):
    """Live chat: client sends {"content": str}; every party receives the
    broadcast MessageResponse JSON (including the sender, as delivery echo).

    Sessions are opened per operation, never for the socket's lifetime — a chat
    socket is mostly idle, and holding a pooled connection open for each one
    would exhaust the pool long before the server ran out of sockets. It also
    means access is re-checked on every message rather than only at connect.
    """
    chat: ChatService = websocket.app.state.chat_service
    sessionmaker: async_sessionmaker[AsyncSession] = websocket.app.state.sessionmaker

    async with sessionmaker() as db:
        user = await _authenticate_ws(websocket, db)
        if user is None:
            await websocket.close(code=4401)
            return
        try:
            await chat.get_for_user(db, conversation_id, user)
        except ConversationAccessError:
            await websocket.close(code=4404)
            return
        user_id = user.id

    await websocket.accept()
    async with chat.pubsub.subscribe(chat.channel(conversation_id)) as stream:

        async def forward() -> None:
            async for payload in stream:
                await websocket.send_text(payload)

        forwarder = asyncio.create_task(forward())
        try:
            while True:
                data = await websocket.receive_json()
                try:
                    body = MessageCreateRequest.model_validate(data)
                except ValidationError:
                    continue  # ignore malformed frames rather than dropping the socket
                async with sessionmaker() as db:
                    sender = await db.get(User, user_id)
                    if sender is None or not sender.is_active:
                        break
                    try:
                        conversation = await chat.get_for_user(db, conversation_id, sender)
                    except ConversationAccessError:
                        break  # access revoked mid-session
                    await chat.send_message(db, conversation, sender, body.content)
        except WebSocketDisconnect:
            pass
        finally:
            forwarder.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await forwarder
