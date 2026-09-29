"""Aircraft dictionary (`data/aircraft.json`): model, category, typical seats."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import AircraftCategory


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


def load_aircraft() -> tuple[AircraftEntry, ...]:
    raise NotImplementedError


def match_aircraft(text: str) -> AircraftMatch | None:
    raise NotImplementedError


def canonical_model(text: str) -> str | None:
    """Canonical dictionary model for free text; used for the client-facing label."""
    raise NotImplementedError
