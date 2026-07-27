"""Push notifications behind a protocol.

APNs in production, a recording fake in tests. Delivery is best-effort by
design: a notification that fails must never fail the action that triggered it —
nobody should lose a signed contract because Apple was briefly unreachable.
"""

import uuid
from dataclasses import dataclass, field
from typing import Protocol

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PushMessage:
    user_id: uuid.UUID
    title: str
    body: str
    data: dict = field(default_factory=dict)


class PushSender(Protocol):
    async def send(self, message: PushMessage, tokens: list[str]) -> None: ...


class APNsSender:
    def __init__(self, key_id: str, team_id: str, bundle_id: str, private_key: str):
        self._configured = all((key_id, team_id, bundle_id, private_key))
        self._bundle_id = bundle_id

    async def send(
        self, message: PushMessage, tokens: list[str]
    ) -> None:  # pragma: no cover - requires Apple credentials
        if not self._configured:
            logger.warning("apns_not_configured", user_id=str(message.user_id))
            return
        raise NotImplementedError(
            "APNsSender needs the signing key wired up; use MATCHIT_PUSH_BACKEND=fake "
            "outside production"
        )


@dataclass
class FakePushSender:
    sent: list[tuple[PushMessage, list[str]]] = field(default_factory=list)

    async def send(self, message: PushMessage, tokens: list[str]) -> None:
        self.sent.append((message, tokens))


@dataclass
class NullPushSender:
    async def send(self, message: PushMessage, tokens: list[str]) -> None:
        return None


def build_push_sender(settings) -> PushSender:
    if settings.push_backend == "apns":
        return APNsSender(
            settings.apns_key_id,
            settings.apns_team_id,
            settings.apns_bundle_id,
            settings.apns_private_key,
        )
    if settings.push_backend == "fake":
        return FakePushSender()
    if settings.push_backend == "off":
        return NullPushSender()
    raise ValueError(f"unknown push_backend: {settings.push_backend}")
