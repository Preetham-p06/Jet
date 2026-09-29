"""Flag evaluation (spec §4 "Flags"). Pure; warning and critical flags block.

Severity rule: anything that could understate the client's cost is warning or
critical; where the engine took the conservative reading, the flag is info.
Fingerprints come from `contracts.flag_fingerprint(type, subject)` and must be
stable across recomputes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from app.models.enums import FeeCategory
from app.services.contracts import (
    ExpectedFee,
    FlagSpec,
    LearnedStat,
    QuoteState,
    TripContext,
    TrueCost,
)


def evaluate_flags(
    state: QuoteState,
    trip: TripContext,
    true_cost: TrueCost,
    expected: Sequence[ExpectedFee],
    now: datetime,
    *,
    learned: Mapping[FeeCategory, LearnedStat] | None = None,
) -> list[FlagSpec]:
    raise NotImplementedError
