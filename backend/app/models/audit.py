import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import JsonVariant, TimestampedBase


class AuditAction(enum.StrEnum):
    USER_REGISTERED = "user_registered"
    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    CONTRACT_SIGNED = "contract_signed"
    DATA_EXPORTED = "data_exported"
    ACCOUNT_DELETED = "account_deleted"


class AuditLog(TimestampedBase):
    """Append-only record of security-relevant actions.

    `actor_user_id` is intentionally SET NULL on user deletion rather than
    cascading: erasing an account must not erase the evidence that it existed and
    what it did, which is exactly what an audit trail is for. Nothing here
    identifies the user beyond the (now dangling) id.
    """

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_action_created", "action", "created_at"),)

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction, native_enum=False, length=30))
    target_type: Mapped[str | None] = mapped_column(String(50), default=None)
    target_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    client_ip: Mapped[str | None] = mapped_column(String(45), default=None)  # IPv6-sized
    context: Mapped[dict] = mapped_column(JsonVariant, default=dict)
