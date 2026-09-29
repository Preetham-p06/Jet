"""Learned fee frequencies, scoped to one workspace (spec §4).

`observe_quote` deletes and re-inserts one `fee_observations` row per
(airport, role, canonical category), with `present` true or false.
Outliers: amount > p75 + 3 x IQR with n >= 8 -> info `fee_outlier`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Final

from sqlalchemy.orm import Session

from app.models.enums import FeeCategory
from app.models.quote import Quote
from app.services.contracts import FeeObservationPoint, LearnedStat, TripContext, TrueCost

OUTLIER_MIN_N: Final = 8
OUTLIER_IQR_FACTOR: Final = 3


def observe_quote(
    db: Session, quote: Quote, trip: TripContext, true_cost: TrueCost, *, now: datetime
) -> int:
    """Rewrite this quote's observations; returns the number of rows written."""
    raise NotImplementedError


def learned_stats(rows: Sequence[FeeObservationPoint]) -> dict[FeeCategory, LearnedStat]:
    """Pure: frequency over all rows, amount quartiles over present rows with amounts."""
    raise NotImplementedError


def load_learned(
    db: Session,
    workspace_id: uuid.UUID,
    airport_icao: str,
    month: int,
    *,
    exclude_quote_id: uuid.UUID | None,
    month_window: int = 0,
) -> dict[FeeCategory, LearnedStat]:
    """Stats for one airport; `month_window=1` widens to month +/- 1 (de-icing)."""
    raise NotImplementedError


def is_outlier(amount_cents: int, stat: LearnedStat) -> bool:
    raise NotImplementedError
