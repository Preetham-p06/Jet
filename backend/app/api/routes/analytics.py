"""Workspace analytics (admins and brokers)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from app.deps import DbSession, Reviewer
from app.errors import not_implemented
from app.schemas.analytics import AnalyticsMetric, AnalyticsMetricOut, AnalyticsOverviewOut

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", summary="All six metrics (default range: the last 12 months)")
def get_overview(
    ctx: Reviewer, db: DbSession, date_from: date | None = None, date_to: date | None = None
) -> AnalyticsOverviewOut:
    not_implemented("Analytics")


@router.get("/{metric}", summary="One metric")
def get_metric(
    metric: AnalyticsMetric,
    ctx: Reviewer,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
) -> AnalyticsMetricOut:
    not_implemented("Analytics")
