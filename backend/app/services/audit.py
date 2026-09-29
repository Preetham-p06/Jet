"""Writing the append-only audit log."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.base import Base
from app.models.enums import ActorKind
from app.permissions import RequestContext

# Columns never copied into before/after snapshots.
_REDACTED = frozenset({"password_hash", "token_hash", "share_token"})

Entity = Base | tuple[str, uuid.UUID | None]


def jsonable(value: Any) -> Any:
    """Convert a column value to plain JSON (UUIDs, datetimes, Decimals, enums)."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [jsonable(v) for v in value]
    return str(value)


def snapshot(obj: Base, fields: Iterable[str] | None = None) -> dict[str, Any]:
    """Column values of `obj` as JSON, for `before`/`after`.

    Secrets are always redacted. Pass `fields` to keep the diff focused.
    """
    columns = [attr.key for attr in inspect(obj).mapper.column_attrs]
    keys = columns if fields is None else [f for f in fields if f in columns]
    return {k: jsonable(getattr(obj, k)) for k in keys if k not in _REDACTED}


def _entity_ref(entity: Entity | None) -> tuple[str, uuid.UUID | None]:
    if entity is None:
        return "none", None
    if isinstance(entity, tuple):
        return entity
    table = type(entity).__tablename__
    entity_type = table[:-1] if table.endswith("s") else table
    entity_id = getattr(entity, "id", None)
    return entity_type, entity_id if isinstance(entity_id, uuid.UUID) else None


def record(
    db: Session,
    ctx: RequestContext | None,
    action: str,
    entity: Entity | None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    *,
    trip_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    actor_kind: ActorKind | None = None,
    actor_label: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    """Append one audit event in the caller's transaction (the caller commits).

    `action` is dotted, e.g. "trip.update" or "field.verify". `entity` is an ORM
    row or an explicit `(entity_type, id)` pair. Without a `ctx` (system jobs,
    public endpoints) pass `workspace_id` and `actor_kind`.
    """
    entity_type, entity_id = _entity_ref(entity)
    if ctx is not None:
        workspace_id = ctx.workspace_id
        actor_kind = actor_kind or ActorKind.USER
        actor_label = actor_label or ctx.user.email
        ip = ip or ctx.ip
        user_agent = user_agent or ctx.user_agent
        request_id = request_id or ctx.request_id
    if workspace_id is None:
        raise ValueError("audit.record needs a ctx or an explicit workspace_id")

    event = AuditEvent(
        workspace_id=workspace_id,
        actor_user_id=ctx.user_id if ctx is not None else None,
        actor_kind=actor_kind or ActorKind.SYSTEM,
        actor_label=actor_label,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        trip_id=trip_id,
        before=jsonable(dict(before)) if before is not None else None,
        after=jsonable(dict(after)) if after is not None else None,
        ip=ip,
        user_agent=(user_agent or "")[:500] or None,
        request_id=request_id or None,
    )
    db.add(event)
    return event


def diff(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reduce two snapshots to the keys that changed."""
    changed = [k for k in after if before.get(k) != after.get(k)]
    return {k: before.get(k) for k in changed}, {k: after[k] for k in changed}
