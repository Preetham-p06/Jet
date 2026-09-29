"""Workspaces (brokerages), their users and pending invites."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, Timestamps, UUIDPk, WorkspaceScoped, str_enum
from app.models.enums import Role


class Workspace(UUIDPk, Timestamps, Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        sa.CheckConstraint(
            "review_threshold >= 50 AND review_threshold <= 100", name="review_threshold_range"
        ),
        sa.CheckConstraint(
            "default_markup_pct >= 0 AND default_markup_pct <= 100", name="markup_range"
        ),
    )

    name: Mapped[str] = mapped_column(sa.String(200))
    slug: Mapped[str] = mapped_column(sa.String(80), unique=True)
    review_threshold: Mapped[int] = mapped_column(default=75, server_default="75")
    default_markup_pct: Mapped[Decimal] = mapped_column(
        sa.Numeric(5, 2), default=Decimal("0"), server_default="0"
    )
    base_currency: Mapped[str] = mapped_column(sa.String(3), default="USD", server_default="USD")
    # Per-signal overrides for the fit score; None means the algorithm defaults.
    scoring_weights: Mapped[dict[str, Any] | None] = mapped_column(JSONType)

    users: Mapped[list[User]] = relationship(back_populates="workspace", passive_deletes=True)


class User(UUIDPk, Timestamps, WorkspaceScoped, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(sa.String(320), unique=True)  # stored lowercased
    full_name: Mapped[str] = mapped_column(sa.String(200))
    password_hash: Mapped[str] = mapped_column(sa.String(255))
    role: Mapped[Role] = mapped_column(str_enum(Role))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    # Bumped on password change or deactivation; tokens carrying an older value are rejected.
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")
    last_login_at: Mapped[datetime | None]

    workspace: Mapped[Workspace] = relationship(back_populates="users")


class Invite(UUIDPk, Timestamps, WorkspaceScoped, Base):
    __tablename__ = "invites"

    email: Mapped[str] = mapped_column(sa.String(320))
    role: Mapped[Role] = mapped_column(str_enum(Role))
    # sha256 hex of the raw token; the raw token is shown to the admin exactly once.
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None]
