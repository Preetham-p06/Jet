"""Aircraft dictionary (`data/aircraft.json`): model, category, typical seats."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

from app.models.enums import AircraftCategory

AIRCRAFT_PATH: Final = Path(__file__).resolve().parents[2] / "data" / "aircraft.json"
_TOKENS: Final = re.compile(r"[A-Za-z]+|\d+|\+")


@dataclass(frozen=True, slots=True)
class AircraftEntry:
    model: str  # canonical, e.g. "Cessna Citation Latitude"
    manufacturer: str
    aliases: tuple[str, ...]
    category: AircraftCategory
    typical_seats: int
    wifi_common: bool


@dataclass(frozen=True, slots=True)
class AircraftMatch:
    entry: AircraftEntry
    text: str
    start: int
    end: int


@lru_cache(maxsize=1)
def load_aircraft() -> tuple[AircraftEntry, ...]:
    data = json.loads(AIRCRAFT_PATH.read_text(encoding="utf-8"))
    return tuple(
        AircraftEntry(
            model=row["model"],
            manufacturer=row["manufacturer"],
            aliases=tuple(row["aliases"]),
            category=AircraftCategory(row["category"]),
            typical_seats=int(row["typical_seats"]),
            wifi_common=bool(row["wifi_common"]),
        )
        for row in data["aircraft"]
    )


def _alias_regex(alias: str) -> str:
    """Letters and digits may be separated by nothing, a space or a hyphen:
    "CL350" matches "CL 350" and "CL-350"."""
    tokens = _TOKENS.findall(alias)
    body = r"[\s-]*".join(re.escape(t) for t in tokens)
    return r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9+])"


@lru_cache(maxsize=1)
def _patterns() -> tuple[tuple[re.Pattern[str], AircraftEntry], ...]:
    pairs: list[tuple[re.Pattern[str], AircraftEntry]] = []
    for entry in load_aircraft():
        for alias in sorted({entry.model, *entry.aliases}, key=len, reverse=True):
            pairs.append((re.compile(_alias_regex(alias), re.IGNORECASE), entry))
    return tuple(pairs)


def find_aircraft(text: str) -> list[AircraftMatch]:
    """Every non-overlapping dictionary match, earliest first (longest on ties)."""
    candidates: list[AircraftMatch] = []
    for pattern, entry in _patterns():
        for m in pattern.finditer(text):
            candidates.append(AircraftMatch(entry, m.group(0), m.start(), m.end()))
    candidates.sort(key=lambda c: (c.start, -(c.end - c.start)))
    chosen: list[AircraftMatch] = []
    for cand in candidates:
        if any(cand.start < c.end and c.start < cand.end for c in chosen):
            continue
        chosen.append(cand)
    return chosen


def match_aircraft(text: str) -> AircraftMatch | None:
    found = find_aircraft(text)
    return found[0] if found else None


def canonical_model(text: str) -> str | None:
    """Canonical dictionary model for free text; used for the client-facing label."""
    match = match_aircraft(text)
    return match.entry.model if match else None
