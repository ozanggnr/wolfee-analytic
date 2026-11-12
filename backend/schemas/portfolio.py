"""Portfolio request and response schemas (API_CONTRACT §5.1)."""
from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from schemas.common import StrictModel, UtcDateTime, reject_unprintable

# Decision D3 (REQ-15): TRY is the only base currency for now. Valuation FX exists
# only as XXX/TRY in exchange_rates.
SUPPORTED_BASE_CURRENCIES = ("TRY",)

PortfolioKind = Literal["real", "paper"]
PortfolioName = Annotated[str, Field(min_length=1, max_length=100), AfterValidator(reject_unprintable)]


class PortfolioCreate(StrictModel):
    name: PortfolioName
    base_currency: str = Field(..., min_length=3, max_length=3)
    kind: PortfolioKind = "real"

    @field_validator("base_currency")
    @classmethod
    def validate_base_currency(cls, value: str) -> str:
        code = value.upper() if value.isascii() else value
        if code not in SUPPORTED_BASE_CURRENCIES:
            allowed = ", ".join(SUPPORTED_BASE_CURRENCIES)
            raise ValueError(f"base_currency must be one of: {allowed}")
        return code


class PortfolioUpdate(StrictModel):
    name: PortfolioName


class PortfolioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_currency: str
    kind: PortfolioKind
    created_at: UtcDateTime
    archived_at: Optional[UtcDateTime] = None
