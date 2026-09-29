"""Signup, login, sessions, Bearer tokens, invites and password changes."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.deps import AnyUser, AppSettings, DbSession, client_ip, get_rate_limiter
from app.errors import Conflict, Forbidden, NotFound, RateLimited, Unauthorized
from app.models.enums import Role
from app.models.workspace import Invite, User, Workspace
from app.permissions import RequestContext, capabilities_for
from app.schemas.auth import (
    ChangePasswordIn,
    InviteAcceptIn,
    LoginIn,
    MeOut,
    SignupIn,
    TokenOut,
)
from app.schemas.user import UserOut
from app.schemas.workspace import WorkspaceOut
from app.security.csrf import CSRFError, enforce_client_header
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.ratelimit import RateLimiter
from app.security.tokens import create_access_token
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])

Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_client_header(request: Request) -> None:
    try:
        enforce_client_header(request)
    except CSRFError:
        raise Forbidden("Missing X-JetStream-Client header", code="csrf_failed") from None


ClientHeader = Depends(require_client_header)


def _check_rate(limiter: RateLimiter, settings: Settings, key: str) -> None:
    decision = limiter.hit(
        key, limit=settings.login_rate_limit, window_s=settings.login_rate_window_s
    )
    if not decision.allowed:
        raise RateLimited(decision.retry_after_s)


def _throttled_authenticate(
    db: Session,
    request: Request,
    settings: Settings,
    limiter: RateLimiter,
    email: str,
    password: str,
) -> User:
    """Rate limit per client IP, then a short per-account backoff after repeated
    failures (never a lockout, so an attacker cannot keep the owner out)."""
    _check_rate(limiter, settings, f"login-ip:{client_ip(request, settings)}")
    account = f"login-account:{email.casefold()}"
    wait = limiter.backoff_s(
        account,
        free_failures=settings.login_backoff_after,
        max_backoff_s=settings.login_backoff_max_s,
    )
    if wait:
        raise RateLimited(wait)
    try:
        user = _authenticate(db, email, password)
    except Unauthorized:
        limiter.record_failure(account)
        raise
    limiter.reset(account)
    return user


def _set_session_cookie(response: Response, settings: Settings, user: User) -> datetime:
    token, expires = create_access_token(
        settings,
        user_id=user.id,
        workspace_id=user.workspace_id,
        token_version=user.token_version,
    )
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.access_token_ttl_min * 60,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return expires


def _me(user: User, workspace: Workspace) -> MeOut:
    return MeOut(
        user=UserOut.model_validate(user),
        workspace=WorkspaceOut.model_validate(workspace),
        role=user.role,
        capabilities=capabilities_for(user.role),
    )


def _unique_slug(db: Session, name: str) -> str:
    base = _SLUG_RE.sub("-", name.casefold()).strip("-")[:60] or "workspace"
    slug = base
    while db.scalar(select(Workspace.id).where(Workspace.slug == slug)) is not None:
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug


def _email_taken(db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(User.email == email)) is not None


def _authenticate(db: Session, email: str, password: str) -> User:
    """Generic 401 on any failure; unknown emails still cost one hash verification."""
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(password, user.password_hash if user else None)
    if user is None or not ok or not user.is_active:
        raise Unauthorized("Invalid email or password", code="invalid_credentials")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = datetime.now(UTC)
    return user


@router.post(
    "/signup",
    status_code=status.HTTP_201_CREATED,
    dependencies=[ClientHeader],
    summary="Create a workspace and its first admin; sets the session cookie",
)
def signup(body: SignupIn, response: Response, db: DbSession, settings: AppSettings) -> MeOut:
    if _email_taken(db, body.email):
        raise Conflict("An account with this email already exists", code="email_taken")
    workspace = Workspace(
        name=body.workspace_name,
        slug=_unique_slug(db, body.workspace_name),
        review_threshold=settings.default_review_threshold,
    )
    db.add(workspace)
    db.flush()
    user = User(
        workspace_id=workspace.id,
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=Role.ADMIN,
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        None,
        "workspace.signup",
        workspace,
        after={"workspace": workspace.name, "admin": user.email},
        workspace_id=workspace.id,
        actor_label=user.email,
    )
    db.commit()
    _set_session_cookie(response, settings, user)
    return _me(user, workspace)


@router.post("/login", dependencies=[ClientHeader], summary="Log in; sets the session cookie")
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    limiter: Limiter,
) -> MeOut:
    user = _throttled_authenticate(db, request, settings, limiter, body.email, body.password)
    db.commit()
    _set_session_cookie(response, settings, user)
    return _me(user, user.workspace)


@router.post(
    "/token",
    summary="OAuth2 password flow returning a Bearer token (scripts, Swagger, tests)",
)
def token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    db: DbSession,
    settings: AppSettings,
    limiter: Limiter,
) -> TokenOut:
    email = form.username.strip().lower()
    user = _throttled_authenticate(db, request, settings, limiter, email, form.password)
    db.commit()
    access_token, expires = create_access_token(
        settings,
        user_id=user.id,
        workspace_id=user.workspace_id,
        token_version=user.token_version,
    )
    return TokenOut(access_token=access_token, expires_at=expires)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear the session cookie and revoke the user's tokens (every session)",
)
def logout(ctx: AnyUser, db: DbSession, settings: AppSettings) -> Response:
    """Bumps `token_version`, so this token (and the user's other sessions and
    Bearer tokens) stops working even if it was copied before logout."""
    ctx.user.token_version += 1
    audit.record(db, ctx, "user.logout", ctx.user, after={"token_version_bumped": True})
    db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        settings.cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/me", summary="The caller, their workspace, role and capabilities")
def me(ctx: AnyUser) -> MeOut:
    return _me(ctx.user, ctx.workspace)


@router.post(
    "/invites/accept",
    status_code=status.HTTP_201_CREATED,
    dependencies=[ClientHeader],
    summary="Accept an invite: creates the user and sets the session cookie",
)
def accept_invite(
    body: InviteAcceptIn,
    request: Request,
    response: Response,
    db: DbSession,
    settings: AppSettings,
    limiter: Limiter,
) -> MeOut:
    _check_rate(limiter, settings, f"invite:{client_ip(request, settings)}")
    invite = db.scalar(select(Invite).where(Invite.token_hash == hash_invite_token(body.token)))
    now = datetime.now(UTC)
    if (
        invite is None
        or invite.accepted_at is not None
        or invite.revoked_at is not None
        or invite.expires_at <= now
    ):
        raise NotFound("Invite not found or expired", code="invite_invalid")
    if _email_taken(db, invite.email):
        raise Conflict("An account with this email already exists", code="email_taken")

    user = User(
        workspace_id=invite.workspace_id,
        email=invite.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=invite.role,
        last_login_at=now,
    )
    db.add(user)
    db.flush()
    invite.accepted_at = now
    invite.accepted_user_id = user.id
    audit.record(
        db,
        None,
        "invite.accept",
        invite,
        after={"email": user.email, "role": user.role.value},
        workspace_id=invite.workspace_id,
        actor_label=user.email,
        ip=client_ip(request, settings),
    )
    db.commit()
    _set_session_cookie(response, settings, user)
    return _me(user, user.workspace)


@router.post(
    "/change-password",
    summary="Change password; signs out other sessions and re-issues the cookie",
)
def change_password(
    body: ChangePasswordIn,
    response: Response,
    ctx: AnyUser,
    db: DbSession,
    settings: AppSettings,
) -> MeOut:
    user = ctx.user
    if not verify_password(body.current_password, user.password_hash):
        raise Unauthorized("Current password is incorrect", code="invalid_credentials")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    _record_password_change(db, ctx)
    db.commit()
    _set_session_cookie(response, settings, user)
    return _me(user, ctx.workspace)


def _record_password_change(db: Session, ctx: RequestContext) -> None:
    audit.record(db, ctx, "user.change_password", ctx.user, after={"token_version_bumped": True})
