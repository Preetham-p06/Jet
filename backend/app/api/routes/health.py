"""Liveness and readiness. Never reveals configuration secrets."""

from __future__ import annotations

from fastapi import APIRouter, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.deps import AppSettings, DbSession
from app.schemas.meta import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", summary="Service, database and extractor status")
def health(response: Response, db: DbSession, settings: AppSettings) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except SQLAlchemyError:
        db_ok = False
    if not db_ok:
        response.status_code = 503
    return HealthOut(
        status="ok" if db_ok else "degraded",
        db="ok" if db_ok else "error",
        extractor="claude" if settings.claude_enabled else "rules",
        version=settings.app_version,
    )
