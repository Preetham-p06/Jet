"""The trip's recommendation: ranking, signals, checks and ineligibility reasons."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.routes._views import recommendation
from app.deps import AnyUser, DbSession
from app.models.trip import Trip
from app.permissions import get_owned
from app.schemas.recommendation import RecommendationOut

router = APIRouter(tags=["recommendation"])


@router.get("/trips/{trip_id}/recommendation", summary="Ranking, signals and the five checks")
def get_recommendation(trip_id: uuid.UUID, ctx: AnyUser, db: DbSession) -> RecommendationOut:
    return recommendation(db, ctx, get_owned(db, Trip, trip_id, ctx))
