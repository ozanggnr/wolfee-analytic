"""Format computed figures as the facts an explanation may use.

Formatting is fixed (two decimals, thousands separators, half-even rounding) so
the same input always yields the same strings. Values that could not be
computed are stated as unavailable, never filled in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Iterable, Mapping

from ai.guardrails import Fact, one_line
from quant._math import CONTEXT
from quant.types import PortfolioValuation, RiskMetrics

_CENT = Decimal("0.01")
_HUNDRED = Decimal(100)


def portfolio_facts(
    valuation: PortfolioValuation, risk: RiskMetrics | None = None
) -> tuple[tuple[Fact, ...], datetime | None]:
    """Facts for ``valuation`` (and ``risk`` when given) plus the age of the oldest price used."""
    facts = [Fact("Number of holdings", str(len(valuation.positions)))]
    facts.extend(_totals(valuation))
    facts.extend(_largest_holding(valuation))
    facts.extend(_risk_facts(risk))
    price_fact, inputs_as_of = _price_data(valuation)
    facts.extend(price_fact)
    return tuple(facts), inputs_as_of


_PARTIAL = " of the holdings that could be valued (partial, not the whole portfolio)"


def _totals(valuation: PortfolioValuation) -> list[Fact]:
    """Totals, worded as partial whenever some holdings could not be valued."""
    currency = valuation.base_currency
    missing = ", ".join(valuation.unvalued_symbols)
    if valuation.total_market_value is None:
        return [Fact("Total market value", f"not available — missing price or exchange rate for: {missing}")]

    if valuation.is_complete:
        value_label, cost_label, pnl_label = "Total market value", "Total cost", "Unrealised profit or loss"
        facts = []
    else:
        value_label, cost_label, pnl_label = (
            f"Market value{_PARTIAL}", f"Cost{_PARTIAL}", f"Unrealised profit or loss{_PARTIAL}"
        )
        facts = [Fact("Holdings left out of every total below (no price or exchange rate)", missing)]

    facts.append(Fact(value_label, _money(valuation.total_market_value, currency)))
    if valuation.total_cost_basis is not None:
        facts.append(Fact(cost_label, _money(valuation.total_cost_basis, currency)))
    if valuation.total_unrealized_pnl is not None:
        facts.append(Fact(pnl_label, _money(valuation.total_unrealized_pnl, currency, signed=True)))
    return facts


def _largest_holding(valuation: PortfolioValuation) -> list[Fact]:
    weighted = [p for p in valuation.positions if p.weight is not None]
    if not weighted:
        return []
    largest = min(weighted, key=lambda p: (-p.weight, p.symbol))
    whole = "the portfolio" if valuation.is_complete else "the holdings that could be valued"
    return [Fact("Largest holding", f"{largest.symbol} at {_percent(largest.weight * _HUNDRED)} of {whole}")]


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


# --------------------------------------------------------------------------
# Market and single-instrument facts (decision D5)
#
# Input rows are the display dicts of the market cache: symbol, name, price,
# change_pct, currency, market_type, previous_close, day_low, day_high, volume
# and, only when computed from real history, rsi, ma_20, volatility_pct with
# indicators_as_of. The card label (``prediction``) is never turned into a fact.
# --------------------------------------------------------------------------

NO_MARKET_DATA = Fact("Market data", "not available yet — no instrument has a price")
MAX_MOVERS = 3

_MAX_NAME_LENGTH = 40
_MAX_AMOUNT = Decimal("1E+18")
_RSI_LOW = Decimal(30)
_RSI_HIGH = Decimal(70)
_GROUP_TITLES = {"BIST": "Turkish market (BIST)", "GLOBAL": "Global markets", "COMMODITY": "Commodities"}
_CURRENCY_CODE = re.compile(r"[A-Z]{3}")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class _Quote:
    label: str
    symbol: str
    group: str
    price: Decimal
    change_pct: Decimal | None
    currency: str


def market_facts(stocks: Iterable[Mapping[str, object]] | None) -> tuple[Fact, ...]:
    """Facts describing today's market from cached quotes; ``(NO_MARKET_DATA,)`` when there are none.

    Counts, simple averages of the day's changes per market, and the largest
    rises and falls. RSI counts appear only for rows whose RSI was computed
    from real price history.
    """
    rows = list(stocks or ())
    quotes = sorted(
        (quote for quote in map(_quote, rows) if quote is not None and quote.change_pct is not None),
        key=lambda quote: quote.symbol,
    )
    if not quotes:
        return (NO_MARKET_DATA,)

    facts = [Fact("Instruments with a price and a daily change", str(len(quotes)))]
    for group, title in _GROUP_TITLES.items():
        members = [quote.change_pct for quote in quotes if quote.group == group]
        if not members:
            continue
        average = CONTEXT.divide(sum(members, Decimal(0)), Decimal(len(members)))
        rose = sum(1 for change in members if change > 0)
        fell = sum(1 for change in members if change < 0)
        facts.append(Fact(f"{title}: number of instruments", str(len(members))))
        facts.append(Fact(f"{title}: simple average of the daily changes", _percent(average, signed=True)))
        facts.append(
            Fact(f"{title}: instruments that rose, fell or did not move",
                 f"{rose} rose, {fell} fell, {len(members) - rose - fell} unchanged")
        )

    risers = sorted((q for q in quotes if q.change_pct > 0), key=lambda q: (-q.change_pct, q.symbol))
    fallers = sorted((q for q in quotes if q.change_pct < 0), key=lambda q: (q.change_pct, q.symbol))
    if risers:
        facts.append(Fact("Largest rises today", _movers(risers)))
    if fallers:
        facts.append(Fact("Largest falls today", _movers(fallers)))
    facts.extend(_market_rsi_facts(rows))
    return tuple(facts)


def stock_facts(stock: Mapping[str, object] | None) -> tuple[Fact, ...]:
    """Facts describing one instrument from its cached quote.

    Indicators are included only when ``indicators_as_of`` shows they were
    computed from real price history; otherwise the facts say they are not
    available.
    """
    quote = _quote(stock)
    if quote is None:
        return (Fact("Price data for this instrument", "not available"),)

    facts = [
        Fact("Instrument", quote.label),
        Fact("Market", _GROUP_TITLES[quote.group]),
        Fact("Price", _amount(quote.price, quote.currency)),
    ]
    if quote.change_pct is not None:
        facts.append(Fact("Change today", _percent(quote.change_pct, signed=True)))
    previous_close = _positive(stock.get("previous_close"))
    if previous_close is not None:
        facts.append(Fact("Previous close", _amount(previous_close, quote.currency)))
    low, high = _positive(stock.get("day_low")), _positive(stock.get("day_high"))
    if low is not None and high is not None:
        facts.append(
            Fact("Lowest and highest price today", f"{_round(low):,.2f} to {_amount(high, quote.currency)}")
        )
    volume = _positive(stock.get("volume"))
    if volume is not None:
        facts.append(Fact("Volume today", f"{int(volume):,}"))
    facts.extend(_indicator_facts(stock, quote))
    return tuple(facts)


def _indicator_facts(stock: Mapping[str, object], quote: _Quote) -> list[Fact]:
    as_of = stock.get("indicators_as_of")
    real = {field: _positive(stock.get(field)) for field in ("rsi", "ma_20", "volatility_pct")}
    if not isinstance(as_of, str) or not _ISO_DATE.fullmatch(as_of) or not any(
        value is not None for value in real.values()
    ):
        return [Fact("RSI, 20-day average and volatility", "not available — no price history yet")]

    facts = []
    if real.get("rsi") is not None:
        facts.append(Fact("14-day RSI (Wilder)", f"{_round(real['rsi']):.2f}"))
    average = real.get("ma_20")
    if average is not None:
        gap = (CONTEXT.divide(quote.price, average) - 1) * _HUNDRED
        side = "above" if gap > 0 else "below" if gap < 0 else "level with"
        facts.append(Fact("20-day average price", _amount(average, quote.currency)))
        facts.append(
            Fact("Price compared with the 20-day average", f"{_percent(gap, signed=True)} ({side} the average)")
        )
    if real.get("volatility_pct") is not None:
        facts.append(Fact("Annualised 20-day volatility", _percent(real["volatility_pct"])))
    facts.append(Fact("Indicators calculated from daily closing prices up to", as_of))
    return facts


def _market_rsi_facts(rows: Iterable[object]) -> list[Fact]:
    values = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        as_of = row.get("indicators_as_of")
        value = _positive(row.get("rsi"))
        if value is not None and isinstance(as_of, str) and _ISO_DATE.fullmatch(as_of):
            values.append(value)
    if not values:
        return [Fact("14-day RSI", "not available — no price history yet")]
    return [
        Fact("Instruments with a 14-day RSI calculated from price history", str(len(values))),
        Fact("Of those, 14-day RSI below 30", str(sum(1 for value in values if value < _RSI_LOW))),
        Fact("Of those, 14-day RSI above 70", str(sum(1 for value in values if value > _RSI_HIGH))),
    ]


def _movers(quotes: list[_Quote]) -> str:
    return "; ".join(f"{q.label} {_percent(q.change_pct, signed=True)}" for q in quotes[:MAX_MOVERS])


def _quote(row: object) -> _Quote | None:
    """A cached quote with a usable symbol and price, or None."""
    if not isinstance(row, Mapping):
        return None
    raw_symbol = row.get("symbol")
    price = _positive(row.get("price"))
    if not isinstance(raw_symbol, str) or not raw_symbol.strip() or price is None:
        return None

    symbol = _clean(raw_symbol.strip().upper().removesuffix(".IS"))
    name = _clean(row.get("name") or "")
    currency = row.get("currency")
    return _Quote(
        label=f"{name} ({symbol})" if name and name.upper() != symbol else symbol,
        symbol=symbol,
        group=_group(row, raw_symbol.strip().upper()),
        price=price,
        change_pct=_decimal(row.get("change_pct")),
        currency=currency if isinstance(currency, str) and _CURRENCY_CODE.fullmatch(currency) else "",
    )


def _group(row: Mapping[str, object], symbol: str) -> str:
    market_type = row.get("market_type")
    if market_type in _GROUP_TITLES:
        return market_type
    if "=" in symbol:
        return "COMMODITY"
    if symbol.endswith(".IS") or row.get("currency") == "TRY":
        return "BIST"
    return "GLOBAL"


def _clean(text: object) -> str:
    """Provider text as one plain line: no markup characters, bounded length."""
    plain = one_line(text).replace("`", "").replace("[", "(").replace("]", ")")
    return plain[:_MAX_NAME_LENGTH].strip()


def _amount(value: Decimal, currency: str) -> str:
    return f"{_round(value):,.2f} {currency}".strip()


def _decimal(value: object) -> Decimal | None:
    """``value`` as a finite Decimal of sane size, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() and abs(number) < _MAX_AMOUNT else None


def _positive(value: object) -> Decimal | None:
    number = _decimal(value)
    return number if number is not None and number > 0 else None
