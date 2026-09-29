"""Workspace settings."""

from __future__ import annotations

import uuid

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.common import APIModel, ORMModel, Percent


class ScoringWeights(BaseModel):
    """Overrides for the fit-score weights (spec §5); omitted signals keep defaults."""

    model_config = ConfigDict(extra="forbid")

    pricing: float | None = Field(default=None, ge=0, le=100)
    fees: float | None = Field(default=None, ge=0, le=100)
    aircraft: float | None = Field(default=None, ge=0, le=100)
    timing: float | None = Field(default=None, ge=0, le=100)
    preferences: float | None = Field(default=None, ge=0, le=100)
    availability: float | None = Field(default=None, ge=0, le=100)
    crew: float | None = Field(default=None, ge=0, le=100)
    routing: float | None = Field(default=None, ge=0, le=100)


class WorkspaceOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    review_threshold: int
    default_markup_pct: Percent
    base_currency: str
    scoring_weights: ScoringWeights | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class WorkspacePatch(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    review_threshold: int | None = Field(default=None, ge=50, le=100)
    default_markup_pct: Percent | None = Field(default=None, le=50)
    scoring_weights: ScoringWeights | None = None
