"""Proposals: the broker view, and the whitelisted public (client) view."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, NaiveDatetime

from app.models.enums import AmountStatus, FeeCategory, ProposalStatus
from app.schemas.common import APIModel, Cents, Percent
from app.schemas.quote import SourceRefOut
from app.schemas.recommendation import ReasonOut

PUBLIC_DISCLAIMER = (
    "Estimated total, all known charges included. Final pricing is subject to "
    "aircraft availability and operator confirmation at booking."
)


class ProposalOptionIn(APIModel):
    quote_id: uuid.UUID
    markup_pct_override: Percent | None = None


class ProposalCreate(APIModel):
    """Omit `quote_ids` for every eligible quote, recommended first then by client total.

    Passing an ineligible quote returns 422 with its reasons.
    """

    quote_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=10)
    markup_pct: Percent | None = Field(default=None, description="Defaults to the workspace's")
    title: str | None = Field(default=None, max_length=200)
    client_name: str | None = Field(default=None, max_length=200)
    message: str | None = Field(default=None, max_length=5000)


class ProposalPatch(APIModel):
    """Drafts only. `options`, when given, replaces the option list in that order."""

    options: list[ProposalOptionIn] | None = Field(default=None, min_length=1, max_length=10)
    markup_pct: Percent | None = None
    title: str | None = Field(default=None, max_length=200)
    client_name: str | None = Field(default=None, max_length=200)
    message: str | None = Field(default=None, max_length=5000)


class OptionChoiceIn(APIModel):
    """Body of mark-accepted / mark-booked; defaults to the accepted or only option."""

    option_id: uuid.UUID | None = None


class BrokerFeeLineOut(BaseModel):
    category: FeeCategory
    label: str
    amount_status: AmountStatus
    amount_cents: Cents | None


class ProposalOptionOut(BaseModel):
    """Broker view of one option: every number behind the client total."""

    id: uuid.UUID
    quote_id: uuid.UUID
    sort_order: int
    is_recommended: bool
    operator_name: str
    aircraft_model: str | None
    aircraft_category: str | None
    tail_number: str | None
    seats: int | None
    wifi: bool | None
    flight_time_minutes: int | None
    headline_cents: Cents | None
    fee_lines: list[BrokerFeeLineOut]
    added_charges_cents: Cents | None
    known_total_cents: Cents | None
    upper_total_cents: Cents | None
    cost_basis_cents: Cents
    markup_pct: Percent = Field(description="Effective markup for this option")
    markup_pct_override: Percent | None
    markup_cents: Cents
    client_total_cents: Cents
    quote_confidence: int | None
    sources: list[SourceRefOut]
    eligible: bool
    reasons: list[ReasonOut]
    snapshot_at: AwareDatetime | None


class ProposalSummaryOut(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    trip_reference: str
    status: ProposalStatus
    title: str
    client_name: str | None
    markup_pct: Percent
    option_count: int
    recommended_client_total_cents: Cents | None
    sent_at: AwareDatetime | None
    share_expires_at: AwareDatetime | None
    view_count: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ProposalOut(BaseModel):
    """Broker view (spec §6), shaped like the landing page's BrokerView."""

    id: uuid.UUID
    trip_id: uuid.UUID
    trip_reference: str
    status: ProposalStatus
    title: str
    client_name: str | None
    message: str | None
    markup_pct: Percent
    share_url: str | None
    share_enabled: bool
    share_expires_at: AwareDatetime | None
    sent_at: AwareDatetime | None
    sent_by_id: uuid.UUID | None
    accepted_at: AwareDatetime | None
    accepted_option_id: uuid.UUID | None
    accepted_by_name: str | None
    booked_at: AwareDatetime | None
    declined_at: AwareDatetime | None
    cancelled_at: AwareDatetime | None
    first_viewed_at: AwareDatetime | None
    last_viewed_at: AwareDatetime | None
    view_count: int
    supersedes_id: uuid.UUID | None
    created_by_id: uuid.UUID | None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    options: list[ProposalOptionOut]


# --------------------------------------------------------------------------- public view
# Whitelist only. Never add the operator, tail number, fees, confidence,
# markup or file names here: `extra="forbid"` makes a leak a server error.


class PublicLegOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_code: str
    origin_city: str
    destination_code: str
    destination_city: str
    departure_local: NaiveDatetime


class PublicOptionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: uuid.UUID
    aircraft: str = Field(description="Canonical model name, operator tokens stripped")
    category: str | None
    client_total_cents: Cents
    seats: int | None
    pax: int
    wifi: bool | None
    flight_time_minutes: int | None
    recommended: bool


class PublicProposalOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    prepared_for: str | None
    prepared_by: str = Field(description="The workspace (brokerage) name")
    legs: list[PublicLegOut]
    date: date
    pax: int
    message: str | None
    options: list[PublicOptionOut]
    disclaimer: str = PUBLIC_DISCLAIMER
    status: ProposalStatus
    accepted_option_id: uuid.UUID | None = None
    expires_at: AwareDatetime | None = None


class PublicAcceptIn(APIModel):
    option_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
