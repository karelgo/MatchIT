"""Chat: conversations opened on mutual matches, live delivery via pub/sub."""

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Assignment,
    CompanyProfile,
    Conversation,
    Match,
    Message,
    SpecialistProfile,
    User,
)
from app.schemas.api import ConversationResponse, MessageResponse
from app.services.pubsub import PubSub


class ConversationAccessError(Exception):
    """Conversation missing or the user is not a party; mapped to 404."""


def _conversation_options():
    return (
        selectinload(Conversation.match)
        .selectinload(Match.specialist)
        .selectinload(SpecialistProfile.user),
        selectinload(Conversation.match)
        .selectinload(Match.assignment)
        .selectinload(Assignment.company),
    )


def _parties(conversation: Conversation) -> tuple[uuid.UUID, uuid.UUID]:
    """(specialist_user_id, company_user_id) for a fully loaded conversation."""
    match = conversation.match
    return match.specialist.user_id, match.assignment.company.user_id


def _assignment_title(conversation: Conversation) -> str:
    requirements = conversation.match.assignment.requirements
    roles = requirements.get("roles") or []
    if roles:
        return roles[0].get("title", "Assignment")
    return (requirements.get("summary") or "Assignment")[:80]


class ChatService:
    def __init__(self, pubsub: PubSub, notifier=None):
        self.pubsub = pubsub
        self.notifier = notifier

    @staticmethod
    def channel(conversation_id: uuid.UUID) -> str:
        return f"chat:{conversation_id}"

    async def ensure_conversation(self, db: AsyncSession, match_id: uuid.UUID) -> Conversation:
        """Idempotently open the chat thread for a mutual match."""
        existing = await db.scalar(select(Conversation).where(Conversation.match_id == match_id))
        if existing is not None:
            return existing
        conversation = Conversation(match_id=match_id)
        db.add(conversation)
        await db.flush()
        return conversation

    async def get_for_user(
        self, db: AsyncSession, conversation_id: uuid.UUID, user: User
    ) -> Conversation:
        conversation = await db.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(*_conversation_options())
        )
        if conversation is None or user.id not in _parties(conversation):
            raise ConversationAccessError(str(conversation_id))
        return conversation

    async def list_for_user(self, db: AsyncSession, user: User) -> list[ConversationResponse]:
        conversations = await db.scalars(
            select(Conversation)
            .join(Match, Conversation.match_id == Match.id)
            .join(SpecialistProfile, Match.specialist_id == SpecialistProfile.id)
            .join(Assignment, Match.assignment_id == Assignment.id)
            .join(CompanyProfile, Assignment.company_id == CompanyProfile.id)
            .where(
                or_(SpecialistProfile.user_id == user.id, CompanyProfile.user_id == user.id)
            )
            .options(*_conversation_options())
            .order_by(Conversation.updated_at.desc())
        )
        responses = []
        for conversation in conversations:
            last = await db.scalar(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.desc())
                .limit(1)
            )
            responses.append(self._to_response(conversation, user, last))
        return responses

    def _to_response(
        self, conversation: Conversation, user: User, last: Message | None
    ) -> ConversationResponse:
        specialist_user_id, _ = _parties(conversation)
        if user.id == specialist_user_id:
            counterpart = conversation.match.assignment.company.name
        else:
            counterpart = conversation.match.specialist.user.full_name
        return ConversationResponse(
            id=conversation.id,
            match_id=conversation.match_id,
            counterpart_name=counterpart,
            assignment_title=_assignment_title(conversation),
            last_message=last.content if last else None,
            last_message_at=last.created_at if last else None,
            created_at=conversation.created_at,
        )

    async def list_messages(
        self, db: AsyncSession, conversation: Conversation, limit: int = 100
    ) -> list[MessageResponse]:
        messages = await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .options(selectinload(Message.sender))
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        ordered = list(reversed(list(messages)))
        return [self._message_response(m, m.sender) for m in ordered]

    async def send_message(
        self, db: AsyncSession, conversation: Conversation, sender: User, content: str
    ) -> MessageResponse:
        message = Message(conversation_id=conversation.id, sender_id=sender.id, content=content)
        db.add(message)
        await db.flush()  # populates message.id / created_at defaults
        conversation.updated_at = message.created_at
        await db.commit()
        response = self._message_response(message, sender)
        await self.pubsub.publish(self.channel(conversation.id), response.model_dump_json())
        if self.notifier is not None:
            specialist_user_id, company_user_id = _parties(conversation)
            recipient = (
                company_user_id if sender.id == specialist_user_id else specialist_user_id
            )
            await self.notifier.new_message(
                db,
                recipient,
                sender_name=sender.full_name,
                preview=message.content,
                conversation_id=conversation.id,
            )
        return response

    @staticmethod
    def _message_response(message: Message, sender: User) -> MessageResponse:
        return MessageResponse(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_id=sender.id,
            sender_name=sender.full_name,
            content=message.content,
            created_at=message.created_at,
        )
