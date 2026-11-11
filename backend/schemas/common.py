"""Shared building blocks for the /api/v1 schemas (API_CONTRACT §4)."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated, Any, Generic, List, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200
MAX_INT32 = 2**31 - 1
MAX_INT64 = 2**63 - 1

T = TypeVar("T")


def reject_binary_float(value: Any) -> Any:
    """Money must arrive as a decimal string (or a whole number), never as a binary float."""
    if isinstance(value, (bool, float)):
        raise ValueError('must be a decimal string such as "12.50", not a fractional JSON number')
    if isinstance(value, str) and not value.isascii():
        raise ValueError("must use the digits 0-9")
    return value


DecimalInput = BeforeValidator(reject_binary_float)

# Control, format and surrogate characters: invisible in a UI, and Postgres rejects NUL in text.
_UNPRINTABLE_CATEGORIES = frozenset({"Cc", "Cf", "Cs"})


def reject_unprintable(value: str, *, allowed: str = "") -> str:
    """Refuse text containing invisible or control characters (except those in `allowed`)."""
    for char in value:
        if char not in allowed and unicodedata.category(char) in _UNPRINTABLE_CATEGORIES:
            raise ValueError("must not contain control or invisible characters")
    return value


def fixed_scale(scale: int) -> PlainSerializer:
    """Serialise a Decimal as a plain string with exactly `scale` decimal places."""
    quantum = Decimal(1).scaleb(-scale)
    return PlainSerializer(lambda value: format(value.quantize(quantum), "f"), return_type=str)


def to_utc_iso(value: datetime) -> str:
    """ISO-8601 in UTC with an offset. SQLite returns naive datetimes; they are stored as UTC."""
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(timezone.utc).isoformat()


UtcDateTime = Annotated[datetime, PlainSerializer(to_utc_iso, return_type=str)]


class StrictModel(BaseModel):
    """Request bodies reject unknown fields so typos are not silently ignored."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    limit: int
    offset: int
