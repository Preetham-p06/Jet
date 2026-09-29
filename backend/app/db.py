"""Engine, sessions and the ORM-level tenant guards.

Isolation is defense in depth: route code always goes through
`permissions.get_owned` / `permissions.scoped`, and on top of that every
session whose `info["workspace_id"]` is set

* adds `with_loader_criteria(WorkspaceScoped, workspace_id == wid)` to every
  ORM SELECT, UPDATE and DELETE (`do_orm_execute`), and
* refuses to flush a `WorkspaceScoped` row that belongs to another workspace,
  filling in `workspace_id` when it was left unset (`before_flush`).

Raw `text()` SQL and Core statements on tables bypass the loader criteria, so
service code must not use them for tenant data.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import ORMExecuteState, Session, sessionmaker, with_loader_criteria

from app.models.base import WorkspaceScoped

WORKSPACE_KEY = "workspace_id"


class TenantViolation(RuntimeError):
    """A flush tried to write a row owned by a different workspace."""


class TenantSession(Session):
    """Session class carrying the tenant guard listeners."""


def make_engine(url: str, *, echo: bool = False) -> Engine:
    is_sqlite = url.startswith("sqlite")
    connect_args: dict[str, Any] = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(url, echo=echo, connect_args=connect_args, pool_pre_ping=not is_sqlite)
    if is_sqlite:
        event.listen(engine, "connect", _sqlite_pragmas)
    return engine


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def make_session_factory(engine: Engine) -> sessionmaker[TenantSession]:
    return sessionmaker(bind=engine, class_=TenantSession, expire_on_commit=False)


def set_workspace(session: Session, workspace_id: uuid.UUID) -> None:
    """Scope a session to one workspace for the rest of its life."""
    current = session.info.get(WORKSPACE_KEY)
    if current is not None and current != workspace_id:
        raise TenantViolation("session is already scoped to another workspace")
    session.info[WORKSPACE_KEY] = workspace_id


def session_workspace(session: Session) -> uuid.UUID | None:
    wid = session.info.get(WORKSPACE_KEY)
    return wid if isinstance(wid, uuid.UUID) else None


@event.listens_for(TenantSession, "do_orm_execute")
def _add_tenant_criteria(state: ORMExecuteState) -> None:
    wid = session_workspace(state.session)
    if wid is None:
        return
    if not (state.is_select or state.is_update or state.is_delete):
        return
    # Relationship and column loads inherit the criteria from the parent query.
    if state.is_select and (state.is_column_load or state.is_relationship_load):
        return
    state.statement = state.statement.options(
        with_loader_criteria(
            WorkspaceScoped,
            lambda cls: cls.workspace_id == wid,
            include_aliases=True,
        )
    )


@event.listens_for(TenantSession, "before_flush")
def _guard_tenant_writes(session: Session, _flush_context: Any, _instances: Any) -> None:
    wid = session_workspace(session)
    if wid is None:
        return
    for obj in (*session.new, *session.dirty, *session.deleted):
        if not isinstance(obj, WorkspaceScoped):
            continue
        if obj.workspace_id is None and obj in session.new:
            obj.workspace_id = wid
        elif obj.workspace_id != wid:
            raise TenantViolation(
                f"refusing to write {type(obj).__name__} owned by another workspace"
            )


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed (and rolled back) at the end.

    Handlers commit explicitly; anything uncommitted is discarded.
    """
    factory: sessionmaker[TenantSession] = request.app.state.session_factory
    with factory() as session:
        yield session
