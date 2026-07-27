"""Append-only audit trail for security-relevant actions."""

import uuid

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLog


def client_ip(request: Request) -> str | None:
    """Caller IP.

    Behind a load balancer this must come from a trusted X-Forwarded-For, which
    is only safe once the proxy is known to strip client-supplied values — until
    that is configured, the direct peer address is the honest answer.
    """
    return request.client.host if request.client else None


class AuditService:
    async def record(
        self,
        db: AsyncSession,
        action: AuditAction,
        *,
        actor_user_id: uuid.UUID | None = None,
        target_type: str | None = None,
        target_id: uuid.UUID | None = None,
        request: Request | None = None,
        context: dict | None = None,
    ) -> None:
        """Append an audit entry. The caller owns the commit."""
        db.add(
            AuditLog(
                actor_user_id=actor_user_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                client_ip=client_ip(request) if request is not None else None,
                context=context or {},
            )
        )
