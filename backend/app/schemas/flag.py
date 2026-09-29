"""Flags and their resolution."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import AwareDatetime, Field, model_validator

from app.models.enums import FeeCategory, FlagResolution, FlagSeverity, FlagStatus, FlagType
from app.schemas.common import APIModel, Cents, ORMModel


class FlagOut(ORMModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    quote_id: uuid.UUID | None
    source_document_id: uuid.UUID | None
    field_id: uuid.UUID | None
    fee_category: FeeCategory | None
    type: FlagType
    severity: FlagSeverity
    blocking: bool
    fingerprint: str
    message: str
    details: dict[str, Any]
    status: FlagStatus
    resolution: FlagResolution | None
    resolution_note: str | None
    resolved_by_id: uuid.UUID | None
    resolved_at: AwareDatetime | None
    allowed_resolutions: list[FlagResolution] = Field(
        default_factory=list, description="Resolutions valid for this flag type"
    )
    created_at: AwareDatetime
    updated_at: AwareDatetime


class FlagResolveIn(APIModel):
    resolution: FlagResolution
    amount_cents: Cents | None = Field(
        default=None, ge=0, description="Required for confirmed_amount (USD cents)"
    )
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _requirements(self) -> FlagResolveIn:
        if self.resolution is FlagResolution.CONFIRMED_AMOUNT and self.amount_cents is None:
            raise ValueError("confirmed_amount needs amount_cents")
        if self.resolution is FlagResolution.DISMISSED and not self.note:
            raise ValueError("dismissing a flag needs a note")
        if self.resolution is FlagResolution.AUTO_CLEARED:
            raise ValueError("auto_cleared is set by the system only")
        return self
