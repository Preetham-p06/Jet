"""Workspace analytics (spec §7). Each metric carries a `metric` discriminator."""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models.enums import FeeCategory
from app.schemas.common import Cents


class AnalyticsMetric(StrEnum):
    QUOTE_VOLUME = "quote-volume"
    RESPONSE_TIMES = "response-times"
    TRUE_COST_DISTRIBUTION = "true-cost-distribution"
    FEE_TYPES = "fee-types"
    AIRCRAFT_MIX = "aircraft-mix"
    FUNNEL = "funnel"


class MonthCount(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$", examples=["2026-10"])
    count: int


class QuoteVolumeOut(BaseModel):
    metric: Literal["quote-volume"] = "quote-volume"
    items: list[MonthCount]


class OperatorResponseTime(BaseModel):
    operator_id: uuid.UUID
    operator_name: str
    median_hours: float
    n: int


class ResponseTimesOut(BaseModel):
    metric: Literal["response-times"] = "response-times"
    median_hours: float | None
    n: int
    operators: list[OperatorResponseTime]


class CostBin(BaseModel):
    lower_cents: Cents
    upper_cents: Cents
    count: int
    lower_bound_count: int = Field(description="Quotes in the bin that are not fully priced")


class TrueCostDistributionOut(BaseModel):
    metric: Literal["true-cost-distribution"] = "true-cost-distribution"
    bin_size_cents: Cents = 500_000
    bins: list[CostBin]
    n: int
    p25_cents: Cents | None
    median_cents: Cents | None
    p75_cents: Cents | None


class FeeShare(BaseModel):
    category: FeeCategory
    label: str
    count: int
    share_pct: float


class FeeTypesOut(BaseModel):
    metric: Literal["fee-types"] = "fee-types"
    n_quotes: int
    items: list[FeeShare]


class CategoryShare(BaseModel):
    category: str = Field(description="Aircraft category value, or 'unknown'")
    label: str
    count: int
    share_pct: float


class AircraftMixOut(BaseModel):
    metric: Literal["aircraft-mix"] = "aircraft-mix"
    n_quotes: int
    items: list[CategoryShare]


class FunnelOut(BaseModel):
    """Counted in trips, so each stage is a subset of the previous one."""

    metric: Literal["funnel"] = "funnel"
    created: int
    quoted: int
    proposal_sent: int
    booked: int


AnalyticsMetricOut = Annotated[
    QuoteVolumeOut
    | ResponseTimesOut
    | TrueCostDistributionOut
    | FeeTypesOut
    | AircraftMixOut
    | FunnelOut,
    Field(discriminator="metric"),
]


class AnalyticsOverviewOut(BaseModel):
    date_from: date
    date_to: date
    quote_volume: QuoteVolumeOut
    response_times: ResponseTimesOut
    true_cost_distribution: TrueCostDistributionOut
    fee_types: FeeTypesOut
    aircraft_mix: AircraftMixOut
    funnel: FunnelOut
