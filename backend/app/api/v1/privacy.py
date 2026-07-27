from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import AuditDep, CurrentUser, DbSession
from app.models import AuditAction
from app.services.privacy import ErasureBlocked, PrivacyService

router = APIRouter(tags=["privacy"])


def get_privacy_service(request: Request) -> PrivacyService:
    return request.app.state.privacy_service


PrivacyDep = Annotated[PrivacyService, Depends(get_privacy_service)]


@router.get("/users/me/export")
async def export_my_data(
    user: CurrentUser,
    db: DbSession,
    privacy: PrivacyDep,
    audit: AuditDep,
    request: Request,
) -> dict:
    """GDPR Article 15/20 — everything held about the caller, as portable JSON."""
    data = await privacy.export(db, user)
    await audit.record(
        db, AuditAction.DATA_EXPORTED, actor_user_id=user.id, request=request
    )
    await db.commit()
    return data


@router.delete("/users/me", status_code=status.HTTP_204_NO_CONTENT)
async def erase_my_account(
    user: CurrentUser,
    db: DbSession,
    privacy: PrivacyDep,
    audit: AuditDep,
    request: Request,
) -> Response:
    """GDPR Article 17 — erase the account and everything cascading from it."""
    # Audit first: the entry must survive the row it describes, and the
    # actor FK is SET NULL rather than CASCADE precisely so it does.
    await audit.record(
        db,
        AuditAction.ACCOUNT_DELETED,
        actor_user_id=user.id,
        request=request,
        context={"role": user.role.value},
    )
    await db.commit()
    try:
        await privacy.erase(db, user)
    except ErasureBlocked as blocked:
        raise HTTPException(status.HTTP_409_CONFLICT, str(blocked)) from blocked
    return Response(status_code=status.HTTP_204_NO_CONTENT)
