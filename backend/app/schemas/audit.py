"""Audit log reads."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field

from app.models.enums import ActorKind
from app.schemas.common import ORMModel


class AuditEventOut(ORMModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_kind: ActorKind
    actor_label: str | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    trip_id: uuid.UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None
    user_agent: str | None
    request_id: str | None
    created_at: AwareDatetime


class AuditFilters(BaseModel):
    """Query filters. Brokers must pass `trip_id`; admins may omit it."""

    trip_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    action: str | None = None
    date_from: AwareDatetime | None = None
    date_to: AwareDatetime | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
