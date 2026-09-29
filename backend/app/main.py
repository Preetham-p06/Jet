"""Application factory: routers, middleware and error handlers."""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.router import API_PREFIX, api_router
from app.config import Settings, get_settings
from app.db import TenantViolation, make_engine, make_session_factory
from app.errors import DomainError, RateLimited
from app.logging import configure_logging, request_id_var
from app.security.ratelimit import InMemoryRateLimiter, RateLimiter
from app.services.storage import LocalStorage, Storage, StorageError

log = logging.getLogger("app")

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"x-robots-tag", b"noindex, nofollow"),
)
PUBLIC_PREFIX = f"{API_PREFIX}/public/"


class RequestContextMiddleware:
    """Assigns a request id (or accepts a sane incoming one) and adds security headers.

    API responses default to `Cache-Control: no-store`; routes may override it.
    Public proposal responses, errors included, never send a referrer.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER.lower().encode(), b"").decode()
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        referrer = (
            b"no-referrer"
            if scope["path"].startswith(PUBLIC_PREFIX)
            else b"strict-origin-when-cross-origin"
        )

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                headers.extend(h for h in SECURITY_HEADERS if h[0] not in present)
                if b"referrer-policy" not in present:
                    headers.append((b"referrer-policy", referrer))
                if b"cache-control" not in present:
                    headers.append((b"cache-control", b"no-store"))
                headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            request_id_var.reset(token)


def _error(status_code: int, detail: str, code: str, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {"detail": detail, "code": code}
    body.update({k: v for k, v in extra.items() if v is not None})
    return JSONResponse(body, status_code=status_code)


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        response = _error(exc.status_code, exc.detail, exc.code, fields=exc.fields)
        if isinstance(exc, RateLimited):
            response.headers["Retry-After"] = str(exc.retry_after_s)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = {
            ".".join(str(p) for p in err.get("loc", ())): err.get("msg", "invalid")
            for err in exc.errors()
        }
        return _error(422, "Validation error", "validation_error", fields=fields)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {404: "not_found", 405: "method_not_allowed", 401: "not_authenticated"}
        response = _error(
            exc.status_code, str(exc.detail), codes.get(exc.status_code, f"http_{exc.status_code}")
        )
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(StaleDataError)
    async def stale(_request: Request, _exc: StaleDataError) -> JSONResponse:
        return _error(409, "This record was changed by someone else; reload", "stale_version")

    @app.exception_handler(IntegrityError)
    async def integrity(_request: Request, exc: IntegrityError) -> JSONResponse:
        log.warning("integrity error: %s", exc.orig)
        return _error(409, "Conflicts with existing data", "conflict")

    @app.exception_handler(TenantViolation)
    async def tenant(_request: Request, exc: TenantViolation) -> JSONResponse:
        # A bug, not a user error: log loudly, but answer like any other miss.
        log.error("tenant guard blocked a write: %s", exc)
        return _error(404, "Not found", "not_found")

    @app.exception_handler(StorageError)
    async def storage_error(_request: Request, _exc: StorageError) -> JSONResponse:
        return _error(404, "File not found", "not_found")

    @app.exception_handler(NotImplementedError)
    async def not_implemented(_request: Request, _exc: NotImplementedError) -> JSONResponse:
        return _error(501, "This feature is not implemented yet", "not_implemented")


def create_app(
    settings: Settings | None = None,
    *,
    storage: Storage | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title="JetStream AI",
        summary="Quote intelligence for private aviation charter brokers",
        version=settings.app_version,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=f"{API_PREFIX}/docs/oauth2-redirect",
        redirect_slashes=False,
        generate_unique_id_function=lambda route: route.name,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.storage = storage or LocalStorage(settings.storage_dir)
    app.state.rate_limiter = rate_limiter or InMemoryRateLimiter()
    app.state.extractor = None  # built lazily by deps.get_extractor

    _register_error_handlers(app)
    app.include_router(api_router)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "Authorization", "X-JetStream-Client"],
        )
    app.add_middleware(RequestContextMiddleware)
    return app


app = create_app()
