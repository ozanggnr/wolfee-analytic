"""Transaction request and response schemas (API_CONTRACT §5.1, DATABASE_CONTRACT §3.3).

Field meaning by type follows the ledger convention shared with the quant layer:

* BUY / SELL           quantity units at price each, plus fee.
* DIVIDEND             quantity units paying price each; fee is tax or charges withheld.
* SPLIT                quantity is the ratio of new units per old unit (2 for a 2-for-1 split).
* DEPOSIT / WITHDRAWAL quantity is the cash amount in currency.
* FEE                  fee is the amount charged.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.common import DecimalInput, StrictModel, UtcDateTime, fixed_scale, reject_unprintable

TransactionType = Literal["BUY", "SELL", "DIVIDEND", "FEE", "DEPOSIT", "WITHDRAWAL", "SPLIT"]

INSTRUMENT_TYPES = frozenset({"BUY", "SELL", "DIVIDEND", "SPLIT"})
PRICED_TYPES = frozenset({"BUY", "SELL", "DIVIDEND"})
CASH_TYPES = frozenset({"DEPOSIT", "WITHDRAWAL"})

SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:[.\-=][A-Za-z0-9]+)*$")
CURRENCY_PATTERN = re.compile(r"^[A-Za-z]{3}$")
EXCHANGE_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
NOTE_WHITESPACE = "\n\t"
EARLIEST_TRADE_DATE = date(1900, 1, 1)
# "Today" differs by a day between UTC and the user's market; allow that much and no more.
TRADE_DATE_TOLERANCE = timedelta(days=1)
ZERO = Decimal(0)

QuantityIn = Annotated[Decimal, DecimalInput, Field(ge=0, max_digits=24, decimal_places=8)]
MoneyIn = Annotated[Decimal, DecimalInput, Field(ge=0, max_digits=20, decimal_places=6)]
FxRateIn = Annotated[Decimal, DecimalInput, Field(gt=0, max_digits=20, decimal_places=8)]

QuantityOut = Annotated[Decimal, fixed_scale(8)]
MoneyOut = Annotated[Decimal, fixed_scale(6)]
FxRateOut = Annotated[Decimal, fixed_scale(8)]


class TransactionCreate(StrictModel):
    type: TransactionType
    symbol: Optional[str] = Field(None, min_length=1, max_length=30)
    exchange: Optional[str] = Field(None, min_length=1, max_length=10)
    quantity: QuantityIn = ZERO
    price: Optional[MoneyIn] = None
    fee: MoneyIn = ZERO
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    fx_rate_to_base: Optional[FxRateIn] = None
    trade_date: date
    executed_at: Optional[datetime] = None
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not SYMBOL_PATTERN.match(value):
            raise ValueError("symbol may contain only letters, digits and single . - = separators")
        return value.upper()

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not EXCHANGE_PATTERN.match(value):
            raise ValueError("exchange may contain only letters, digits and underscores")
        return value.upper()

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not CURRENCY_PATTERN.match(value):
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return value.upper()

    @field_validator("trade_date")
    @classmethod
    def validate_trade_date(cls, value: date) -> date:
        latest = datetime.now(timezone.utc).date() + TRADE_DATE_TOLERANCE
        if value < EARLIEST_TRADE_DATE or value > latest:
            raise ValueError("trade_date must not be in the future or before 1900-01-01")
        return value

    @field_validator("executed_at")
    @classmethod
    def validate_executed_at(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("executed_at must include a UTC offset")
        return value.astimezone(timezone.utc)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: Optional[str]) -> Optional[str]:
        return reject_unprintable(value, allowed=NOTE_WHITESPACE) if value else None

    @model_validator(mode="after")
    def validate_fields_for_type(self) -> "TransactionCreate":
        kind = self.type
        if kind in INSTRUMENT_TYPES and not self.symbol:
            raise ValueError(f"symbol is required for {kind}")
        if kind in CASH_TYPES and self.symbol:
            raise ValueError(f"symbol is not allowed for {kind}")
        if self.exchange and not self.symbol:
            raise ValueError("exchange is only meaningful together with symbol")
        if not self.symbol and not self.currency:
            raise ValueError(f"currency is required for {kind} without a symbol")

        if kind in PRICED_TYPES and self.price is None:
            raise ValueError(f"price is required for {kind}")
        if kind not in PRICED_TYPES and self.price is not None:
            raise ValueError(f"price is not allowed for {kind}")

        if kind == "FEE":
            if self.fee <= ZERO:
                raise ValueError("fee must be greater than zero for FEE")
            if self.quantity != ZERO:
                raise ValueError("quantity is not allowed for FEE; put the amount in fee")
        elif self.quantity <= ZERO:
            raise ValueError(f"quantity must be greater than zero for {kind}")

        if kind in CASH_TYPES | {"SPLIT"} and self.fee != ZERO:
            raise ValueError(f"fee is not allowed for {kind}; record a separate FEE transaction")
        return self


class TransactionVoid(StrictModel):
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: Optional[str]) -> Optional[str]:
        return reject_unprintable(value, allowed=NOTE_WHITESPACE) if value else None


class TransactionOut(BaseModel):
    id: int
    portfolio_id: int
    type: TransactionType
    symbol: Optional[str] = None
    exchange: Optional[str] = None
    quantity: QuantityOut
    price: Optional[MoneyOut] = None
    fee: MoneyOut
    currency: str
    fx_rate_to_base: Optional[FxRateOut] = None
    trade_date: date
    executed_at: Optional[UtcDateTime] = None
    note: Optional[str] = None
    source: str
    voids_transaction_id: Optional[int] = None
    voided_by_transaction_id: Optional[int] = None
    created_at: UtcDateTime
