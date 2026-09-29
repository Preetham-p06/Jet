"""True cost (spec §4): `normalize_quote` is pure.

headline = stated | hourly_rate x max(billable_hours, daily_minimum_hours)
         | hourly_rate x ceil_0.1(flight_time/60) (estimated, `hourly_estimate` warning)
known = upper = headline, then per line:
  stated / edited         -> known += amt, upper += amt
  percent (FET 7.5 %)     -> amt = round(pct x (headline + stated fees except
                             fet/segment_fees/taxes/international))
  included / waived       -> +0, even when an amount is written
  estimated, accepted     -> known += amt, upper += amt
  estimated, unaccepted   -> upper += amt; not fully priced
  not_stated              -> upper += estimate (operator | rule | learned median)
  not_applicable          -> 0
all_in: `ALL_IN_COVERED` categories without a line get a synthetic included line
  (included_by all_in); itemized and "extra" amounts are still added.
WARNING expected fees -> synthetic not_stated lines; INFO -> `conditional_charges`.
Stated total (tolerance max($1, 0.1 %)): above -> known = stated (warning);
  below -> keep computed, name reconciling lines by subset-sum over <= 12 lines.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.services.contracts import (
    ExpectedFee,
    FxTable,
    NormalizedFeeLine,
    QuoteState,
    TripContext,
    TrueCost,
)

SUBSET_SUM_MAX_LINES = 12


def normalize_quote(
    state: QuoteState,
    trip: TripContext,
    fx: FxTable,
    expected: Sequence[ExpectedFee],
) -> TrueCost:
    raise NotImplementedError


def total_tolerance_cents(stated_cents: int) -> int:
    """max($1, 0.1 % of the stated total)."""
    raise NotImplementedError


def reconciling_lines(
    lines: Sequence[NormalizedFeeLine], difference_cents: int, tolerance_cents: int
) -> tuple[NormalizedFeeLine, ...] | None:
    """Smallest subset of counted lines whose sum matches `difference_cents`
    within tolerance, or None (considers at most `SUBSET_SUM_MAX_LINES`)."""
    raise NotImplementedError
