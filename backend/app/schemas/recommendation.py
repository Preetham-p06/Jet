"""Recommendation and fit breakdown."""

from __future__ import annotations

import uuid

from pydantic import AwareDatetime, BaseModel, Field

from app.schemas.common import Cents


class SignalOut(BaseModel):
    key: str = Field(description="pricing, fees, aircraft, timing, preferences, ...")
    label: str
    weight: float
    raw: float | None
    value: float | None
    imputed: bool = Field(description="Missing for this quote; cohort median used (neutral)")
    dropped: bool = Field(description="Missing for every quote; weight renormalized away")
    detail: str | None = None


class ScoreBreakdownOut(BaseModel):
    fit: int | None
    signals: list[SignalOut]
    schedule_subscore: float | None = None


class CheckOut(BaseModel):
    key: str
    label: str
    passed: bool


class ReasonOut(BaseModel):
    code: str
    message: str


class RankingEntryOut(BaseModel):
    quote_id: uuid.UUID
    operator_name: str
    rank: int
    fit_score: int | None
    eligible: bool
    reasons: list[ReasonOut]
    signals: list[SignalOut]
    known_total_cents: Cents | None
    upper_total_cents: Cents | None
    is_fully_priced: bool
    quote_confidence: int | None


class RecommendationOut(BaseModel):
    trip_id: uuid.UUID
    algorithm_version: str
    weights: dict[str, float]
    recommended_quote_id: uuid.UUID | None
    computed_at: AwareDatetime | None
    checks: list[CheckOut]
    ranking: list[RankingEntryOut]
