"""Roles, capabilities, the request context and tenant-scoped lookups."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, TypeVar

from sqlalchemy import Select
from sqlalchemy.orm import Session

from app.errors import NotFound
from app.models.base import WorkspaceScoped
from app.models.enums import Role
from app.models.workspace import User, Workspace


class Capability(StrEnum):
    TRIP_WRITE = "trip.write"
    INGEST = "ingest"
    FIELD_REVIEW = "field.review"
    FLAG_RESOLVE = "flag.resolve"
    PROPOSAL_MANAGE = "proposal.manage"
    ANALYTICS_VIEW = "analytics.view"
    AUDIT_VIEW = "audit.view"
    WORKSPACE_ADMIN = "workspace.admin"
    USERS_ADMIN = "users.admin"


_ASSISTANT: Final = frozenset({Capability.TRIP_WRITE, Capability.INGEST})
_BROKER: Final = _ASSISTANT | {
    Capability.FIELD_REVIEW,
    Capability.FLAG_RESOLVE,
    Capability.PROPOSAL_MANAGE,
    Capability.ANALYTICS_VIEW,
    Capability.AUDIT_VIEW,  # brokers see the audit log filtered to one trip only
}
_ADMIN: Final = _BROKER | {Capability.WORKSPACE_ADMIN, Capability.USERS_ADMIN}

ROLE_CAPABILITIES: Final[dict[Role, frozenset[Capability]]] = {
    Role.ASSISTANT: _ASSISTANT,
    Role.BROKER: frozenset(_BROKER),
    Role.ADMIN: frozenset(_ADMIN),
}

# Role sets used by route dependencies (spec §8).
ANY_ROLE: Final = (Role.ADMIN, Role.BROKER, Role.ASSISTANT)
REVIEWERS: Final = (Role.ADMIN, Role.BROKER)
ADMINS: Final = (Role.ADMIN,)


def capabilities_for(role: Role) -> list[Capability]:
    """Stable, sorted list for `/auth/me`."""
    return sorted(ROLE_CAPABILITIES[role], key=lambda c: c.value)


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Who is calling, loaded fresh from the database on every request."""

    user: User
    workspace: Workspace
    role: Role
    request_id: str
    ip: str | None = None
    user_agent: str | None = None

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.workspace.id

    def can(self, capability: Capability) -> bool:
        return capability in ROLE_CAPABILITIES[self.role]


M = TypeVar("M", bound=WorkspaceScoped)
S = TypeVar("S", bound=Select[Any])


def get_owned(db: Session, model: type[M], obj_id: uuid.UUID, ctx: RequestContext) -> M:
    """Load one row of the caller's workspace, or raise 404 (never 403)."""
    obj = db.get(model, obj_id)
    if obj is None or obj.workspace_id != ctx.workspace_id:
        raise NotFound(f"{model.__name__} not found")
    return obj


def scoped(stmt: S, ctx: RequestContext, model: type[WorkspaceScoped] | None = None) -> S:
    """Add an explicit workspace filter to a SELECT.

    `model` defaults to the statement's first selected entity. The ORM guard
    adds the same criteria; this keeps the intent visible at the call site and
    covers statements the guard cannot see.
    """
    target: Any = model
    if target is None:
        entity = stmt.column_descriptions[0].get("entity")
        if entity is None or not issubclass(entity, WorkspaceScoped):
            raise TypeError("scoped() needs a WorkspaceScoped entity; pass model=")
        target = entity
    return stmt.where(target.workspace_id == ctx.workspace_id)
