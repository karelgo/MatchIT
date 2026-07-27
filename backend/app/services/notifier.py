"""Domain-level notifications: what to say, to whom, and when."""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DeviceToken
from app.services.notifications import PushMessage, PushSender

logger = structlog.get_logger(__name__)


class Notifier:
    def __init__(self, sender: PushSender):
        self._sender = sender

    async def notify(
        self, db: AsyncSession, user_id: uuid.UUID, *, title: str, body: str, data: dict
    ) -> None:
        """Best-effort delivery.

        A failed push must never fail the action that triggered it: nobody should
        lose a signed contract because Apple was briefly unreachable.
        """
        tokens = list(
            await db.scalars(select(DeviceToken.token).where(DeviceToken.user_id == user_id))
        )
        if not tokens:
            return
        try:
            await self._sender.send(
                PushMessage(user_id=user_id, title=title, body=body, data=data), tokens
            )
        except Exception:  # noqa: BLE001 - deliberate: delivery is best-effort
            logger.warning("push_delivery_failed", user_id=str(user_id), exc_info=True)

    async def mutual_match(
        self, db: AsyncSession, user_id: uuid.UUID, *, counterpart: str, match_id: uuid.UUID
    ) -> None:
        await self.notify(
            db,
            user_id,
            title="It's a match",
            body=f"You and {counterpart} both said yes. Chat is open.",
            data={"type": "mutual_match", "match_id": str(match_id)},
        )

    async def new_message(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        *,
        sender_name: str,
        preview: str,
        conversation_id: uuid.UUID,
    ) -> None:
        await self.notify(
            db,
            user_id,
            title=sender_name,
            body=preview[:120],
            data={"type": "message", "conversation_id": str(conversation_id)},
        )

    async def contract_signed(
        self, db: AsyncSession, user_id: uuid.UUID, *, match_id: uuid.UUID, is_active: bool
    ) -> None:
        await self.notify(
            db,
            user_id,
            title="Contract signed" if is_active else "Signature received",
            body=(
                "Both parties have signed — the engagement is active."
                if is_active
                else "The other party signed. Your signature is next."
            ),
            data={"type": "contract", "match_id": str(match_id)},
        )
