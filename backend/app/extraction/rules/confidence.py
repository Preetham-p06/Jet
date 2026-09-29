"""The confidence table shared by the rules extractor and Claude's rubric (spec §3.3 step 7).

Checks: Summit fuel 82 - 15 - 6 = 61; Summit crew overnight 82 + 2 = 84;
Atlas positioning 92 + 3 = 95.
"""

from __future__ import annotations

from typing import Final

from app.extraction.rules.segment import LineKind

BASE: Final[dict[LineKind, int]] = {
    LineKind.LABELLED: 92,
    LineKind.PROSE: 88,
    LineKind.INFORMAL: 82,
    LineKind.QUOTED: 70,
}
CURRENCY_BONUS: Final = 3
EXTRA_BONUS: Final = 2
INCLUDED_SCORE: Final = 95
INCLUDED_ABBREVIATED_SCORE: Final = 93
HEDGE_PENALTY: Final = 15
ESTIMATE_PENALTY: Final = 6
FAR_ANCHOR_PENALTY: Final = 10
FAR_ANCHOR_CHARS: Final = 40
CONFLICT_PENALTY: Final = 20
DICTIONARY_INFERRED: Final = 65
MIN_CONFIDENCE: Final = 5
MAX_CONFIDENCE: Final = 99  # 100 is reserved for human verification


def score(
    line_kind: LineKind,
    *,
    currency_marker: bool = False,
    explicit_extra: bool = False,
    hedge: bool = False,
    estimate: bool = False,
    far_from_anchor: bool = False,
    conflict: bool = False,
) -> int:
    raise NotImplementedError


def clamp(value: int) -> int:
    raise NotImplementedError
