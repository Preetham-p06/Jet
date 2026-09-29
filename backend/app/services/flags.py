"""Flag evaluation (spec §4 "Flags"). Pure; warning and critical flags block.

Severity rule: anything that could understate the client's cost is warning or
critical; where the engine took the conservative reading, the flag is info.
Fingerprints come from `contracts.flag_fingerprint(type, subject)` and must be
stable across recomputes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final

from app.models.enums import AmountStatus, FeeCategory, FlagSeverity, FlagType
from app.schemas.field_values import slugify
from app.services.contracts import (
    ExpectedFee,
    FlagSpec,
    LearnedStat,
    NormalizedFeeLine,
    QuoteState,
    TripContext,
    TrueCost,
    flag_fingerprint,
)
from app.services.fee_intelligence import is_outlier
from app.services.money import format_usd

#: Departure deviation (minutes) beyond which the quote's time is flagged.
SCHEDULE_MISMATCH_MINUTES: Final = 120

_CHARGEABLE: Final = frozenset(
    {AmountStatus.STATED, AmountStatus.ESTIMATED, AmountStatus.NOT_STATED}
)


def _subject(line: NormalizedFeeLine) -> str:
    if line.category is FeeCategory.OTHER:
        return f"other.{slugify(line.label)}"
    return line.category.value


def _spec(
    type_: FlagType,
    severity: FlagSeverity,
    message: str,
    subject: str = "",
    *,
    details: Mapping[str, Any] | None = None,
    **links: Any,
) -> FlagSpec:
    return FlagSpec(
        type=type_,
        severity=severity,
        fingerprint=flag_fingerprint(type_, subject),
        message=message,
        details=dict(details or {}),
        **links,
    )


def _money(cents: int | None) -> str:
    return "unknown" if cents is None else format_usd(cents)


def _fee_flags(true_cost: TrueCost) -> list[FlagSpec]:
    out: list[FlagSpec] = []
    for ln in true_cost.lines:
        if ln.is_synthetic or ln.amount_status not in _CHARGEABLE or ln.counts_in_known:
            continue
        # A line the operator itself left open: estimated, hedged or "not included"
        # without an amount. Counting it only in the upper total could understate.
        if ln.amount_status is AmountStatus.ESTIMATED:
            what = f"estimated at {_money(ln.estimate_cents)}"
        elif ln.estimate_cents is not None:
            what = f"not stated (estimate {_money(ln.estimate_cents)})"
        else:
            what = "not stated"
        out.append(
            _spec(
                FlagType.AMBIGUOUS_CHARGE,
                FlagSeverity.WARNING,
                f"{ln.label} {what}; confirm the amount with the operator",
                _subject(ln),
                details={
                    "category": ln.category.value,
                    "label": ln.label,
                    "status": ln.amount_status.value,
                    "estimate_cents": ln.estimate_cents,
                    "estimate_basis": ln.estimate_basis,
                    "confidence": ln.confidence,
                },
                field_id=ln.field_id,
                fee_category=ln.category,
                source_document_id=ln.source_document_id,
            )
        )
    return out


def _expected_flags(expected: Sequence[ExpectedFee], true_cost: TrueCost) -> list[FlagSpec]:
    """Expected fees that ended up as synthetic lines or conditional charges."""
    handled = {
        ln.category
        for ln in true_cost.lines
        if ln.is_synthetic and ln.amount_status is AmountStatus.NOT_STATED
    }
    conditional = {e.category for e in true_cost.conditional_charges}
    out: list[FlagSpec] = []
    for exp in expected:
        if exp.category not in handled and exp.category not in conditional:
            continue
        details: dict[str, Any] = {
            "category": exp.category.value,
            "rule_id": exp.rule_id,
            "estimate_cents": exp.estimate_cents,
            "reason": exp.reason,
        }
        if exp.stat is not None:
            details.update(n=exp.stat.n, frequency=round(exp.stat.frequency, 3))
        label = exp.category.value.replace("_", " ")
        estimate = (
            f" (est. {format_usd(exp.estimate_cents)})" if exp.estimate_cents is not None else ""
        )
        if exp.severity is FlagSeverity.INFO and exp.rule_id == "deicing":
            type_ = FlagType.CONDITIONAL_CHARGE
            message = f"{exp.reason}{estimate}"
        elif exp.source == "learned":
            type_ = FlagType.LEARNED_FEE_MISSING
            message = f"{exp.reason}, but this quote does not mention it{estimate}"
        else:
            type_ = FlagType.EXPECTED_FEE_MISSING
            message = f"{exp.reason}; the quote does not mention {label}{estimate}"
        out.append(
            _spec(
                type_,
                exp.severity,
                message,
                exp.category.value,
                details=details,
                fee_category=exp.category,
            )
        )
    return out


def evaluate_flags(
    state: QuoteState,
    trip: TripContext,
    true_cost: TrueCost,
    expected: Sequence[ExpectedFee],
    now: datetime,
    *,
    learned: Mapping[FeeCategory, LearnedStat] | None = None,
) -> list[FlagSpec]:
    out: list[FlagSpec] = []

    # Required values.
    if true_cost.headline_cents is None and true_cost.unknown_currency is None:
        out.append(
            _spec(
                FlagType.MISSING_REQUIRED_FIELD,
                FlagSeverity.CRITICAL,
                "No headline price found",
                "headline_price",
                details={"key": "headline_price"},
            )
        )
    if not state.aircraft_model and state.aircraft_category is None:
        out.append(
            _spec(
                FlagType.MISSING_REQUIRED_FIELD,
                FlagSeverity.WARNING,
                "No aircraft found",
                "aircraft_model",
                details={"key": "aircraft_model"},
            )
        )
    if state.seats is not None and state.seats < trip.pax:
        seats_field = state.field("seats")
        out.append(
            _spec(
                FlagType.CAPACITY_INSUFFICIENT,
                FlagSeverity.CRITICAL,
                f"{state.seats} seats for {trip.pax} passengers",
                details={"seats": state.seats, "pax": trip.pax},
                field_id=seats_field.field_id if seats_field else None,
            )
        )

    # Price basis.
    if true_cost.headline_estimated:
        out.append(
            _spec(
                FlagType.HOURLY_ESTIMATE,
                FlagSeverity.WARNING,
                "Hourly quote without billable hours: "
                f"{_money(true_cost.headline_cents)} estimated from "
                + ("flight time" if state.flight_time_minutes else "the daily minimum"),
                details={
                    "headline_cents": true_cost.headline_cents,
                    "flight_time_minutes": state.flight_time_minutes,
                    "daily_minimum_hours": (
                        str(state.daily_minimum_hours)
                        if state.daily_minimum_hours is not None
                        else None
                    ),
                },
            )
        )
    if true_cost.unknown_currency is not None:
        out.append(
            _spec(
                FlagType.UNKNOWN_CURRENCY,
                FlagSeverity.CRITICAL,
                f"No exchange rate for {true_cost.unknown_currency}",
                true_cost.unknown_currency,
                details={"currency": true_cost.unknown_currency},
            )
        )
    if true_cost.fx is not None:
        out.append(
            _spec(
                FlagType.FX_CONVERTED,
                FlagSeverity.INFO,
                f"Converted from {true_cost.fx.currency} at {true_cost.fx.rate} USD "
                f"(rates as of {true_cost.fx.as_of.isoformat()})",
                true_cost.fx.currency,
                details={
                    "currency": true_cost.fx.currency,
                    "rate": str(true_cost.fx.rate),
                    "as_of": true_cost.fx.as_of.isoformat(),
                },
            )
        )

    # Fees.
    out.extend(_fee_flags(true_cost))
    out.extend(_expected_flags(expected, true_cost))
    if true_cost.all_in_itemized_conflict:
        itemized = [
            ln.label
            for ln in true_cost.lines
            if not ln.is_synthetic
            and ln.amount_status in (AmountStatus.STATED, AmountStatus.ESTIMATED)
            and not ln.explicitly_extra
        ]
        out.append(
            _spec(
                FlagType.ALL_IN_ITEMIZED_CONFLICT,
                FlagSeverity.INFO,
                'Quoted "all in" but also itemizes charges; itemized amounts were added '
                "(conservative)",
                details={"itemized": itemized},
            )
        )
    mismatch = true_cost.total_mismatch
    if mismatch is not None:
        if mismatch.direction == "above":
            severity = FlagSeverity.WARNING
            message = (
                f"Stated total {format_usd(mismatch.stated_cents)} is "
                f"{format_usd(mismatch.difference_cents)} above the itemized sum "
                f"{format_usd(mismatch.computed_cents)}; an unlisted charge is likely"
            )
        else:
            severity = FlagSeverity.INFO
            hint = (
                f"; excluding {', '.join(mismatch.reconciling_labels)} would reconcile it"
                if mismatch.reconciling_labels
                else ""
            )
            message = (
                f"Stated total {format_usd(mismatch.stated_cents)} is below the itemized sum "
                f"{format_usd(mismatch.computed_cents)}; the higher figure is used{hint}"
            )
        out.append(
            _spec(
                FlagType.TOTAL_MISMATCH,
                severity,
                message,
                details={
                    "direction": mismatch.direction,
                    "stated_cents": mismatch.stated_cents,
                    "computed_cents": mismatch.computed_cents,
                    "reconciling_labels": list(mismatch.reconciling_labels),
                },
            )
        )
    if learned:
        for ln in true_cost.lines:
            stat = learned.get(ln.category)
            if ln.is_synthetic or ln.amount_cents is None or stat is None:
                continue
            if is_outlier(ln.amount_cents, stat):
                out.append(
                    _spec(
                        FlagType.FEE_OUTLIER,
                        FlagSeverity.INFO,
                        f"{ln.label} {format_usd(ln.amount_cents)} is well above the usual "
                        f"{_money(stat.median_cents)} at {trip.first_leg.origin_icao}",
                        _subject(ln),
                        details={
                            "amount_cents": ln.amount_cents,
                            "median_cents": stat.median_cents,
                            "p75_cents": stat.p75_cents,
                            "n": stat.n_amounts,
                        },
                        field_id=ln.field_id,
                        fee_category=ln.category,
                    )
                )

    # Merge outcomes and provenance.
    for c in state.conflicts:
        type_ = (
            FlagType.CONFLICT_WITH_LOCKED
            if c.kind == "conflict_with_locked"
            else FlagType.CONFLICTING_VALUES
        )
        out.append(
            _spec(
                type_,
                FlagSeverity.WARNING,
                f"New value for {c.key} differs from the current one",
                c.key,
                details={
                    "key": c.key,
                    "current_value": c.current_value,
                    "candidate_value": c.candidate_value,
                    "candidate_field_id": str(c.candidate_field_id),
                },
                field_id=c.current_field_id,
                source_document_id=c.candidate_source_document_id,
            )
        )
    for r in state.revisions:
        out.append(
            _spec(
                FlagType.VALUE_REVISED,
                FlagSeverity.INFO,
                f"{r.key} was revised by a newer source",
                r.key,
                details={"previous": r.previous_value, "current": r.current_value},
                field_id=r.field_id,
                source_document_id=r.source_document_id,
            )
        )
    for f in state.fields:
        if not f.snippet_verified and not f.is_reviewed:
            out.append(
                _spec(
                    FlagType.SNIPPET_UNVERIFIED,
                    FlagSeverity.INFO,
                    f"Source text for {f.key} could not be found in the document",
                    f.key,
                    details={"key": f.key, "page": f.page},
                    field_id=f.field_id,
                    source_document_id=f.source_document_id,
                )
            )
    for issue in state.document_issues:
        failed = issue.kind == "extraction_failed"
        out.append(
            _spec(
                FlagType.EXTRACTION_FAILED if failed else FlagType.OCR_UNAVAILABLE,
                FlagSeverity.CRITICAL if failed else FlagSeverity.WARNING,
                issue.message,
                str(issue.source_document_id),
                details={"kind": issue.kind},
                source_document_id=issue.source_document_id,
            )
        )

    # Timing.
    if state.valid_until is not None and state.valid_until < now:
        out.append(
            _spec(
                FlagType.QUOTE_EXPIRED,
                FlagSeverity.WARNING,
                f"Quote expired {state.valid_until.isoformat()}",
                details={"valid_until": state.valid_until.isoformat()},
            )
        )
    if state.departure_local is not None:
        wanted = trip.first_leg.depart_local
        minutes = abs((state.departure_local - wanted).total_seconds()) / 60
        if state.departure_local.date() != wanted.date() or minutes > SCHEDULE_MISMATCH_MINUTES:
            out.append(
                _spec(
                    FlagType.SCHEDULE_MISMATCH,
                    FlagSeverity.INFO,
                    f"Quoted departure {state.departure_local:%d %b %H:%M} differs from the "
                    f"requested {wanted:%d %b %H:%M}",
                    details={
                        "quoted": state.departure_local.isoformat(),
                        "requested": wanted.isoformat(),
                    },
                )
            )
    return out
