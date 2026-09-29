"""Flag evaluation: the demo flags, every flag type, severity rule and fingerprint stability."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.enums import (
    AmountStatus,
    FeeCategory,
    FieldGroup,
    FieldStatus,
    FlagSeverity,
    FlagType,
    PricingBasis,
)
from app.services.contracts import (
    ConflictState,
    DocumentIssue,
    FieldState,
    FlagSpec,
    LearnedStat,
    QuoteState,
    RevisionState,
)
from app.services.fee_rules import expected_fees
from app.services.flags import evaluate_flags
from app.services.fx import load_fx_table
from app.services.normalization import normalize_quote
from tests.unit.demo_js184 import NOW, line, make_trip, run_demo, state

F = FeeCategory
A = AmountStatus
T = FlagType
TRIP = make_trip()


def flags_for(s: QuoteState, **kw: object) -> dict[str, FlagSpec]:
    expected = expected_fees(s, TRIP)
    tc = normalize_quote(s, TRIP, load_fx_table(), expected)
    return {f.fingerprint: f for f in evaluate_flags(s, TRIP, tc, expected, NOW, **kw)}  # type: ignore[arg-type]


def ok_state(**kw: object) -> QuoteState:
    base = state(
        (
            line(F.FET, A.INCLUDED),
            line(F.SEGMENT_FEES, A.INCLUDED),
            line(F.DEICING, A.NOT_APPLICABLE),
        ),
        aircraft_model="Citation Latitude",
        seats=8,
    )
    return replace(base, **kw)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- demo


def test_demo_flags() -> None:
    ev, _ = run_demo()
    summit = {f.fingerprint: f for f in ev["Summit"].flags}
    assert set(summit) == {
        "ambiguous_charge:fuel_surcharge",
        "all_in_itemized_conflict",
        "conditional_charge:deicing",
    }
    fuel = summit["ambiguous_charge:fuel_surcharge"]
    assert fuel.severity is FlagSeverity.WARNING and fuel.is_blocking
    assert fuel.fee_category is F.FUEL_SURCHARGE and fuel.details["confidence"] == 61
    assert fuel.field_id is not None
    assert [f.fingerprint for f in ev["Summit"].blocking] == ["ambiguous_charge:fuel_surcharge"]
    for name in ("Atlas", "SkyBridge", "Northstar"):
        assert [f.fingerprint for f in ev[name].flags] == ["conditional_charge:deicing"]
        assert not ev[name].blocking


def test_demo_flags_after_fuel_resolution() -> None:
    for fuel in ("accepted", "included"):
        ev, _ = run_demo(fuel)
        assert not ev["Summit"].blocking


def test_fingerprints_and_hashes_are_stable() -> None:
    a, _ = run_demo()
    b, _ = run_demo()
    fa = [(f.fingerprint, f.data_hash()) for f in a["Summit"].flags]
    fb = [(f.fingerprint, f.data_hash()) for f in b["Summit"].flags]
    assert fa == fb


def test_data_hash_changes_with_details() -> None:
    s = ok_state(fees=(*ok_state().fees, line(F.FUEL_SURCHARGE, A.ESTIMATED, 85_000)))
    before = flags_for(s)["ambiguous_charge:fuel_surcharge"]
    s2 = ok_state(fees=(*ok_state().fees, line(F.FUEL_SURCHARGE, A.ESTIMATED, 95_000)))
    after = flags_for(s2)["ambiguous_charge:fuel_surcharge"]
    assert before.fingerprint == after.fingerprint
    assert before.data_hash() != after.data_hash()


# --------------------------------------------------------------------------- types


def test_clean_quote_has_no_flags() -> None:
    assert flags_for(ok_state()) == {}


def test_missing_required_fields() -> None:
    flags = flags_for(ok_state(headline_minor=None, aircraft_model=None))
    assert flags["missing_required_field:headline_price"].severity is FlagSeverity.CRITICAL
    assert flags["missing_required_field:aircraft_model"].severity is FlagSeverity.WARNING


def test_capacity_insufficient() -> None:
    flag = flags_for(ok_state(seats=6))["capacity_insufficient"]
    assert flag.severity is FlagSeverity.CRITICAL and flag.is_blocking


def test_hourly_estimate() -> None:
    s = ok_state(
        headline_minor=None,
        pricing_basis=PricingBasis.HOURLY,
        hourly_rate_minor=600_000,
        flight_time_minutes=170,
    )
    assert flags_for(s)["hourly_estimate"].severity is FlagSeverity.WARNING


def test_currency_flags() -> None:
    assert flags_for(ok_state(currency="XYZ"))["unknown_currency:XYZ"].severity is (
        FlagSeverity.CRITICAL
    )
    fx = flags_for(ok_state(currency="EUR"))["fx_converted:EUR"]
    assert fx.severity is FlagSeverity.INFO and not fx.is_blocking
    assert fx.details["as_of"] == "2026-09-01"


def test_ambiguous_charge_for_not_stated_and_other_lines() -> None:
    s = ok_state(
        fees=(
            *ok_state().fees,
            line(F.CATERING, A.NOT_STATED),
            line(F.OTHER, A.ESTIMATED, 5_000, label="Cleaning fee"),
        )
    )
    flags = flags_for(s)
    assert flags["ambiguous_charge:catering"].is_blocking
    assert flags["ambiguous_charge:other.cleaning_fee"].is_blocking


def test_accepted_estimate_is_not_ambiguous() -> None:
    est = line(F.FUEL_SURCHARGE, A.ESTIMATED, 85_000, review_status=FieldStatus.ACCEPTED)
    assert "ambiguous_charge:fuel_surcharge" not in flags_for(
        ok_state(fees=(*ok_state().fees, est))
    )


def test_expected_fee_missing_and_conditional() -> None:
    flags = flags_for(state(aircraft_model="X"))
    assert flags["expected_fee_missing:fet"].severity is FlagSeverity.WARNING
    assert flags["expected_fee_missing:segment_fees"].severity is FlagSeverity.INFO
    assert flags["conditional_charge:deicing"].severity is FlagSeverity.INFO
    assert not flags["conditional_charge:deicing"].is_blocking


def test_learned_fee_missing_and_outlier() -> None:
    learned = {
        F.LANDING: LearnedStat(n=12, frequency=0.9, median_cents=30_000),
        F.RAMP_HANDLING: LearnedStat(
            n=10,
            frequency=1.0,
            median_cents=45_000,
            p25_cents=40_000,
            p75_cents=50_000,
            n_amounts=10,
        ),
    }
    s = ok_state(fees=(*ok_state().fees, line(F.RAMP_HANDLING, A.STATED, 90_000)))
    expected = expected_fees(s, TRIP, learned=learned)
    tc = normalize_quote(s, TRIP, load_fx_table(), expected)
    flags = {f.fingerprint: f for f in evaluate_flags(s, TRIP, tc, expected, NOW, learned=learned)}
    assert flags["learned_fee_missing:landing"].severity is FlagSeverity.WARNING
    assert flags["fee_outlier:ramp_handling"].severity is FlagSeverity.INFO


def test_total_mismatch_directions() -> None:
    fees = (*ok_state().fees, line(F.RAMP_HANDLING, A.STATED, 40_000, label="Ramp"))
    above = flags_for(ok_state(fees=fees, stated_total_minor=1_100_000))["total_mismatch"]
    assert above.severity is FlagSeverity.WARNING and above.is_blocking
    below = flags_for(ok_state(fees=fees, stated_total_minor=1_000_000))["total_mismatch"]
    assert below.severity is FlagSeverity.INFO and not below.is_blocking
    assert below.details["reconciling_labels"] == ["Ramp"]


def test_all_in_itemized_conflict_is_info() -> None:
    s = ok_state(all_in=True, fees=(line(F.POSITIONING, A.STATED, 100_000),))
    flag = flags_for(s)["all_in_itemized_conflict"]
    assert flag.severity is FlagSeverity.INFO and flag.details["itemized"] == ["positioning"]


def test_merge_and_provenance_flags() -> None:
    fid, cid, doc = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    s = ok_state(
        conflicts=(
            ConflictState("conflict_with_locked", "seats", fid, cid, 8, 9),
            ConflictState("conflicting_values", "fee.positioning", fid, cid, {}, {}),
        ),
        revisions=(RevisionState("fee.positioning", 120_000, 90_000, fid, doc),),
        fields=(
            FieldState(
                fid,
                "tail_number",
                FieldGroup.SCALAR,
                "N1",
                65,
                FieldStatus.EXTRACTED,
                snippet_verified=False,
            ),
        ),
        document_issues=(
            DocumentIssue("extraction_failed", doc, "Extraction failed"),
            DocumentIssue("ocr_unavailable", cid, "Scanned PDF needs OCR"),
        ),
    )
    flags = flags_for(s)
    assert flags["conflict_with_locked:seats"].severity is FlagSeverity.WARNING
    assert flags["conflicting_values:fee.positioning"].is_blocking
    assert flags["value_revised:fee.positioning"].severity is FlagSeverity.INFO
    assert flags["snippet_unverified:tail_number"].severity is FlagSeverity.INFO
    assert flags[f"extraction_failed:{doc}"].severity is FlagSeverity.CRITICAL
    assert flags[f"ocr_unavailable:{cid}"].severity is FlagSeverity.WARNING


def test_timing_flags() -> None:
    expired = ok_state(valid_until=NOW - timedelta(hours=1))
    assert flags_for(expired)["quote_expired"].severity is FlagSeverity.WARNING
    assert "quote_expired" not in flags_for(ok_state(valid_until=NOW + timedelta(days=1)))
    late = ok_state(departure_local=datetime(2026, 10, 18, 12, 0))
    assert flags_for(late)["schedule_mismatch"].severity is FlagSeverity.INFO
    near = ok_state(departure_local=datetime(2026, 10, 18, 10, 0))
    assert "schedule_mismatch" not in flags_for(near)


def test_every_warning_or_critical_blocks() -> None:
    s = ok_state(
        headline_minor=None,
        seats=3,
        currency="EUR",
        valid_until=datetime(2020, 1, 1, tzinfo=UTC),
        fees=(line(F.FUEL_SURCHARGE, A.ESTIMATED, 1_000, percent=Decimal("1")),),
    )
    for flag in flags_for(s).values():
        assert flag.is_blocking is (flag.severity is not FlagSeverity.INFO)
    assert {f.type for f in flags_for(s).values()} >= {
        T.MISSING_REQUIRED_FIELD,
        T.CAPACITY_INSUFFICIENT,
        T.QUOTE_EXPIRED,
        T.FX_CONVERTED,
    }
