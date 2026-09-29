"""Operators."""

from __future__ import annotations

import uuid

from pydantic import AwareDatetime, BaseModel, EmailStr, Field

from app.models.enums import OperatorSource
from app.schemas.common import ICAO, APIModel, ORMModel


class OperatorCreate(APIModel):
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, pattern=r"^\+[1-9]\d{6,14}$")  # E.164
    website: str | None = Field(default=None, max_length=500)
    home_base_icao: ICAO | None = None
    notes: str | None = Field(default=None, max_length=5000)


class OperatorPatch(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    aliases: list[str] | None = Field(default=None, max_length=20)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, pattern=r"^\+[1-9]\d{6,14}$")
    website: str | None = Field(default=None, max_length=500)
    home_base_icao: ICAO | None = None
    notes: str | None = Field(default=None, max_length=5000)
    is_archived: bool | None = None


class OperatorOut(ORMModel):
    id: uuid.UUID
    name: str
    normalized_name: str
    aliases: list[str]
    email: str | None
    email_domain: str | None
    phone: str | None
    website: str | None
    home_base_icao: str | None
    notes: str | None
    source: OperatorSource
    is_archived: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime


class OperatorStats(BaseModel):
    quote_count: int
    trips_requested: int
    trips_quoted: int
    trips_declined: int
    median_response_hours: float | None


class OperatorDetailOut(OperatorOut):
    stats: OperatorStats
