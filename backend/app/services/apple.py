"""Sign in with Apple: identity-token verification against Apple's JWKS."""

from dataclasses import dataclass
from typing import Protocol

import jwt

from app.core.config import Settings


@dataclass
class AppleIdentity:
    apple_user_id: str  # stable `sub`
    email: str | None


class AppleVerificationError(Exception):
    pass


class AppleIdentityVerifier(Protocol):
    def verify(self, identity_token: str) -> AppleIdentity: ...


class JWKSAppleVerifier:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._jwks_client = jwt.PyJWKClient(settings.apple_jwks_url)

    def verify(self, identity_token: str) -> AppleIdentity:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(identity_token)
            payload = jwt.decode(
                identity_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._settings.apple_client_id,
                issuer=self._settings.apple_issuer,
            )
        except jwt.PyJWTError as error:
            raise AppleVerificationError(str(error)) from error
        return AppleIdentity(apple_user_id=payload["sub"], email=payload.get("email"))
