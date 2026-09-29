"""True cost (spec §4): `normalize_quote` is pure.

headline = stated | hourly_rate x max(billable_hours, daily_minimum_hours)
         | hourly_rate x ceil_0.1(flight_time/60) (estimated, `hourly_estimate` warning)
known = upper = headline, then per line:
  stated / edited         -> known += amt, upper += amt
  percent (FET 7.5 %)     -> amt = round(pct x (headline + stated fees except
                             fet/segment_fees/taxes/international))
  included / waived       -> +0, even when an amount is written
  estimated, accepted     -> known += amt, upper += amt
  estimated, unaccepted   -> upper += amt; not fully priced
  not_stated              -> upper += estimate (operator | rule | learned median)
  not_applicable          -> 0
all_in: `ALL_IN_COVERED` categories without a line get a synthetic included line
  (included_by all_in); itemized and "extra" amounts are still added.
WARNING expected fees -> synthetic not_stated lines; INFO -> `conditional_charges`.
Stated total (tolerance max($1, 0.1 %)): above -> known = stated (warning);
  below -> keep computed, name reconciling lines by subset-sum over <= 12 lines.

`is_fully_priced` here covers everything the numbers themselves can tell:
no unaccepted estimate, no unresolved not_stated line or expected fee, no
estimated headline, a known currency and a headline. Open blocking *flags*
(which depend on broker resolutions) are applied on top by the caller; the
recommendation gate checks them separately.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Final

from app.models.enums import (
    FEE_CATEGORY_ORDER,
    AmountStatus,
    FeeCategory,
    FeeUnit,
    FlagSeverity,
    IncludedBy,
)
from app.services import fee_rules
from app.services import fx as fx_mod
from app.services.contracts import (
    ALL_IN_COVERED,
    FET_BASE_EXCLUDED,
    ExpectedFee,
    FeeLineState,
    FxApplied,
    FxTable,
    NormalizedFeeLine,
    QuoteState,
    TotalMismatch,
    TripContext,
    TrueCost,
)
from app.services.money import percent_of, to_int_half_up

SUBSET_SUM_MAX_LINES = 12

FET_PERCENT: Final = fee_rules.FET_RATE * 100

CATEGORY_LABELS: Final[Mapping[FeeCategory, str]] = {
    FeeCategory.POSITIONING: "Positioning",
    FeeCategory.RAMP_HANDLING: "Ramp / handling",
    FeeCategory.FUEL_SURCHARGE: "Fuel surcharge",
    FeeCategory.CATERING: "Catering",
    FeeCategory.CREW_OVERNIGHT: "Crew overnight",
    FeeCategory.CREW: "Crew",
    FeeCategory.OVERNIGHT: "Aircraft overnight",
    FeeCategory.LANDING: "Landing fees",
    FeeCategory.DEICING: "De-icing",
    FeeCategory.INTERNATIONAL: "International fees",
    FeeCategory.FET: "Federal excise tax (7.5%)",
    FeeCategory.SEGMENT_FEES: "Segment fees",
    FeeCategory.TAXES: "Taxes",
    FeeCategory.WIFI_FEE: "Wi-Fi fee",
    FeeCategory.OTHER: "Other",
}

_ORDER: Final = {c: i for i, c in enumerate(FEE_CATEGORY_ORDER)}
_AMOUNT_STATUSES: Final = frozenset(
    {AmountStatus.STATED, AmountStatus.ESTIMATED, AmountStatus.NOT_STATED}
)


@dataclass(slots=True)
class _Converter:
    fx: FxTable
    unknown: str | None = None

    def usd(self, amount_minor: int | None, currency: str) -> int | None:
        if amount_minor is None:
            return None
        try:
            return fx_mod.to_usd_cents(amount_minor, currency, self.fx)
        except fx_mod.UnknownCurrency as exc:
            self.unknown = self.unknown or exc.currency
            return None


def total_tolerance_cents(stated_cents: int) -> int:
    """max($1, 0.1 % of the stated total)."""
    return max(100, to_int_half_up(Decimal(abs(stated_cents)) / 1000))


def reconciling_lines(
    lines: Sequence[NormalizedFeeLine], difference_cents: int, tolerance_cents: int
) -> tuple[NormalizedFeeLine, ...] | None:
    """Smallest subset of counted lines whose sum matches `difference_cents`
    within tolerance, or None (considers at most `SUBSET_SUM_MAX_LINES`)."""
    target = abs(difference_cents)
    candidates = [ln for ln in lines if ln.counts_in_known and ln.amount_cents][
        :SUBSET_SUM_MAX_LINES
    ]
    for size in range(1, len(candidates) + 1):
        for combo in itertools.combinations(candidates, size):
            if abs(sum(ln.amount_cents or 0 for ln in combo) - target) <= tolerance_cents:
                return combo
    return None


def _multiplier(line: FeeLineState, trip: TripContext) -> Decimal:
    if line.unit in (FeeUnit.FLAT, FeeUnit.PERCENT):
        return Decimal(1)
    if line.quantity is not None:
        return line.quantity
    if line.unit is FeeUnit.PER_LEG:
        return Decimal(len(trip.legs))
    if line.unit is FeeUnit.PER_PAX:
        return Decimal(trip.pax)
    return Decimal(1)


def _is_percent(line: FeeLineState) -> bool:
    return line.percent is not None and line.amount_minor is None


def _line_label(line: FeeLineState) -> str:
    return line.label or CATEGORY_LABELS[line.category]


def _base_line(line: FeeLineState, state: QuoteState) -> NormalizedFeeLine:
    return NormalizedFeeLine(
        category=line.category,
        label=_line_label(line),
        amount_status=line.status,
        counts_in_known=False,
        counts_in_upper=False,
        sort_order=0,
        original_amount_minor=line.amount_minor,
        original_currency=(line.currency or state.currency)
        if line.amount_minor is not None
        else None,
        unit=line.unit,
        quantity=line.quantity,
        percent=line.percent,
        explicitly_extra=line.explicitly_extra,
        confidence=line.confidence,
        review_status=line.review_status,
        field_id=line.field_id,
        source_document_id=line.source_document_id,
        page=line.page,
    )


def _priced(
    base: NormalizedFeeLine,
    line: FeeLineState,
    amount: int | None,
    expected_by_cat: Mapping[FeeCategory, ExpectedFee],
    fallback: tuple[int | None, str | None] = (None, None),
) -> NormalizedFeeLine:
    """Apply the status semantics to a line whose amount (USD cents) is known or None."""
    status = line.status
    if status in (AmountStatus.INCLUDED, AmountStatus.WAIVED):
        return replace(
            base,
            included_by=IncludedBy.EXPLICIT if status is AmountStatus.INCLUDED else None,
        )
    if status is AmountStatus.NOT_APPLICABLE:
        return base
    if status is AmountStatus.STATED:
        ok = amount is not None
        return replace(base, amount_cents=amount, counts_in_known=ok, counts_in_upper=ok)
    if status is AmountStatus.ESTIMATED:
        ok = amount is not None
        return replace(
            base,
            amount_cents=amount,
            estimate_cents=amount,
            estimate_basis="operator_estimate" if ok else None,
            counts_in_known=ok and line.is_accepted,
            counts_in_upper=ok,
        )
    # NOT_STATED: estimate from the operator, else the matching rule or learned median.
    basis: str | None = "operator_estimate" if amount is not None else None
    estimate = amount
    if estimate is None and (exp := expected_by_cat.get(line.category)) is not None:
        estimate = exp.estimate_cents
        basis = _basis(exp) if estimate is not None else None
    if estimate is None:
        estimate, basis = fallback
    return replace(
        base,
        estimate_cents=estimate,
        estimate_basis=basis,
        amount_cents=estimate if line.is_accepted else None,
        counts_in_known=estimate is not None and line.is_accepted,
        counts_in_upper=estimate is not None,
    )


def _basis(exp: ExpectedFee) -> str:
    return exp.rule_id if exp.source == "learned" else f"rule:{exp.rule_id}"


def _fet_base(headline: int, lines: Sequence[NormalizedFeeLine]) -> int:
    return headline + sum(
        ln.amount_cents or 0
        for ln in lines
        if ln.counts_in_known and ln.category not in FET_BASE_EXCLUDED and ln.percent is None
    )


def _unresolved(line: NormalizedFeeLine) -> bool:
    return line.amount_status in _AMOUNT_STATUSES and not line.counts_in_known


def _sort_key(item: tuple[int, NormalizedFeeLine]) -> tuple[int, int, int]:
    idx, ln = item
    return (_ORDER[ln.category], 1 if ln.is_synthetic else 0, idx)


def normalize_quote(
    state: QuoteState,
    trip: TripContext,
    fx: FxTable,
    expected: Sequence[ExpectedFee],
) -> TrueCost:
    conv = _Converter(fx)
    ccy = state.currency.upper()
    fx_applied: FxApplied | None = None
    if ccy != fx.base and fx.knows(ccy):
        fx_applied = FxApplied(currency=ccy, rate=fx_mod.rate_for(ccy, fx), as_of=fx.as_of)

    head_minor, headline_estimated = fee_rules.headline_minor(state)
    headline = conv.usd(head_minor, ccy)

    expected_by_cat: dict[FeeCategory, ExpectedFee] = {}
    for exp in expected:
        expected_by_cat.setdefault(exp.category, exp)

    # Pass 1: every non-percent line.
    lines: list[NormalizedFeeLine | None] = []
    for fee in state.fees:
        if _is_percent(fee):
            lines.append(None)
            continue
        amount_one = conv.usd(fee.amount_minor, fee.currency or ccy)
        amount = None if amount_one is None else to_int_half_up(amount_one * _multiplier(fee, trip))
        fallback = (
            fee_rules.rule_estimate(fee.category, state, trip)
            if fee.status is AmountStatus.NOT_STATED and amount is None
            else (None, None)
        )
        lines.append(_priced(_base_line(fee, state), fee, amount, expected_by_cat, fallback))

    # Pass 2: percent lines on the FET base of what is known so far.
    known_so_far = [ln for ln in lines if ln is not None]
    for i, fee in enumerate(state.fees):
        if lines[i] is not None:
            continue
        pct_amount = (
            None
            if headline is None or fee.percent is None
            else percent_of(_fet_base(headline, known_so_far), fee.percent)
        )
        lines[i] = _priced(_base_line(fee, state), fee, pct_amount, expected_by_cat)
    real = [ln for ln in lines if ln is not None]
    present = {ln.category for ln in real}

    # "All in": covered categories without a line of their own.
    synthetic: list[NormalizedFeeLine] = []
    if state.all_in:
        for cat in FEE_CATEGORY_ORDER:
            if cat in ALL_IN_COVERED and cat not in present:
                synthetic.append(
                    NormalizedFeeLine(
                        category=cat,
                        label=f"{CATEGORY_LABELS[cat]} (all in)",
                        amount_status=AmountStatus.INCLUDED,
                        included_by=IncludedBy.ALL_IN,
                        counts_in_known=False,
                        counts_in_upper=False,
                        sort_order=0,
                    )
                )
                present.add(cat)
    itemized_conflict = state.all_in and any(
        ln.amount_status in (AmountStatus.STATED, AmountStatus.ESTIMATED)
        and not ln.explicitly_extra
        and (ln.original_amount_minor is not None or ln.amount_cents is not None)
        for ln in real
    )

    # Expected fees the quote does not mention.
    conditional: list[ExpectedFee] = []
    for exp in expected:
        if exp.category in present:
            continue
        if exp.severity is FlagSeverity.INFO:
            conditional.append(exp)
            continue
        estimate = exp.estimate_cents
        if exp.rule_id == "fet" and headline is not None:
            estimate = percent_of(_fet_base(headline, real), FET_PERCENT)
        synthetic.append(
            NormalizedFeeLine(
                category=exp.category,
                label=CATEGORY_LABELS[exp.category],
                amount_status=AmountStatus.NOT_STATED,
                counts_in_known=False,
                counts_in_upper=estimate is not None,
                sort_order=0,
                estimate_cents=estimate,
                estimate_basis=_basis(exp) if estimate is not None else None,
                percent=FET_PERCENT if exp.rule_id == "fet" else None,
                unit=FeeUnit.PERCENT if exp.rule_id == "fet" else FeeUnit.FLAT,
            )
        )
        present.add(exp.category)

    ordered = sorted(enumerate([*real, *synthetic]), key=_sort_key)
    final = tuple(replace(ln, sort_order=i) for i, (_, ln) in enumerate(ordered))

    known: int | None = None
    upper: int | None = None
    if headline is not None:
        known = headline + sum(ln.amount_cents or 0 for ln in final if ln.counts_in_known)
        upper = headline + sum(
            (ln.amount_cents if ln.amount_cents is not None else ln.estimate_cents) or 0
            for ln in final
            if ln.counts_in_upper
        )

    stated = conv.usd(state.stated_total_minor, ccy)
    mismatch: TotalMismatch | None = None
    if stated is not None and known is not None and upper is not None:
        tol = total_tolerance_cents(stated)
        if stated - known > tol:
            mismatch = TotalMismatch(direction="above", stated_cents=stated, computed_cents=known)
            known = stated
            upper = max(upper, stated)
        elif known - stated > tol:
            subset = reconciling_lines(final, known - stated, tol)
            mismatch = TotalMismatch(
                direction="below",
                stated_cents=stated,
                computed_cents=known,
                reconciling_labels=tuple(ln.label for ln in subset or ()),
            )

    fully_priced = (
        headline is not None
        and not headline_estimated
        and conv.unknown is None
        and not any(_unresolved(ln) for ln in final)
    )
    return TrueCost(
        headline_cents=headline,
        headline_estimated=headline_estimated,
        known_total_cents=known,
        upper_total_cents=upper,
        is_fully_priced=fully_priced,
        lines=final,
        conditional_charges=tuple(conditional),
        stated_total_cents=stated,
        total_mismatch=mismatch,
        fx=fx_applied,
        unknown_currency=conv.unknown,
        all_in_itemized_conflict=itemized_conflict,
    )
