"""Admin portal API.

The portal itself is a thin client over these endpoints; everything it needs to
show is computed here so a future web UI has no business logic of its own.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.deps import AuditDep, CurrentUser, DbSession
from app.models import AuditAction, AuditLog, User, UserRole
from app.schemas.api import (
    AdminAuditEntry,
    AdminMetricsResponse,
    AdminUserView,
    FunnelView,
)
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        # 404, not 403: the admin surface should not confirm its own existence
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


@router.get("/metrics", response_model=AdminMetricsResponse)
async def metrics(admin: AdminUser, db: DbSession, request: Request):
    analytics: AnalyticsService = request.app.state.analytics_service
    funnel = await analytics.funnel(db)
    return AdminMetricsResponse(
        funnel=FunnelView(
            specialists=funnel.specialists,
            companies=funnel.companies,
            assignments=funnel.assignments,
            matches_suggested=funnel.matches_suggested,
            matches_mutual=funnel.matches_mutual,
            interviews_completed=funnel.interviews_completed,
            contracts_active=funnel.contracts_active,
        ),
        conversion=funnel.conversion_rates(),
        quality=await analytics.quality(db),
        users_by_role=await analytics.user_counts(db),
        mean_time_to_contract_hours=await analytics.time_to_contract_hours(db),
        ai_calls_by_feature=await request.app.state.usage_counter.totals(),
    )


@router.get("/users", response_model=list[AdminUserView])
async def list_users(
    admin: AdminUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    role: UserRole | None = None,
    is_active: bool | None = None,
):
    statement = select(User).order_by(User.created_at.desc())
    if role is not None:
        statement = statement.where(User.role == role)
    if is_active is not None:
        statement = statement.where(User.is_active == is_active)
    users = await db.scalars(statement.limit(limit).offset(offset))
    return [AdminUserView.model_validate(u, from_attributes=True) for u in users]


@router.post("/users/{user_id}/suspend", response_model=AdminUserView)
async def suspend_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    db: DbSession,
    audit: AuditDep,
    request: Request,
):
    """Suspend an account. Reversible, and always audited."""
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if target.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "an admin cannot suspend themselves")
    target.is_active = False
    await audit.record(
        db,
        AuditAction.USER_SUSPENDED,
        actor_user_id=admin.id,
        target_type="user",
        target_id=target.id,
        request=request,
    )
    await db.commit()
    return AdminUserView.model_validate(target, from_attributes=True)


@router.post("/users/{user_id}/reinstate", response_model=AdminUserView)
async def reinstate_user(
    user_id: uuid.UUID,
    admin: AdminUser,
    db: DbSession,
    audit: AuditDep,
    request: Request,
):
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    target.is_active = True
    await audit.record(
        db,
        AuditAction.USER_REINSTATED,
        actor_user_id=admin.id,
        target_type="user",
        target_id=target.id,
        request=request,
    )
    await db.commit()
    return AdminUserView.model_validate(target, from_attributes=True)


@router.get("/audit", response_model=list[AdminAuditEntry])
async def search_audit(
    admin: AdminUser,
    db: DbSession,
    action: AuditAction | None = None,
    actor_user_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    statement = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action is not None:
        statement = statement.where(AuditLog.action == action)
    if actor_user_id is not None:
        statement = statement.where(AuditLog.actor_user_id == actor_user_id)
    rows = await db.scalars(statement.limit(limit).offset(offset))
    return [AdminAuditEntry.model_validate(r, from_attributes=True) for r in rows]
