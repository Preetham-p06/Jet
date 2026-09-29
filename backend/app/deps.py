"""FastAPI dependencies: settings, storage, the caller's context and role gates."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_db, set_workspace
from app.errors import Forbidden, Unauthorized
from app.extraction.base import Extractor
from app.models.enums import Role
from app.models.workspace import User, Workspace
from app.permissions import (
    ADMINS,
    ANY_ROLE,
    REVIEWERS,
    Capability,
    RequestContext,
)
from app.security.csrf import CSRFError, enforce_csrf
from app.security.ratelimit import RateLimiter
from app.security.tokens import InvalidToken, decode_access_token
from app.services.storage import Storage

__all__ = [
    "Admin",
    "AnyUser",
    "AppSettings",
    "DbSession",
    "RequestContext",
    "StorageDep",
    "Reviewer",
    "get_current_context",
    "get_extractor",
    "get_rate_limiter",
    "get_settings_dep",
    "get_storage",
    "require_capability",
    "require_roles",
]

_bearer = HTTPBearer(auto_error=False, description="Session JWT (cookie `js_session` also works)")


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


def get_extractor(request: Request) -> Extractor:
    """The configured extractor, built once per app (tests inject a fake on `app.state`)."""
    extractor: Extractor | None = getattr(request.app.state, "extractor", None)
    if extractor is None:
        from app.extraction.registry import select_extractor

        extractor = select_extractor(request.app.state.settings)
        request.app.state.extractor = extractor
    return extractor


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def request_id_of(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "")


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]
StorageDep = Annotated[Storage, Depends(get_storage)]


def get_current_context(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> RequestContext:
    """Authenticate the caller and scope the session to their workspace.

    A Bearer token wins over the cookie. The user is reloaded on every request,
    so deactivation, role changes and `token_version` bumps apply immediately.
    """
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token, via_cookie = credentials.credentials, False
    else:
        token, via_cookie = request.cookies.get(settings.cookie_name, ""), True
    if not token:
        raise Unauthorized("Not authenticated")

    try:
        claims = decode_access_token(settings, token)
    except InvalidToken:
        raise Unauthorized("Session expired or invalid", code="invalid_token") from None

    user = db.get(User, claims.user_id)
    if (
        user is None
        or not user.is_active
        or user.token_version != claims.token_version
        or user.workspace_id != claims.workspace_id
    ):
        raise Unauthorized("Session expired or invalid", code="invalid_token")

    try:
        enforce_csrf(request, cookie_authenticated=via_cookie)
    except CSRFError:
        raise Forbidden("Missing X-JetStream-Client header", code="csrf_failed") from None

    workspace = db.get(Workspace, user.workspace_id)
    if workspace is None:  # pragma: no cover - FK cascade makes this unreachable
        raise Unauthorized("Session expired or invalid", code="invalid_token")

    set_workspace(db, workspace.id)
    request.state.user_id = str(user.id)
    return RequestContext(
        user=user,
        workspace=workspace,
        role=user.role,
        request_id=request_id_of(request),
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


CurrentContext = Annotated[RequestContext, Depends(get_current_context)]


def require_roles(*roles: Role) -> Callable[..., RequestContext]:
    """Dependency factory: the caller must hold one of `roles`, else 403.

    The returned callable carries `__roles__` so tests can assert that every
    route declares a role gate.
    """
    allowed = frozenset(roles)

    def dependency(ctx: CurrentContext) -> RequestContext:
        if ctx.role not in allowed:
            raise Forbidden("Your role does not allow this action", code="forbidden_role")
        return ctx

    dependency.__roles__ = allowed  # type: ignore[attr-defined]
    dependency.__name__ = f"require_{'_'.join(sorted(r.value for r in allowed))}"
    return dependency


def require_capability(capability: Capability) -> Callable[..., RequestContext]:
    def dependency(ctx: CurrentContext) -> RequestContext:
        if not ctx.can(capability):
            raise Forbidden("Your role does not allow this action", code="forbidden_role")
        return ctx

    dependency.__capability__ = capability  # type: ignore[attr-defined]
    return dependency


AnyUser = Annotated[RequestContext, Depends(require_roles(*ANY_ROLE))]
Reviewer = Annotated[RequestContext, Depends(require_roles(*REVIEWERS))]
Admin = Annotated[RequestContext, Depends(require_roles(*ADMINS))]


def role_gate_of(dependency: Any) -> frozenset[Role] | None:
    """The roles a `require_roles` dependency allows, or None for anything else."""
    roles = getattr(dependency, "__roles__", None)
    return roles if isinstance(roles, frozenset) else None
