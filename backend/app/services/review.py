"""Human review of fields and flags (spec §4 "Reconciling flags", §8 review endpoints).

Every action checks `version` (409 `stale_version` on mismatch), locks the
field, writes an audit entry with before/after, and recomputes the trip in the
same transaction. Flag resolutions that change money write the field too:
`confirmed_amount` creates or edits the fee field (edited, locked),
`accepted_estimate` accepts it, `confirmed_included` edits it to included,
`not_applicable` sets the line to not_applicable.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import FlagResolution
from app.models.flag import Flag
from app.models.quote import Quote, QuoteField
from app.models.trip import Trip
from app.permissions import RequestContext
from app.schemas.quote import ReviewQueueItemOut


def verify_field(
    db: Session, ctx: RequestContext, field: QuoteField, *, version: int
) -> QuoteField:
    """Status verified, locked; effective confidence becomes 100."""
    raise NotImplementedError


def accept_field(
    db: Session, ctx: RequestContext, field: QuoteField, *, version: int, note: str | None
) -> QuoteField:
    """Status accepted, locked; an accepted estimate counts in the known total."""
    raise NotImplementedError


def edit_field(
    db: Session,
    ctx: RequestContext,
    field: QuoteField,
    *,
    version: int,
    value: Any,
    note: str | None,
) -> QuoteField:
    """Validate `value` for the key, set `current_value`, status edited, locked."""
    raise NotImplementedError


def reset_field(db: Session, ctx: RequestContext, field: QuoteField, *, version: int) -> QuoteField:
    """Back to `original_value`, status extracted, unlocked."""
    raise NotImplementedError


def add_manual_field(
    db: Session,
    ctx: RequestContext,
    quote: Quote,
    *,
    key: str,
    value: Any,
    label: str | None,
    note: str | None,
) -> QuoteField:
    """Insert a manual current value (extractor manual, edited, locked), superseding
    any current value for the key."""
    raise NotImplementedError


def field_history(db: Session, field: QuoteField) -> list[QuoteField]:
    """Every revision of the field's (quote, key), newest first."""
    raise NotImplementedError


def review_queue(db: Session, ctx: RequestContext, trip: Trip) -> list[ReviewQueueItemOut]:
    """Unlocked material fields below the workspace threshold plus open blocking
    flags, sorted by money impact (largest first)."""
    raise NotImplementedError


def resolve_flag(
    db: Session,
    ctx: RequestContext,
    flag: Flag,
    *,
    resolution: FlagResolution,
    amount_cents: int | None,
    note: str | None,
) -> Flag:
    """422 when `resolution` is not allowed for the flag type (`FLAG_RESOLUTIONS`)."""
    raise NotImplementedError


def reopen_flag(db: Session, ctx: RequestContext, flag: Flag) -> Flag:
    raise NotImplementedError
