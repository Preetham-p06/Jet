"""Scalar field patterns and the aircraft dictionary (spec §3.3 step 6)."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.extraction.rules.aircraft import canonical_model, load_aircraft, match_aircraft
from app.extraction.rules.patterns import (
    detect_decline,
    find_availability,
    find_category,
    find_daily_minimum,
    find_dates,
    find_durations,
    find_operator_name,
    find_pax,
    find_route,
    find_seats,
    find_tail_numbers,
    find_times,
    find_wifi,
)
from app.models.enums import AircraftCategory, Availability


@pytest.mark.parametrize("tail", ["N684AC", "N1", "N12345", "N1234Z", "N350SB", "N75RW"])
def test_valid_tail_numbers(tail: str) -> None:
    assert [f.value for f in find_tail_numbers(f"Tail {tail}")] == [tail]


@pytest.mark.parametrize("text", ["N0123", "N123456", "N12IO", "N302IH", "NA123", "n684ac"])
def test_invalid_tail_numbers(text: str) -> None:
    assert find_tail_numbers(text) == []


def test_tail_confidence_depends_on_context() -> None:
    assert find_tail_numbers("Aircraft: Latitude (N684AC)")[0].confidence == 85
    assert find_tail_numbers("reg N35CR")[0].confidence == 85
    assert find_tail_numbers("... N350SB ...")[0].confidence == 65
    near_model = find_tail_numbers("Challenger 350 · N350SB", context_spans=((0, 14),))
    assert near_model[0].confidence == 85


def test_seats_and_pax_are_distinct() -> None:
    text = "9 passenger seats, 7 pax"
    assert [f.value for f in find_seats(text)] == [9]
    assert [f.value for f in find_pax(text)] == [7]
    assert [f.value for f in find_seats("configured for 8")] == [8]
    assert [f.value for f in find_seats("8-passenger configuration")] == [8]
    assert [f.value for f in find_seats("Seats: 12")] == [12]
    assert [f.value for f in find_pax("Passengers: 7")] == [7]
    assert find_pax("9 passenger seats") == []


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Wi-Fi: Yes", True),
        ("WiFi onboard", True),
        ("Wi-Fi: Ka-band", True),
        ("Starlink installed", True),
        ("Wi-Fi: not installed", False),
        ("no wifi on this tail", False),
        ("Internet: none", False),
    ],
)
def test_wifi(text: str, value: bool) -> None:
    assert find_wifi(text)[0].value is value


@pytest.mark.parametrize(
    ("text", "route"),
    [
        ("KTEB-KOPF", ("KTEB", "KOPF")),
        ("KTEB - KOPF", ("KTEB", "KOPF")),
        ("KTEB -> KOPF", ("KTEB", "KOPF")),
        ("KTEB to MYNN", ("KTEB", "MYNN")),
        ("TEB-OPF", ("TEB", "OPF")),
    ],
)
def test_routes(text: str, route: tuple[str, str]) -> None:
    assert find_route(text)[0].value == route


def test_route_ignores_non_airport_codes() -> None:
    assert find_route("FET-USD") == []
    assert find_route("ktEB-kopf") == []


@pytest.mark.parametrize(
    "text",
    ["18 Oct 2026", "Oct 18, 2026", "10/18/2026", "2026-10-18", "18-Oct-2026", "18 October 2026"],
)
def test_dates(text: str) -> None:
    assert find_dates(text, default_year=None)[0].value == date(2026, 10, 18)


def test_missing_year_comes_from_the_trip() -> None:
    [found] = find_dates("re JS184 18 Oct.", default_year=2026)
    assert found.value == date(2026, 10, 18)
    assert found.confidence < 92
    assert find_dates("18 Oct", default_year=None) == []


@pytest.mark.parametrize(
    ("text", "value"),
    [("09:00", time(9)), ("9:30 PM", time(21, 30)), ("0900L", time(9)), ("10am", time(10))],
)
def test_times(text: str, value: time) -> None:
    assert find_times(f"dep {text}")[0].value == value


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("2h 58m", 178),
        ("2h45m", 165),
        ("3h 05m", 185),
        ("2:48", 168),
        ("2 hr 58 min", 178),
        ("2.97 hrs", 178),
    ],
)
def test_durations(text: str, minutes: int) -> None:
    assert find_durations(f"flight time {text}")[0].value == minutes


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("Availability: Confirmed", Availability.CONFIRMED),
        ("Aircraft available", Availability.AVAILABLE),
        ("Subject to availability", Availability.SUBJECT_TO),
        ("subject to final confirmation", Availability.SUBJECT_TO),
        ("tentatively held", Availability.TENTATIVE),
        ("not available that day", Availability.UNAVAILABLE),
    ],
)
def test_availability(text: str, value: Availability) -> None:
    assert find_availability(text)[0].value is value


def test_decline() -> None:
    assert detect_decline("Unfortunately we are unable to support JS184")
    assert detect_decline("no availability on 18 Oct")
    assert detect_decline("We must decline")
    assert not detect_decline("Charter price $41,800")


def test_category_explicit_only() -> None:
    found = find_category("Category: Midsize")
    assert found is not None
    assert found.value is AircraftCategory.MIDSIZE
    assert found.confidence == 95
    found = find_category("super mid-size")
    assert found is not None
    assert found.value is AircraftCategory.SUPER_MIDSIZE
    assert find_category("light rain expected") is None


def test_daily_minimum() -> None:
    found = find_daily_minimum("$4,950/hr x 3.2 hrs, 2 hr daily minimum")
    assert found is not None
    assert found.value == 2.0


def test_aircraft_dictionary() -> None:
    entries = load_aircraft()
    assert len(entries) >= 30
    match = match_aircraft("Aircraft: Cessna Citation Latitude (N684AC)")
    assert match is not None
    assert match.entry.category is AircraftCategory.MIDSIZE
    assert match.entry.typical_seats == 8
    assert canonical_model("CL-350") == "Bombardier Challenger 350"
    assert canonical_model("cl350") == "Bombardier Challenger 350"
    assert canonical_model("G280") == "Gulfstream G280"
    assert canonical_model("Legacy 650") == "Embraer Legacy 650"
    assert canonical_model("Citation XLS+") == "Cessna Citation XLS+"
    assert canonical_model("a nice jet") is None


KNOWN = ("Atlas Air Charter", "Summit Executive Aviation", "Coastal Wings", "Meridian Air")


def test_operator_name_order() -> None:
    from_sender = find_operator_name(
        "body", sender="Atlas Air Charter <q@atlas.example>", known_names=KNOWN
    )
    assert from_sender is not None
    assert (from_sender.value, from_sender.start) == ("Atlas Air Charter", -1)
    header = find_operator_name("Northwind Charter\nCharter price: $1", sender=None, known_names=())
    assert header is not None
    assert header.value == "Northwind Charter"
    token = find_operator_name("Hi it's Dan at Summit re JS184", sender=None, known_names=KNOWN)
    assert token is not None
    assert token.value == "Summit Executive Aviation"
    person = find_operator_name("hello", sender="Dan Reyes <d@x.example>", known_names=KNOWN)
    assert person is None
