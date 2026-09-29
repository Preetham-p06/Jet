"""Scalar field patterns: tail numbers, seats, pax, Wi-Fi, routes, dates, times,
durations, availability, decline intent and operator names (spec §3.3 step 6)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time
from typing import Final, Generic, TypeVar

from app.models.enums import Availability

TAIL_NUMBER_RE: Final = re.compile(
    r"\bN(?:[1-9]\d{0,4}|[1-9]\d{0,3}[A-HJ-NP-Z]|[1-9]\d{0,2}[A-HJ-NP-Z]{2})\b"
)


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Found(Generic[T]):
    value: T
    start: int
    end: int
    confidence: int


def find_tail_numbers(text: str) -> list[Found[str]]:
    raise NotImplementedError


def find_seats(text: str) -> list[Found[int]]:
    raise NotImplementedError


def find_pax(text: str) -> list[Found[int]]:
    raise NotImplementedError


def find_wifi(text: str) -> list[Found[bool]]:
    raise NotImplementedError


def find_route(text: str) -> list[Found[tuple[str, str]]]:
    raise NotImplementedError


def find_dates(text: str, *, default_year: int | None) -> list[Found[date]]:
    raise NotImplementedError


def find_times(text: str) -> list[Found[time]]:
    raise NotImplementedError


def find_durations(text: str) -> list[Found[int]]:
    """Durations in minutes: `2h 58m`, `2:58`, `ETE 2:48`, `2.97 hrs`."""
    raise NotImplementedError


def find_availability(text: str) -> list[Found[Availability]]:
    raise NotImplementedError


def detect_decline(text: str) -> bool:
    raise NotImplementedError


def find_operator_name(
    text: str, *, sender: str | None, known_names: tuple[str, ...]
) -> Found[str] | None:
    raise NotImplementedError
