from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import AuditDep, DbSession, get_auth_service, rate_limit
from app.models import AuditAction
from app.schemas.api import (
    AppleSignInRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.services.apple import AppleVerificationError
from app.services.auth import AuthError, AuthService, EmailTakenError, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"])

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def _to_response(pair: TokenPair) -> TokenResponse:
    return TokenResponse.model_validate(
        {
            "access_token": pair.access_token,
            "refresh_token": pair.refresh_token,
            "user": pair.user,
        },
        from_attributes=True,
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", per_user=False))],
)
async def register(
    body: RegisterRequest, db: DbSession, auth: AuthServiceDep, audit: AuditDep, request: Request
):
    try:
        pair = await auth.register(
            db, email=body.email, password=body.password, full_name=body.full_name, role=body.role
        )
    except EmailTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered") from None
    await audit.record(
        db, AuditAction.USER_REGISTERED, actor_user_id=pair.user.id, request=request
    )
    await db.commit()
    return _to_response(pair)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("login", per_user=False))],
)
async def login(
    body: LoginRequest, db: DbSession, auth: AuthServiceDep, audit: AuditDep, request: Request
):
    try:
        pair = await auth.login(db, email=body.email, password=body.password)
    except AuthError:
        # Record the failure without the password or a user id we cannot trust
        await audit.record(
            db, AuditAction.LOGIN_FAILED, request=request, context={"email": body.email}
        )
        await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials") from None
    await audit.record(
        db, AuditAction.LOGIN_SUCCEEDED, actor_user_id=pair.user.id, request=request
    )
    await db.commit()
    return _to_response(pair)


@router.post("/apple", response_model=TokenResponse)
async def apple_sign_in(body: AppleSignInRequest, db: DbSession, auth: AuthServiceDep):
    try:
        pair = await auth.login_with_apple(
            db, identity_token=body.identity_token, full_name=body.full_name, role=body.role
        )
    except (AppleVerificationError, AuthError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "apple sign-in failed") from None
    return _to_response(pair)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: DbSession, auth: AuthServiceDep):
    try:
        pair = await auth.refresh(db, refresh_token=body.refresh_token)
    except AuthError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token") from None
    return _to_response(pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, db: DbSession, auth: AuthServiceDep):
    await auth.logout(db, refresh_token=body.refresh_token)
