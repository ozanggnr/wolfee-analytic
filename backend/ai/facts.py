"""Format computed portfolio figures as the facts an explanation may use.

Formatting is fixed (two decimals, thousands separators, half-even rounding) so
the same valuation always yields the same strings. Values that could not be
computed are stated as unavailable, never filled in.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal

from ai.guardrails import Fact
from quant._math import CONTEXT
from quant.types import PortfolioValuation, RiskMetrics

_CENT = Decimal("0.01")
_HUNDRED = Decimal(100)


def portfolio_facts(
    valuation: PortfolioValuation, risk: RiskMetrics | None = None
) -> tuple[tuple[Fact, ...], datetime | None]:
    """Facts for ``valuation`` (and ``risk`` when given) plus the age of the oldest price used."""
    currency = valuation.base_currency
    facts = [Fact("Number of holdings", str(len(valuation.positions)))]

    if valuation.total_market_value is None:
        missing = ", ".join(valuation.unvalued_symbols)
        facts.append(Fact("Total market value", f"not available — missing price or exchange rate for: {missing}"))
    else:
        facts.append(Fact("Total market value", _money(valuation.total_market_value, currency)))
    if valuation.total_cost_basis is not None:
        facts.append(Fact("Total cost", _money(valuation.total_cost_basis, currency)))
    if valuation.total_unrealized_pnl is not None:
        facts.append(
            Fact("Unrealised profit or loss", _money(valuation.total_unrealized_pnl, currency, signed=True))
        )

    facts.extend(_largest_holding(valuation))
    facts.extend(_risk_facts(risk))
    price_fact, inputs_as_of = _price_data(valuation)
    facts.extend(price_fact)
    return tuple(facts), inputs_as_of


def _largest_holding(valuation: PortfolioValuation) -> list[Fact]:
    weighted = [p for p in valuation.positions if p.weight is not None]
    if not weighted:
        return []
    largest = min(weighted, key=lambda p: (-p.weight, p.symbol))
    return [Fact("Largest holding", f"{largest.symbol} at {_percent(largest.weight * _HUNDRED)} of the portfolio")]


def _risk_facts(risk: RiskMetrics | None) -> list[Fact]:
    if risk is None or risk.period_return_pct is None:
        return []
    facts = [
        Fact(
            f"Return over the period {risk.start.isoformat()} to {risk.end.isoformat()}",
            _percent(risk.period_return_pct, signed=True),
        )
    ]
    if risk.annualized_volatility_pct is not None:
        facts.append(Fact("Annualised volatility in that period", _percent(risk.annualized_volatility_pct)))
    if risk.max_drawdown_pct is not None:
        facts.append(Fact("Largest fall from a peak in that period", _percent(risk.max_drawdown_pct)))
    return facts


def _price_data(valuation: PortfolioValuation) -> tuple[list[Fact], datetime | None]:
    quotes = [p.quote for p in valuation.positions if p.quote is not None]
    if not quotes:
        return [], None
    oldest = min(_utc(quote.as_of) for quote in quotes)
    freshness = ", ".join(sorted({quote.freshness.value for quote in quotes}))
    sources = ", ".join(sorted({quote.source for quote in quotes}))
    text = f"{freshness} (source: {sources}); oldest price from {oldest:%Y-%m-%d %H:%M} UTC"
    return [Fact("Price data", text)], oldest


def _utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("quote timestamps must be timezone-aware")
    return moment.astimezone(timezone.utc)


def _round(value: Decimal) -> Decimal:
    """Two decimals, half-even, independent of the caller's context; never a negative zero."""
    rounded = value.quantize(_CENT, rounding=ROUND_HALF_EVEN, context=CONTEXT)
    return abs(rounded) if rounded.is_zero() else rounded


def _money(value: Decimal, currency: str, signed: bool = False) -> str:
    return f"{_round(value):{'+' if signed else ''},.2f} {currency}"


def _percent(value: Decimal, signed: bool = False) -> str:
    return f"{_round(value):{'+' if signed else ''}.2f}%"
