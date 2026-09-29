"""Every route, mounted under `/api/v1`. Paths never end with a slash."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    analytics,
    audit,
    auth,
    fields,
    flags,
    health,
    ingest,
    meta,
    operators,
    proposals,
    public,
    quotes,
    recommendation,
    trip_operators,
    trips,
    users,
    workspace,
)
from app.schemas.common import ERROR_RESPONSES

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX, responses=ERROR_RESPONSES)
for module in (
    health,
    auth,
    workspace,
    users,
    operators,
    trips,
    trip_operators,
    ingest,
    quotes,
    fields,
    flags,
    recommendation,
    proposals,
    public,
    analytics,
    audit,
    meta,
):
    api_router.include_router(module.router)
