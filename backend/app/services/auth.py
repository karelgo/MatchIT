"""Authentication: registration, login, token rotation, Sign in with Apple."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models import RefreshToken, User, UserRole
from app.services.apple import AppleIdentityVerifier


class AuthError(Exception):
    """Raised for any credential failure; mapped to 401 at the API layer."""


class EmailTakenError(Exception):
    pass


class RoleNotSelfAssignable(Exception):
    """Privileged roles cannot be claimed at registration."""


# Public registration must never mint privilege. Admins are provisioned
# out-of-band; nothing in the sign-up flow can grant this role.
SELF_ASSIGNABLE_ROLES = frozenset(UserRole) - {UserRole.ADMIN}


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    user: User


class AuthService:
    def __init__(self, settings: Settings, apple_verifier: AppleIdentityVerifier):
        self._settings = settings
        self._apple = apple_verifier

    async def register(
        self, db: AsyncSession, *, email: str, password: str, full_name: str, role: UserRole
    ) -> TokenPair:
        if role not in SELF_ASSIGNABLE_ROLES:
            raise RoleNotSelfAssignable(role.value)
        email = email.strip().lower()
        existing = await db.scalar(select(User).where(User.email == email))
        if existing is not None:
            raise EmailTakenError(email)
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name.strip(),
            role=role,
        )
        db.add(user)
        await db.flush()
        return await self._issue_tokens(db, user)

    async def login(self, db: AsyncSession, *, email: str, password: str) -> TokenPair:
        user = await db.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None or user.password_hash is None or not user.is_active:
            raise AuthError("invalid credentials")
        if not verify_password(password, user.password_hash):
            raise AuthError("invalid credentials")
        return await self._issue_tokens(db, user)

    async def login_with_apple(
        self, db: AsyncSession, *, identity_token: str, full_name: str | None, role: UserRole
    ) -> TokenPair:
        if role not in SELF_ASSIGNABLE_ROLES:
            raise RoleNotSelfAssignable(role.value)
        identity = self._apple.verify(identity_token)
        user = await db.scalar(select(User).where(User.apple_user_id == identity.apple_user_id))
        if user is None and identity.email:
            # first Apple sign-in for an existing email account: link them
            user = await db.scalar(select(User).where(User.email == identity.email.lower()))
            if user is not None:
                user.apple_user_id = identity.apple_user_id
        if user is None:
            email = identity.email or f"{identity.apple_user_id}@privaterelay.appleid.com"
            user = User(
                email=email.lower(),
                apple_user_id=identity.apple_user_id,
                full_name=(full_name or "").strip() or "Apple User",
                role=role,
                is_verified=True,
            )
            db.add(user)
            await db.flush()
        if not user.is_active:
            raise AuthError("account disabled")
        return await self._issue_tokens(db, user)

    async def refresh(self, db: AsyncSession, *, refresh_token: str) -> TokenPair:
        token_hash = hash_refresh_token(refresh_token)
        stored = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        now = datetime.now(UTC)
        if stored is None or stored.revoked_at is not None:
            raise AuthError("invalid refresh token")
        expires_at = stored.expires_at
        if expires_at.tzinfo is None:  # SQLite loses tz info
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < now:
            raise AuthError("refresh token expired")
        user = await db.get(User, stored.user_id)
        if user is None or not user.is_active:
            raise AuthError("account disabled")
        stored.revoked_at = now  # rotation: old token dies with the new issue
        return await self._issue_tokens(db, user)

    async def logout(self, db: AsyncSession, *, refresh_token: str) -> None:
        token_hash = hash_refresh_token(refresh_token)
        stored = await db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(UTC)
        await db.commit()

    async def _issue_tokens(self, db: AsyncSession, user: User) -> TokenPair:
        access = create_access_token(self._settings, user.id, user.role.value)
        refresh = generate_refresh_token()
        db.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_refresh_token(refresh),
                expires_at=datetime.now(UTC)
                + timedelta(days=self._settings.refresh_token_ttl_days),
            )
        )
        await db.commit()
        return TokenPair(access_token=access, refresh_token=refresh, user=user)


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)
