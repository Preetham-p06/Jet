"""Typed values stored in `quote_fields.original_value` / `current_value`.

A field's `value_type` decides the JSON shape:

=========  ===========================================================
text       str (enum-valued keys hold the enum value)
int        int
number     float
bool       bool
money      {"amount_minor": int, "currency": "USD"}
datetime   ISO 8601 str ("2026-10-18T09:00" local, or aware for valid_until)
duration   int minutes
fee        `FeeValue`
=========  ===========================================================
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.errors import Unprocessable
from app.models.enums import (
    AircraftCategory,
    AmountStatus,
    Availability,
    FeeCategory,
    FeeUnit,
    FieldGroup,
    ValueType,
)
from app.schemas.common import DecimalNumber

FEE_PREFIX: Final = "fee."


class MoneyValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    amount_minor: int
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class FeeValue(BaseModel):
    """A fee field. `amount` is in the original currency's minor units."""

    model_config = ConfigDict(extra="forbid")

    category: FeeCategory
    label: str = Field(max_length=200)
    status: AmountStatus
    amount: MoneyValue | None = None
    unit: FeeUnit = FeeUnit.FLAT
    quantity: DecimalNumber | None = None
    percent: DecimalNumber | None = None
    explicitly_extra: bool = False
    hedged: bool = False


FieldValue = str | int | float | bool | MoneyValue | FeeValue

# Value type of every scalar key; fee keys are always `fee`.
SCALAR_VALUE_TYPES: Final[dict[str, ValueType]] = {
    "operator_name": ValueType.TEXT,
    "aircraft_model": ValueType.TEXT,
    "aircraft_category": ValueType.TEXT,
    "tail_number": ValueType.TEXT,
    "seats": ValueType.INT,
    "wifi": ValueType.BOOL,
    "departure_airport": ValueType.TEXT,
    "arrival_airport": ValueType.TEXT,
    "departure_local": ValueType.DATETIME,
    "flight_time_minutes": ValueType.DURATION,
    "pax": ValueType.INT,
    "availability": ValueType.TEXT,
    "currency": ValueType.TEXT,
    "headline_price": ValueType.MONEY,
    "hourly_rate": ValueType.MONEY,
    "billable_hours": ValueType.NUMBER,
    "daily_minimum_hours": ValueType.NUMBER,
    "stated_total": ValueType.MONEY,
    "all_in": ValueType.BOOL,
    "valid_until": ValueType.DATETIME,
}

# Text keys whose values must come from an enum.
_ENUM_TEXT_KEYS: Final[dict[str, type[AircraftCategory] | type[Availability]]] = {
    "aircraft_category": AircraftCategory,
    "availability": Availability,
}

_ADAPTERS: Final[dict[ValueType, TypeAdapter[Any]]] = {
    ValueType.TEXT: TypeAdapter(str),
    ValueType.INT: TypeAdapter(int),
    ValueType.NUMBER: TypeAdapter(float),
    ValueType.BOOL: TypeAdapter(bool),
    ValueType.MONEY: TypeAdapter(MoneyValue),
    ValueType.DATETIME: TypeAdapter(str),
    ValueType.DURATION: TypeAdapter(int),
    ValueType.FEE: TypeAdapter(FeeValue),
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(label: str) -> str:
    return _SLUG_RE.sub("_", label.casefold()).strip("_")[:40] or "item"


def fee_key(category: FeeCategory, label: str = "") -> str:
    """`fee.<category>`, or `fee.other.<slug>` so distinct "other" items coexist."""
    if category is FeeCategory.OTHER:
        return f"{FEE_PREFIX}other.{slugify(label)}"
    return f"{FEE_PREFIX}{category.value}"


def is_fee_key(key: str) -> bool:
    return key.startswith(FEE_PREFIX)


def group_for_key(key: str) -> FieldGroup:
    return FieldGroup.FEE if is_fee_key(key) else FieldGroup.SCALAR


def value_type_for_key(key: str) -> ValueType:
    if is_fee_key(key):
        return ValueType.FEE
    try:
        return SCALAR_VALUE_TYPES[key]
    except KeyError:
        raise Unprocessable(f"Unknown field key {key!r}", code="unknown_field_key") from None


def parse_field_value(key: str, raw: Any) -> Any:
    """Validate `raw` for `key` and return its JSON-ready form (for `current_value`).

    Raises `Unprocessable` (422) with the validation message on bad input.
    """
    value_type = value_type_for_key(key)
    try:
        value = _ADAPTERS[value_type].validate_python(raw, strict=value_type is ValueType.BOOL)
        if key in _ENUM_TEXT_KEYS:
            value = _ENUM_TEXT_KEYS[key](value).value
    except (ValidationError, ValueError) as exc:
        raise Unprocessable(
            f"Invalid value for {key}", code="invalid_field_value", fields={key: str(exc)}
        ) from None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def fee_amount_minor(value: Any) -> int | None:
    """Amount of a stored fee value, or None."""
    if isinstance(value, dict):
        amount = value.get("amount")
        if isinstance(amount, dict) and isinstance(amount.get("amount_minor"), int):
            return int(amount["amount_minor"])
    return None


def decimal_or_none(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))
