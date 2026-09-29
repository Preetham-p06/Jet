"""Rebuilding every derived value of a trip (spec §4-5).

For each active quote: build `QuoteState`, get expected fees (rules + learned),
`normalize_quote`, rebuild `fee_lines`, `evaluate_flags` and reconcile them by
fingerprint, observe fees, compute quote confidence. Then `score_trip`,
persist a `Recommendation`, and update quotes' fit, recommendation and
proposal eligibility. Flag reconciliation: open flags are updated; resolved or
dismissed flags stay unless `data_hash` changed and the condition still
holds (reopened, audited `flag.auto_reopen`); open flags whose condition is
gone are resolved `auto_cleared`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.flag import Flag
from app.models.quote import Quote
from app.models.trip import Trip
from app.models.workspace import Workspace
from app.permissions import RequestContext
from app.services.contracts import (
    FlagSpec,
    QuoteState,
    RecommendationResult,
    TripContext,
    TrueCost,
)


@dataclass(slots=True)
class FlagReconcileReport:
    created: list[Flag] = field(default_factory=list)
    updated: list[Flag] = field(default_factory=list)
    reopened: list[Flag] = field(default_factory=list)
    auto_cleared: list[Flag] = field(default_factory=list)


def build_trip_context(db: Session, trip: Trip, workspace: Workspace) -> TripContext:
    raise NotImplementedError


def build_quote_state(db: Session, quote: Quote) -> QuoteState:
    """Current fields -> QuoteState, plus conflicts, revisions and document issues."""
    raise NotImplementedError


def recompute_quote(
    db: Session, quote: Quote, trip_ctx: TripContext, *, now: datetime
) -> tuple[TrueCost, list[FlagSpec]]:
    """Normalize one quote, rebuild its fee lines and reconcile its flags."""
    raise NotImplementedError


def reconcile_flags(
    db: Session,
    quote: Quote,
    specs: Sequence[FlagSpec],
    *,
    now: datetime,
    ctx: RequestContext | None = None,
) -> FlagReconcileReport:
    raise NotImplementedError


def recompute_trip(
    db: Session,
    trip: Trip,
    *,
    now: datetime | None = None,
    ctx: RequestContext | None = None,
) -> RecommendationResult | None:
    """Recompute every quote of the trip and the recommendation; None without quotes."""
    raise NotImplementedError
