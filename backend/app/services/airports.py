"""Airport reference data from `data/airports.json` (ICAO, IATA, city, country, tz,
lat/lon, de-ice zone). Lookups accept ICAO or IATA/FAA codes, case-insensitively."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.services.contracts import AirportInfo


def load_airports(path: Path | None = None) -> Mapping[str, AirportInfo]:
    """All airports by ICAO (cached)."""
    raise NotImplementedError


def get_airport(code: str) -> AirportInfo | None:
    """By ICAO, or by IATA/FAA code (e.g. "TEB" -> KTEB)."""
    raise NotImplementedError


def timezone_for(code: str) -> str | None:
    """IANA zone of the airport, used to default `trip_legs.depart_tz`."""
    raise NotImplementedError


def search_airports(query: str, *, limit: int = 10) -> list[AirportInfo]:
    """Prefix match on codes, substring match on name and city; codes rank first."""
    raise NotImplementedError


def airports_for(codes: list[str]) -> dict[str, AirportInfo]:
    """The known subset of `codes`, keyed by ICAO (for `TripContext.airports`)."""
    raise NotImplementedError
