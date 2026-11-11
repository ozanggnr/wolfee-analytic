"""Decimal helpers shared by the quant modules.

Every public quant function runs inside one fixed decimal context (see
``fixed_context``), so results never depend on the context the caller happens
to have active, and products of stored amounts are exact.
"""
from __future__ import annotations

import functools
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, localcontext
from typing import Callable, Sequence, TypeVar

# NUMERIC(24,8) x NUMERIC(20,6) needs 44 significant digits to multiply exactly.
CONTEXT = Context(prec=60, rounding=ROUND_HALF_EVEN)

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)

# Internal scale for amounts and ratios produced by a division. Wider than any
# stored column, so storage rounding is the caller's last step, not ours.
SCALE = Decimal("1E-10")

# Inputs beyond these bounds are data errors, not money. Wider than the stored columns.
MAX_MAGNITUDE = Decimal("1E+18")
MAX_DECIMAL_PLACES = 18

_F = TypeVar("_F", bound=Callable)


def fixed_context(error: type[Exception] = ValueError) -> Callable[[_F], _F]:
    """Run the decorated function in ``CONTEXT``; report arithmetic failures as ``error``."""

    def decorate(func: _F) -> _F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with localcontext(CONTEXT):
                try:
                    return func(*args, **kwargs)
                except DecimalException as exc:
                    raise error(
                        f"amounts are outside the supported range ({type(exc).__name__})"
                    ) from exc

        return wrapper  # type: ignore[return-value]

    return decorate


def to_decimal(value: object, name: str) -> Decimal:
    """Return ``value`` as a finite, sanely sized Decimal; floats and other types are rejected."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise ValueError(f"{name} must be a Decimal or int, got {type(value).__name__}")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    if abs(result) >= MAX_MAGNITUDE:
        raise ValueError(f"{name} is too large")
    if -result.as_tuple().exponent > MAX_DECIMAL_PLACES:
        raise ValueError(f"{name} has too many decimal places")
    return result


def require_positive_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    return CONTEXT.divide(numerator, denominator)


def scaled(value: Decimal) -> Decimal:
    """Round to the internal scale (half-even)."""
    return value.quantize(SCALE, rounding=ROUND_HALF_EVEN, context=CONTEXT)


def proportion(amount: Decimal, part: Decimal, whole: Decimal) -> Decimal:
    """``amount * part / whole`` rounded to the internal scale."""
    return scaled(divide(CONTEXT.multiply(amount, part), whole))


def sample_stdev(values: Sequence[Decimal]) -> Decimal | None:
    """Sample standard deviation (n - 1 denominator); None for fewer than two values."""
    count = len(values)
    if count < 2:
        return None
    mean = divide(sum(values, ZERO), Decimal(count))
    squares = sum((CONTEXT.power(CONTEXT.subtract(v, mean), 2) for v in values), ZERO)
    return CONTEXT.sqrt(divide(squares, Decimal(count - 1)))


def weights_summing_to_one(amounts: Sequence[Decimal]) -> list[Decimal] | None:
    """Share of each amount in the total, at the internal scale.

    The largest amount (first one on a tie) absorbs the rounding remainder so
    the shares add up to exactly 1 and a zero amount always has a zero share.
    Returns None when the total is not positive.
    """
    total = sum(amounts, ZERO)
    if total <= ZERO:
        return None
    shares = [scaled(divide(amount, total)) for amount in amounts]
    largest = max(range(len(amounts)), key=lambda index: (amounts[index], -index))
    remainder = ONE - sum(shares, ZERO)
    return [share + remainder if index == largest else share for index, share in enumerate(shares)]
