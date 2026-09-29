"""Session tokens: HS256 JWTs carried in the `js_session` cookie or a Bearer header."""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.config import Settings

ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ["sub", "wid", "tv", "iat", "exp", "jti"]


class InvalidToken(Exception):
    """Token is missing, malformed, expired or signed with another key."""


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    token_version: int
    issued_at: datetime
    expires_at: datetime
    jti: str


def create_access_token(
    settings: Settings,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    token_version: int,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    """Return the encoded token and its expiry."""
    issued = now or datetime.now(UTC)
    expires = issued + timedelta(minutes=settings.access_token_ttl_min)
    payload = {
        "sub": str(user_id),
        "wid": str(workspace_id),
        "tv": token_version,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    token = jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=ALGORITHM)
    return token, expires


def decode_access_token(settings: Settings, token: str) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": _REQUIRED_CLAIMS},
        )
        return TokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            workspace_id=uuid.UUID(payload["wid"]),
            token_version=int(payload["tv"]),
            issued_at=datetime.fromtimestamp(payload["iat"], UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
            jti=str(payload["jti"]),
        )
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise InvalidToken(str(exc)) from exc
