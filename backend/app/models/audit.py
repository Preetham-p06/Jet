"""Append-only audit log. There is deliberately no update or delete path."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, Timestamps, UUIDPk, WorkspaceScoped, str_enum
from app.models.enums import ActorKind


class AuditEvent(UUIDPk, Timestamps, WorkspaceScoped, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        sa.Index("ix_audit_events_workspace_id_created_at", "workspace_id", "created_at"),
        sa.Index("ix_audit_events_entity", "entity_type", "entity_id"),
    )

    # Actor
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_kind: Mapped[ActorKind] = mapped_column(str_enum(ActorKind), default=ActorKind.USER)
    actor_label: Mapped[str | None] = mapped_column(sa.String(320))

    # Change
    action: Mapped[str] = mapped_column(sa.String(80))  # e.g. "field.verify"
    entity_type: Mapped[str] = mapped_column(sa.String(40))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("trips.id", ondelete="SET NULL"), index=True
    )
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONType)

    # Request
    ip: Mapped[str | None] = mapped_column(sa.String(64))
    user_agent: Mapped[str | None] = mapped_column(sa.String(500))
    request_id: Mapped[str | None] = mapped_column(sa.String(64))
