"""Users and invites (admin only). Invites are shared by copying the link; no email is sent."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Response, status
from sqlalchemy import func, select

from app.api.params import PageParams
from app.api.routes.auth import hash_invite_token
from app.deps import Admin, AppSettings, DbSession
from app.errors import Conflict
from app.models.enums import Role
from app.models.workspace import Invite, User
from app.permissions import get_owned, scoped
from app.schemas.common import Page
from app.schemas.user import (
    InviteCreate,
    InviteCreatedOut,
    InviteOut,
    InviteState,
    UserOut,
    UserPatch,
)
from app.services import audit

router = APIRouter(tags=["users"])


@router.get("/users", summary="List users")
def list_users(ctx: Admin, db: DbSession, page: PageParams) -> Page[UserOut]:
    stmt = scoped(select(User), ctx)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(User.created_at).limit(page.limit).offset(page.offset))
    return Page(items=[UserOut.model_validate(u) for u in rows], total=total)


@router.patch("/users/{user_id}", summary="Change role or active state")
def update_user(user_id: uuid.UUID, body: UserPatch, ctx: Admin, db: DbSession) -> UserOut:
    user = get_owned(db, User, user_id, ctx)
    before = audit.snapshot(user, ("role", "is_active"))
    demoting = body.role is not None and body.role is not Role.ADMIN
    deactivating = body.is_active is False
    if user.role is Role.ADMIN and user.is_active and (demoting or deactivating):
        other_admins = db.scalar(
            scoped(select(func.count()).select_from(User), ctx, User).where(
                User.role == Role.ADMIN, User.is_active.is_(True), User.id != user.id
            )
        )
        if not other_admins:
            raise Conflict("The workspace needs at least one active admin", code="last_admin")

    if body.role is not None:
        user.role = body.role
    if body.is_active is not None and body.is_active != user.is_active:
        user.is_active = body.is_active
        if not body.is_active:
            user.token_version += 1  # sign the user out everywhere
    old, new = audit.diff(before, audit.snapshot(user, ("role", "is_active")))
    if new:
        audit.record(db, ctx, "user.update", user, old, new)
    db.commit()
    return UserOut.model_validate(user)


def _invite_state(invite: Invite, now: datetime) -> InviteState:
    if invite.accepted_at is not None:
        return "accepted"
    if invite.revoked_at is not None:
        return "revoked"
    return "expired" if invite.expires_at <= now else "pending"


def _invite_out(invite: Invite, now: datetime) -> InviteOut:
    return InviteOut(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        state=_invite_state(invite, now),
        invited_by_id=invite.invited_by_id,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        revoked_at=invite.revoked_at,
        created_at=invite.created_at,
    )


@router.get("/invites", summary="List invites")
def list_invites(ctx: Admin, db: DbSession, page: PageParams) -> Page[InviteOut]:
    stmt = scoped(select(Invite), ctx)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Invite.created_at.desc()).limit(page.limit).offset(page.offset))
    now = datetime.now(UTC)
    return Page(items=[_invite_out(i, now) for i in rows], total=total)


@router.post(
    "/invites",
    status_code=status.HTTP_201_CREATED,
    summary="Create an invite link (the token is shown once)",
)
def create_invite(
    body: InviteCreate, ctx: Admin, db: DbSession, settings: AppSettings
) -> InviteCreatedOut:
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise Conflict("An account with this email already exists", code="email_taken")
    raw_token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(days=settings.invite_ttl_days)
    invite = Invite(
        workspace_id=ctx.workspace_id,
        email=email,
        role=body.role,
        token_hash=hash_invite_token(raw_token),
        invited_by_id=ctx.user_id,
        expires_at=expires,
    )
    db.add(invite)
    db.flush()
    audit.record(db, ctx, "invite.create", invite, after={"email": email, "role": body.role.value})
    db.commit()
    return InviteCreatedOut(
        id=invite.id,
        email=email,
        role=invite.role,
        invite_url=f"{settings.public_app_url.rstrip('/')}/invite/{raw_token}",
        expires_at=expires,
    )


@router.delete(
    "/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke an invite"
)
def revoke_invite(invite_id: uuid.UUID, ctx: Admin, db: DbSession) -> Response:
    invite = get_owned(db, Invite, invite_id, ctx)
    if invite.accepted_at is not None:
        raise Conflict("Invite was already accepted", code="invite_accepted")
    if invite.revoked_at is None:
        invite.revoked_at = datetime.now(UTC)
        audit.record(db, ctx, "invite.revoke", invite, after={"email": invite.email})
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
