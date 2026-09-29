"""Expected-fee rules (spec §4 table). None fires when the category is present
or covered by "all in".

fet             all legs US-US              warning, 7.5 % x FET base
segment_fees    US domestic                 info, pax x segments x $5.30
international   any non-US endpoint         warning, estimate by category
deicing         departure in de-ice zone,   info Oct/Nov/Mar/Apr, warning Dec-Feb
                month Oct-Apr
crew_overnight  legs span a night           warning
positioning     aircraft based elsewhere,   warning
                no positioning line
learned         freq >= 0.6 with n >= 5     info; warning at >= 0.85 with n >= 10
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Final

from app.models.enums import FeeCategory
from app.services.contracts import ExpectedFee, LearnedStat, QuoteState, TripContext

FET_RATE: Final = Decimal("0.075")
SEGMENT_FEE_CENTS: Final = 530
DEICE_WARNING_MONTHS: Final = frozenset({12, 1, 2})
DEICE_INFO_MONTHS: Final = frozenset({10, 11, 3, 4})
LEARNED_INFO_FREQUENCY: Final = 0.6
LEARNED_INFO_MIN_N: Final = 5
LEARNED_WARNING_FREQUENCY: Final = 0.85
LEARNED_WARNING_MIN_N: Final = 10


def expected_fees(
    state: QuoteState,
    trip: TripContext,
    *,
    learned: Mapping[FeeCategory, LearnedStat] | None = None,
) -> list[ExpectedFee]:
    raise NotImplementedError
