"""Workspace analytics (admins and brokers)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter

from app.deps import DbSession, Reviewer
from app.errors import Unprocessable
from app.schemas.analytics import AnalyticsMetric, AnalyticsMetricOut, AnalyticsOverviewOut
from app.services import analytics


def _range(date_from: date | None, date_to: date | None) -> analytics.DateRange:
    """Defaults to the last 12 months; either end may be given alone."""
    default = analytics.default_range(datetime.now(UTC).date())
    rng = analytics.DateRange(
        date_from=date_from or default.date_from, date_to=date_to or default.date_to
    )
    if rng.date_from > rng.date_to:
        raise Unprocessable(
            "date_from must not be after date_to",
            code="invalid_range",
            fields={"date_from": "after date_to"},
        )
    return rng


router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", summary="All six metrics (default range: the last 12 months)")
def get_overview(
    ctx: Reviewer, db: DbSession, date_from: date | None = None, date_to: date | None = None
) -> AnalyticsOverviewOut:
    return analytics.overview(db, ctx, _range(date_from, date_to))


@router.get("/{metric}", summary="One metric")
def get_metric(
    metric: AnalyticsMetric,
    ctx: Reviewer,
    db: DbSession,
    date_from: date | None = None,
    date_to: date | None = None,
) -> AnalyticsMetricOut:
    return analytics.compute_metric(db, ctx, metric, _range(date_from, date_to))
