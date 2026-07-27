"""FastAPI dependencies: settings, DB session, auth, AI services.

Service singletons hang off `app.state` (built in `app.main.create_app`) so tests
swap them by constructing the app with fakes — no monkeypatching.
"""

import uuid
from collections.abc import Callable
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import (
    COMPANY_ROLES,
    SPECIALIST_ROLES,
    Assignment,
    CompanyProfile,
    Match,
    SpecialistProfile,
    User,
)
from app.services.audit import AuditService
from app.services.auth import AuthService
from app.services.intake import IntakeService
from app.services.matching import MatchingEngine
from app.services.ratelimit import RateLimiter, RateLimitExceeded

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_auth_service(request: Request) -> AuthService:
    return request.app.state.auth_service


def get_intake_service(request: Request) -> IntakeService:
    return request.app.state.intake_service


def get_matching_engine(request: Request) -> MatchingEngine:
    return request.app.state.matching_engine


async def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    settings: Settings = request.app.state.settings
    try:
        payload = decode_access_token(settings, credentials.credentials)
    except pyjwt.PyJWTError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from error
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account unavailable")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_specialist_profile(user: CurrentUser, db: DbSession) -> SpecialistProfile:
    if user.role not in SPECIALIST_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "specialist role required")
    profile = await db.scalar(
        select(SpecialistProfile).where(SpecialistProfile.user_id == user.id)
    )
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "create your specialist profile first")
    return profile


async def get_current_company_profile(user: CurrentUser, db: DbSession) -> CompanyProfile:
    if user.role not in COMPANY_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "company role required")
    profile = await db.scalar(select(CompanyProfile).where(CompanyProfile.user_id == user.id))
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "create your company profile first")
    return profile


CurrentSpecialistProfile = Annotated[SpecialistProfile, Depends(get_current_specialist_profile)]
CurrentCompanyProfile = Annotated[CompanyProfile, Depends(get_current_company_profile)]


def get_audit_service(request: Request) -> AuditService:
    return request.app.state.audit_service


AuditDep = Annotated[AuditService, Depends(get_audit_service)]


def rate_limit(scope: str, *, per_user: bool) -> Callable:
    """Dependency enforcing a fixed-window limit.

    Anonymous endpoints key on client IP; authenticated ones key on user id, so
    one abusive account cannot be hidden behind a NAT shared with real users.
    """

    async def dependency(request: Request) -> None:
        settings: Settings = request.app.state.settings
        limiter: RateLimiter = request.app.state.rate_limiter
        if per_user:
            limit = settings.ai_rate_limit
            window = settings.ai_rate_window_seconds
            # falls back to IP when unauthenticated; the auth dependency rejects
            # those requests anyway, this only decides the bucket
            identity = request.headers.get("authorization", "")[-32:] or (
                request.client.host if request.client else "anonymous"
            )
        else:
            limit = settings.login_rate_limit
            window = settings.login_rate_window_seconds
            identity = request.client.host if request.client else "anonymous"
        try:
            await limiter.hit(f"{scope}:{identity}", limit=limit, window_seconds=window)
        except RateLimitExceeded as exceeded:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "too many requests",
                headers={"Retry-After": str(exceeded.retry_after)},
            ) from exceeded

    return dependency


async def load_match(db: AsyncSession, match_id: uuid.UUID) -> Match:
    """Load a match with both parties eagerly attached."""
    match = await db.scalar(
        select(Match)
        .where(Match.id == match_id)
        .options(
            selectinload(Match.specialist).selectinload(SpecialistProfile.user),
            selectinload(Match.assignment).selectinload(Assignment.company),
        )
    )
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "match not found")
    return match


def viewer_role(match: Match, user: User) -> str:
    """'specialist' | 'company' for a party to this match; 404 otherwise.

    Not-a-party is reported as 404 rather than 403 so match existence does not
    leak to strangers.
    """
    if match.specialist.user_id == user.id:
        return "specialist"
    if match.assignment.company.user_id == user.id:
        return "company"
    raise HTTPException(status.HTTP_404_NOT_FOUND, "match not found")
