"""Workspace analytics (spec §7), aggregated in Python for portability.

Default range: the 12 months up to `now`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.permissions import RequestContext
from app.schemas.analytics import (
    AircraftMixOut,
    AnalyticsMetric,
    AnalyticsMetricOut,
    AnalyticsOverviewOut,
    FeeTypesOut,
    FunnelOut,
    QuoteVolumeOut,
    ResponseTimesOut,
    TrueCostDistributionOut,
)

TRUE_COST_BIN_CENTS = 500_000  # $5k


@dataclass(frozen=True, slots=True)
class DateRange:
    date_from: date
    date_to: date  # inclusive


def default_range(today: date) -> DateRange:
    raise NotImplementedError


def quote_volume(db: Session, ctx: RequestContext, rng: DateRange) -> QuoteVolumeOut:
    """Active quotes per month of `first_received_at`."""
    raise NotImplementedError


def response_times(db: Session, ctx: RequestContext, rng: DateRange) -> ResponseTimesOut:
    """Median hours from requested_at to responded_at, overall and per operator."""
    raise NotImplementedError


def true_cost_distribution(
    db: Session, ctx: RequestContext, rng: DateRange
) -> TrueCostDistributionOut:
    raise NotImplementedError


def fee_types(db: Session, ctx: RequestContext, rng: DateRange) -> FeeTypesOut:
    """Share of active quotes with a stated, estimated or not_stated line per category."""
    raise NotImplementedError


def aircraft_mix(db: Session, ctx: RequestContext, rng: DateRange) -> AircraftMixOut:
    raise NotImplementedError


def funnel(db: Session, ctx: RequestContext, rng: DateRange) -> FunnelOut:
    """Trips created -> with a quote -> with a sent proposal -> booked."""
    raise NotImplementedError


def compute_metric(
    db: Session, ctx: RequestContext, metric: AnalyticsMetric, rng: DateRange
) -> AnalyticsMetricOut:
    raise NotImplementedError


def overview(db: Session, ctx: RequestContext, rng: DateRange) -> AnalyticsOverviewOut:
    raise NotImplementedError
