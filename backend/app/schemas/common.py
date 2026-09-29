"""Shared schema building blocks."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Generic, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

T = TypeVar("T")


class APIModel(BaseModel):
    """Base for request bodies: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ORMModel(BaseModel):
    """Base for responses built from ORM rows."""

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_row(cls, obj: Any, **extra: Any) -> Self:
        """Validate from an ORM row plus computed fields the row lacks."""
        data = {
            name: getattr(obj, name)
            for name in cls.model_fields
            if name not in extra and hasattr(obj, name)
        }
        return cls.model_validate({**data, **extra})


class Page(BaseModel, Generic[T]):
    """Every list endpoint returns `{items, total}`; `total` ignores limit/offset."""

    items: list[T]
    total: int


class ErrorOut(BaseModel):
    detail: str
    code: str
    fields: dict[str, Any] | None = None


class OkOut(BaseModel):
    ok: bool = True


# Percentages are Decimals internally and JSON numbers on the wire.
Percent = Annotated[
    Decimal,
    Field(ge=0, le=100, max_digits=5, decimal_places=2),
    PlainSerializer(float, return_type=float, when_used="json"),
]
DecimalNumber = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
Cents = Annotated[int, Field(description="Integer USD cents")]
ICAO = Annotated[str, Field(pattern=r"^[A-Z0-9]{3,4}$", examples=["KTEB"])]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorOut, "description": "Not authenticated"},
    403: {"model": ErrorOut, "description": "Forbidden (role or CSRF)"},
    404: {"model": ErrorOut, "description": "Not found (including other workspaces' rows)"},
    409: {"model": ErrorOut, "description": "Conflict or stale version"},
    422: {"model": ErrorOut, "description": "Validation error"},
    501: {"model": ErrorOut, "description": "Not implemented yet"},
}
