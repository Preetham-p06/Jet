"""Vocabulary for the dashboard, and the airport lookup for the trip form."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import AnyUser
from app.models.enums import (
    FEE_CATEGORY_ORDER,
    FLAG_RESOLUTIONS,
    AircraftCategory,
    AmountStatus,
    FieldStatus,
    FlagSeverity,
    FlagType,
    ProposalStatus,
    QuoteStatus,
    Role,
    TripOperatorStatus,
    TripStatus,
)
from app.schemas.common import Page
from app.schemas.meta import (
    AIRCRAFT_CATEGORY_LABELS,
    AMOUNT_STATUS_LABELS,
    FEE_CATEGORY_LABELS,
    FLAG_RESOLUTION_LABELS,
    FLAG_TYPE_LABELS,
    AirportOut,
    FeeCategoryItem,
    FlagTypeItem,
    VocabItem,
    VocabularyOut,
)
from app.services import airports

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/vocabulary", summary="Fee categories, statuses and flag types with labels")
def get_vocabulary(ctx: AnyUser) -> VocabularyOut:
    return VocabularyOut(
        fee_categories=[
            FeeCategoryItem(value=c.value, label=FEE_CATEGORY_LABELS[c], order=i)
            for i, c in enumerate(FEE_CATEGORY_ORDER)
        ],
        aircraft_categories=[
            VocabItem(value=c.value, label=AIRCRAFT_CATEGORY_LABELS[c]) for c in AircraftCategory
        ],
        amount_statuses=[
            VocabItem(value=s.value, label=AMOUNT_STATUS_LABELS[s]) for s in AmountStatus
        ],
        flag_types=[
            FlagTypeItem(
                value=t.value,
                label=FLAG_TYPE_LABELS[t],
                resolutions=[
                    VocabItem(value=r.value, label=FLAG_RESOLUTION_LABELS[r])
                    for r in FLAG_RESOLUTIONS.get(t, ())
                ],
            )
            for t in FlagType
        ],
        flag_severities=list(FlagSeverity),
        field_statuses=list(FieldStatus),
        quote_statuses=list(QuoteStatus),
        trip_statuses=list(TripStatus),
        trip_operator_statuses=list(TripOperatorStatus),
        proposal_statuses=list(ProposalStatus),
        roles=list(Role),
    )


@router.get("/airports", summary="Airport lookup by code, name or city")
def search_airports(
    ctx: AnyUser,
    q: Annotated[str, Query(min_length=1, max_length=60)],
    limit: Annotated[int, Query(ge=1, le=25)] = 10,
) -> Page[AirportOut]:
    found = airports.search_airports(q, limit=limit)
    items = [
        AirportOut(icao=a.icao, iata=a.iata, name=a.name, city=a.city, country=a.country, tz=a.tz)
        for a in found
    ]
    return Page(items=items, total=len(items))
