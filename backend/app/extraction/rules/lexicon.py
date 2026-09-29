"""Fee and price anchors plus status qualifiers (design spec §3.3, table 2).

Matching is longest-first, case-insensitive, on whole words. "not included"
and "excl." are matched before "included".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Final, Literal

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


# Phrases are written in lower case; a space matches any run of whitespace, and
# "/", "&" and "-" inside a phrase may be surrounded by optional spaces.
PRICE_ANCHORS: Final[dict[AnchorKind, tuple[str, ...]]] = {
    "headline": (
        "charter price",
        "charter cost",
        "charter fee",
        "charter rate",
        "flight charge",
        "flight price",
        "flight cost",
        "aircraft charge",
        "trip price",
        "trip cost",
        "base price",
        "base charter",
        "quoted price",
        "price is",
        "quote is",
        "quoted at",
        "our price",
        "price",
    ),
    "stated_total": (
        "total",
        "grand total",
        "total price",
        "total cost",
        "trip total",
        "total due",
        "total amount",
        "total charter cost",
    ),
    "hourly_rate": ("hourly rate", "hourly", "per hour", "/hr", "/hour"),
}

FEE_ANCHORS: Final[dict[FeeCategory, tuple[str, ...]]] = {
    FeeCategory.POSITIONING: (
        "positioning",
        "repositioning",
        "ferry flight",
        "ferry",
        "deadhead",
        "positioning fee",
    ),
    FeeCategory.RAMP_HANDLING: (
        "ramp fee",
        "ramp fees",
        "ramp",
        "handling",
        "handling fee",
        "handling fees",
        "ground handling",
        "ramp & handling",
        "ramp and handling",
        "ramp / handling",
        "fbo fee",
        "fbo fees",
        "fbo handling",
        "fbo",
        "facility fee",
    ),
    FeeCategory.FUEL_SURCHARGE: (
        "fuel surcharge",
        "fuel",
        "fuel adjustment",
        "fuel uplift",
        "fsc",
    ),
    FeeCategory.CATERING: ("catering", "catered", "meals"),
    FeeCategory.CREW_OVERNIGHT: (
        "crew overnight",
        "crew overnights",
        "crew ron",
        "ron",
        "crew hotel",
        "crew hotels",
        "crew accommodation",
        "crew lodging",
    ),
    FeeCategory.CREW: (
        "crew fee",
        "crew fees",
        "crew expenses",
        "extra crew",
        "flight attendant",
        "cabin attendant",
        "per diem",
        "crew",
    ),
    FeeCategory.OVERNIGHT: (
        "aircraft overnight",
        "overnight fee",
        "overnight",
        "parking",
        "hangar",
        "hangarage",
    ),
    FeeCategory.LANDING: ("landing fee", "landing fees", "landing"),
    FeeCategory.DEICING: (
        "de-ice",
        "deice",
        "de-icing",
        "deicing",
        "anti-ice",
        "anti-icing",
        "type i",
        "type iv",
        "glycol",
    ),
    FeeCategory.INTERNATIONAL: (
        "international fees",
        "international fee",
        "customs",
        "cbp",
        "apis",
        "eapis",
        "immigration",
        "overflight",
        "overflight fees",
    ),
    FeeCategory.FET: ("fet", "federal excise tax", "excise tax", "federal excise taxes"),
    FeeCategory.SEGMENT_FEES: (
        "segment fee",
        "segment fees",
        "segment tax",
        "segment taxes",
        "domestic segment",
        "domestic segment fees",
    ),
    FeeCategory.TAXES: (
        "taxes",
        "tax",
        "vat",
        "airport taxes",
        "government taxes",
        "security fee",
        "departure tax",
    ),
    FeeCategory.WIFI_FEE: (
        "wifi fee",
        "wi-fi fee",
        "wifi charge",
        "wi-fi charge",
        "wifi usage",
        "wi-fi usage",
        "internet fee",
        "internet usage",
        "satcom charge",
        "satcom fee",
        "connectivity charge",
    ),
}

# Order matters only for equal-length overlaps; longer phrases always win.
QUALIFIERS: Final[dict[Qualifier, tuple[str, ...]]] = {
    Qualifier.ALL_IN: (
        "all in",
        "all-in",
        "all inclusive",
        "all-inclusive",
        "fully inclusive",
        "inclusive of all",
        "incl. standard charges",
        "incl. all charges",
        "incl. all fees",
        "including all charges",
        "including all fees",
        "including standard charges",
    ),
    Qualifier.EXTRA: (
        "extra",
        "additional",
        "plus",
        "on top",
        "not included",
        "not incl.",
        "excl.",
        "excluding",
        "excludes",
        "exclusive of",
        "not covered",
    ),
    Qualifier.INCLUDED: (
        "included",
        "incl.",
        "incl",
        "inclusive",
        "includes",
        "including",
        "complimentary",
        "no charge",
        "at no charge",
        "covered",
    ),
    Qualifier.WAIVED: ("waived", "no fee"),
    Qualifier.HEDGE: (
        "may",
        "might",
        "possibly",
        "depending on",
        "depends on",
        "subject to",
        "if required",
        "if needed",
        "if applicable",
        "tbd",
        "tbc",
        "to be confirmed",
        "to be determined",
        "at cost",
    ),
    Qualifier.ESTIMATE: (
        "est.",
        "est",
        "estimated",
        "estimate",
        "approx.",
        "approx",
        "approximately",
        "~",
        "circa",
        "around",
        "up to",
        "roughly",
    ),
}

_MONTH_MAY: Final = re.compile(r"May\s+\d|May,?\s+20\d\d")
ABBREVIATED_INCLUDED: Final = frozenset({"incl.", "incl"})


_SEPARATORS: Final = re.compile(r"(\s+|[/&-])")


def _phrase_regex(phrase: str) -> str:
    """Whole-word, whitespace-tolerant regex for a lexicon phrase."""
    compact = re.sub(r"\s*([/&-])\s*", r"\1", phrase.strip())
    parts: list[str] = []
    for token in _SEPARATORS.split(compact):
        if not token:
            continue
        if token.isspace():
            parts.append(r"\s+")
        elif token in ("/", "&", "-"):
            parts.append(r"\s*" + re.escape(token) + r"\s*")
        else:
            parts.append(re.escape(token))
    # Only require a word boundary where the phrase starts/ends with a word char.
    head = r"(?<![\w])" if compact[0].isalnum() else ""
    tail = r"(?![\w])" if compact[-1].isalnum() else ""
    return head + "".join(parts) + tail


@dataclass(frozen=True, slots=True)
class _Entry:
    pattern: re.Pattern[str]
    length: int
    kind: AnchorKind
    category: FeeCategory | None


@lru_cache(maxsize=1)
def _anchor_entries() -> tuple[_Entry, ...]:
    entries: list[_Entry] = []
    for kind, phrases in PRICE_ANCHORS.items():
        for phrase in phrases:
            entries.append(
                _Entry(re.compile(_phrase_regex(phrase), re.IGNORECASE), len(phrase), kind, None)
            )
    for category, phrases in FEE_ANCHORS.items():
        for phrase in phrases:
            entries.append(
                _Entry(
                    re.compile(_phrase_regex(phrase), re.IGNORECASE), len(phrase), "fee", category
                )
            )
    entries.sort(key=lambda e: -e.length)
    return tuple(entries)


@lru_cache(maxsize=1)
def _qualifier_entries() -> tuple[tuple[re.Pattern[str], int, Qualifier], ...]:
    entries: list[tuple[re.Pattern[str], int, Qualifier]] = []
    for qualifier, phrases in QUALIFIERS.items():
        for phrase in phrases:
            length = len(phrase)
            # "not included" / "excl." beat "included" by length; bump EXTRA ties.
            bonus = 1 if qualifier is Qualifier.EXTRA else 0
            entries.append(
                (re.compile(_phrase_regex(phrase), re.IGNORECASE), length * 2 + bonus, qualifier)
            )
    entries.sort(key=lambda e: -e[1])
    return tuple(entries)


def _overlaps(taken: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < t_end and t_start < end for t_start, t_end in taken)


def _raw_anchors(clause: str) -> list[AnchorMatch]:
    taken: list[tuple[int, int]] = []
    found: list[AnchorMatch] = []
    for entry in _anchor_entries():
        for m in entry.pattern.finditer(clause):
            if _overlaps(taken, m.start(), m.end()):
                continue
            taken.append((m.start(), m.end()))
            found.append(AnchorMatch(entry.kind, entry.category, m.group(0), m.start(), m.end()))
    found.sort(key=lambda a: a.start)
    return found


_JOINER: Final = re.compile(r"^[\s/&(),:-]*(?:and\s*)?[\s/&(),:-]*$", re.IGNORECASE)


def match_anchors(clause: str) -> list[AnchorMatch]:
    """Anchors in reading order. Adjacent anchors of the same kind and category
    ("Ramp / handling", "Positioning (ferry") are merged into one span."""
    merged: list[AnchorMatch] = []
    for anchor in _raw_anchors(clause):
        if merged:
            prev = merged[-1]
            gap = clause[prev.end : anchor.start]
            same = prev.kind == anchor.kind and prev.category == anchor.category
            if same and len(gap) <= 6 and _JOINER.match(gap):
                merged[-1] = AnchorMatch(
                    prev.kind,
                    prev.category,
                    clause[prev.start : anchor.end],
                    prev.start,
                    anchor.end,
                )
                continue
        merged.append(anchor)
    return merged


def match_qualifiers(clause: str) -> list[QualifierMatch]:
    taken: list[tuple[int, int]] = []
    found: list[QualifierMatch] = []
    for pattern, _, qualifier in _qualifier_entries():
        for m in pattern.finditer(clause):
            if _overlaps(taken, m.start(), m.end()):
                continue
            if qualifier is Qualifier.HEDGE and _MONTH_MAY.match(clause, m.start()):
                continue  # "May 18" is a date, not a hedge
            taken.append((m.start(), m.end()))
            found.append(QualifierMatch(qualifier, m.group(0), m.start(), m.end()))
    found.sort(key=lambda q: q.start)
    return found
