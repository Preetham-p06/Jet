"""Fee and price anchors plus status qualifiers (design spec §3.3, table 2).

Matching is longest-first, case-insensitive, on whole words. "not included"
and "excl." are matched before "included".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from app.models.enums import FeeCategory

AnchorKind = Literal["headline", "stated_total", "hourly_rate", "fee"]


class Qualifier(StrEnum):
    INCLUDED = "included"
    WAIVED = "waived"
    EXTRA = "extra"
    HEDGE = "hedge"
    ESTIMATE = "estimate"
    ALL_IN = "all_in"


@dataclass(frozen=True, slots=True)
class AnchorMatch:
    kind: AnchorKind
    category: FeeCategory | None  # set when kind == "fee"
    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class QualifierMatch:
    qualifier: Qualifier
    text: str
    start: int
    end: int


def match_anchors(clause: str) -> list[AnchorMatch]:
    raise NotImplementedError


def match_qualifiers(clause: str) -> list[QualifierMatch]:
    raise NotImplementedError
