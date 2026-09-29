"""Fit score and recommendation, algorithm "fit-1" (spec §5). Pure and deterministic.

fit = round_half_up(sum(w_k * s_k) / sum(w_k)), s_k in [0, 100]. A missing
signal is imputed as the cohort median (neutral); a signal missing for every
quote is dropped and the weights renormalize. Recommended: the highest-fit
eligible quote (active, fully priced, no open blocking flags, enough seats,
not unavailable). Ties: lower known total, higher quote confidence, earlier
created_at, then id.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.services.contracts import (
    Eligibility,
    QuoteState,
    RecommendationResult,
    ScoreInput,
    Signal,
    TripContext,
    TrueCost,
)


def quote_confidence(state: QuoteState, review_threshold: int) -> tuple[int | None, float | None]:
    """(min effective confidence over material fields, money-weighted mean).

    Verified or edited counts as 100, accepted as max(confidence, threshold).
    """
    raise NotImplementedError


def build_score_input(
    state: QuoteState,
    true_cost: TrueCost,
    *,
    open_blocking_flags: int,
    quote_confidence: int | None,
) -> ScoreInput:
    raise NotImplementedError


def recommendation_eligibility(inp: ScoreInput, trip: TripContext) -> Eligibility:
    raise NotImplementedError


def score_trip(
    inputs: Sequence[ScoreInput],
    trip: TripContext,
    *,
    weights: Mapping[Signal, float] | None = None,
) -> RecommendationResult:
    raise NotImplementedError
