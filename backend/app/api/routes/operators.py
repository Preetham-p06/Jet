"""Operators (the charter companies a workspace asks for quotes)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.params import PageParams
from app.deps import Admin, AnyUser, DbSession, Reviewer
from app.errors import Conflict
from app.models.enums import OperatorSource
from app.models.operator import Operator
from app.permissions import RequestContext, get_owned, scoped
from app.schemas.common import Page
from app.schemas.operator import OperatorCreate, OperatorDetailOut, OperatorOut, OperatorPatch
from app.services import audit
from app.services.operators import email_domain, normalize_operator_name, operator_stats

router = APIRouter(prefix="/operators", tags=["operators"])

_AUDITED = (
    "name",
    "aliases",
    "email",
    "phone",
    "website",
    "home_base_icao",
    "notes",
    "is_archived",
)


def _ensure_unique_name(
    db: Session, ctx: RequestContext, normalized: str, exclude: uuid.UUID | None = None
) -> None:
    stmt = scoped(select(Operator.id), ctx, Operator).where(Operator.normalized_name == normalized)
    if exclude is not None:
        stmt = stmt.where(Operator.id != exclude)
    if db.scalar(stmt) is not None:
        raise Conflict("An operator with this name already exists", code="operator_exists")


def create_operator(
    db: Session,
    ctx: RequestContext,
    body: OperatorCreate,
    *,
    source: OperatorSource = OperatorSource.MANUAL,
) -> Operator:
    """Shared with bulk RFQ creation; raises 409 on a duplicate normalized name."""
    normalized = normalize_operator_name(body.name)
    _ensure_unique_name(db, ctx, normalized)
    email = body.email.lower() if body.email else None
    operator = Operator(
        workspace_id=ctx.workspace_id,
        name=body.name,
        normalized_name=normalized,
        aliases=body.aliases,
        email=email,
        email_domain=email_domain(email),
        phone=body.phone,
        website=body.website,
        home_base_icao=body.home_base_icao,
        notes=body.notes,
        source=source,
    )
    db.add(operator)
    db.flush()
    audit.record(db, ctx, "operator.create", operator, after=audit.snapshot(operator, _AUDITED))
    return operator


@router.get("", summary="Search operators")
def list_operators(
    ctx: AnyUser,
    db: DbSession,
    page: PageParams,
    q: Annotated[str | None, Query(max_length=100)] = None,
    include_archived: bool = False,
) -> Page[OperatorOut]:
    stmt = scoped(select(Operator), ctx)
    if not include_archived:
        stmt = stmt.where(Operator.is_archived.is_(False))
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                Operator.normalized_name.like(like),
                func.lower(Operator.email).like(like),
                Operator.email_domain.like(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Operator.name).limit(page.limit).offset(page.offset))
    return Page(items=[OperatorOut.model_validate(o) for o in rows], total=total)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create an operator")
def post_operator(body: OperatorCreate, ctx: AnyUser, db: DbSession) -> OperatorOut:
    operator = create_operator(db, ctx, body)
    db.commit()
    return OperatorOut.model_validate(operator)


@router.get("/{operator_id}", summary="Operator detail with quote and response stats")
def get_operator(operator_id: uuid.UUID, ctx: AnyUser, db: DbSession) -> OperatorDetailOut:
    operator = get_owned(db, Operator, operator_id, ctx)
    base = OperatorOut.model_validate(operator).model_dump()
    return OperatorDetailOut(**base, stats=operator_stats(db, operator))


@router.patch("/{operator_id}", summary="Update an operator")
def update_operator(
    operator_id: uuid.UUID, body: OperatorPatch, ctx: Reviewer, db: DbSession
) -> OperatorOut:
    operator = get_owned(db, Operator, operator_id, ctx)
    before = audit.snapshot(operator, _AUDITED)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and body.name is not None:
        normalized = normalize_operator_name(body.name)
        _ensure_unique_name(db, ctx, normalized, exclude=operator.id)
        operator.normalized_name = normalized
    if "email" in changes:
        changes["email"] = body.email.lower() if body.email else None
        operator.email_domain = email_domain(changes["email"])
    for key, value in changes.items():
        setattr(operator, key, value)
    old, new = audit.diff(before, audit.snapshot(operator, _AUDITED))
    if new:
        audit.record(db, ctx, "operator.update", operator, old, new)
    db.commit()
    return OperatorOut.model_validate(operator)


@router.delete(
    "/{operator_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Archive an operator"
)
def archive_operator(operator_id: uuid.UUID, ctx: Admin, db: DbSession) -> Response:
    operator = get_owned(db, Operator, operator_id, ctx)
    if not operator.is_archived:
        operator.is_archived = True
        audit.record(
            db, ctx, "operator.archive", operator, {"is_archived": False}, {"is_archived": True}
        )
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
