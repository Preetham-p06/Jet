"""Public client view of a sent proposal. No authentication; the token is the secret.

Unknown, revoked, draft and expired tokens all return the same 404; a
superseded proposal returns 410. Responses are never cached or indexed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response

from app.api.routes.auth import ClientHeader
from app.deps import AppSettings, client_ip, get_rate_limiter
from app.errors import RateLimited, not_implemented
from app.schemas.proposal import PublicAcceptIn, PublicProposalOut
from app.security.ratelimit import RateLimiter

router = APIRouter(prefix="/public", tags=["public"])

# The middleware also sets these on every public response, errors included.
PUBLIC_HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
}

Token = Annotated[str, Path(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]


def public_guard(
    request: Request,
    response: Response,
    settings: AppSettings,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> None:
    """Rate limit per client IP and set the no-store/noindex headers."""
    decision = limiter.hit(
        f"public:{client_ip(request)}",
        limit=settings.public_rate_limit,
        window_s=settings.public_rate_window_s,
    )
    if not decision.allowed:
        raise RateLimited(decision.retry_after_s)
    response.headers.update(PUBLIC_HEADERS)


PublicGuard = Depends(public_guard)


@router.get(
    "/proposals/{token}",
    dependencies=[PublicGuard],
    summary="Client view of a proposal (whitelisted fields only)",
)
def get_public_proposal(token: Token) -> PublicProposalOut:
    not_implemented("Public proposal")


@router.post(
    "/proposals/{token}/accept",
    dependencies=[PublicGuard, ClientHeader],
    summary="Client accepts one option",
)
def accept_public_proposal(token: Token, body: PublicAcceptIn) -> PublicProposalOut:
    not_implemented("Public proposal acceptance")
