"""Hand-checked valuation, multi-currency conversion and allocation tests."""
from datetime import date, datetime, timezone
from decimal import Decimal as D

import pytest

from quant.allocation import allocation_by, concentration
from quant.types import Freshness, FxRate, Position, PriceQuote
from quant.valuation import value_positions

AS_OF = datetime(2026, 1, 9, 15, 0, tzinfo=timezone.utc)


def position(symbol, currency, quantity, cost, cost_base):
    return Position(
        symbol=symbol, currency=currency, quantity=D(quantity), cost_basis=D(cost),
        average_cost=D(cost) / D(quantity),
        cost_basis_base=None if cost_base is None else D(cost_base),
    )


def quote(symbol, price, currency):
    return PriceQuote(symbol=symbol, price=D(price), currency=currency, as_of=AS_OF,
                      freshness=Freshness.DELAYED, source="test")


USD_TRY = FxRate(base="USD", quote="TRY", rate=D("35"), as_of=date(2026, 1, 9), source="test")

POSITIONS = [
    position("THYAO", "TRY", "10", "1000", "1000"),
    position("AAPL", "USD", "5", "500", "15000"),     # bought at 30 TRY per USD
]
QUOTES = {"THYAO": quote("THYAO", "120", "TRY"), "AAPL": quote("AAPL", "110", "USD")}


def test_values_each_position_in_its_own_and_in_base_currency():
    valuation = value_positions(POSITIONS, QUOTES, {"USD": USD_TRY}, "TRY")
    aapl, thyao = valuation.positions                 # sorted by symbol

    assert (thyao.market_value, thyao.unrealized_pnl) == (D("1200"), D("200"))
    assert (thyao.market_value_base, thyao.unrealized_pnl_base) == (D("1200"), D("200"))
    # 5 x 110 = 550 USD; x 35 = 19250 TRY; base cost 15000 -> +4250 including FX gain
    assert (aapl.market_value, aapl.unrealized_pnl) == (D("550"), D("50"))
    assert (aapl.market_value_base, aapl.unrealized_pnl_base) == (D("19250"), D("4250"))
    assert aapl.quote is QUOTES["AAPL"]
    assert aapl.unavailable_reason is None


def test_totals_and_weights_in_base_currency():
    valuation = value_positions(POSITIONS, QUOTES, {"USD": USD_TRY}, "TRY")
    aapl, thyao = valuation.positions

    assert valuation.base_currency == "TRY"
    assert valuation.is_complete is True
    assert valuation.total_market_value == D("20450")
    assert valuation.total_cost_basis == D("16000")
    assert valuation.total_unrealized_pnl == D("4450")
    assert aapl.weight + thyao.weight == D("1")
    assert thyao.weight.quantize(D("0.000001")) == D("0.058680")   # 1200 / 20450


def test_missing_quote_is_reported_and_totals_are_withheld_not_estimated():
    valuation = value_positions(POSITIONS, {"THYAO": QUOTES["THYAO"]}, {"USD": USD_TRY}, "TRY")
    aapl, thyao = valuation.positions

    assert aapl.market_value is None and aapl.market_value_base is None
    assert aapl.unavailable_reason == "missing_quote"
    assert thyao.market_value == D("1200")
    assert thyao.weight is None
    assert valuation.is_complete is False
    assert valuation.total_market_value is None
    assert valuation.total_unrealized_pnl is None
    assert valuation.unvalued_symbols == ("AAPL",)


def test_missing_fx_rate_keeps_local_value_but_withholds_base_value():
    valuation = value_positions(POSITIONS, QUOTES, {}, "TRY")
    aapl = valuation.positions[0]

    assert aapl.market_value == D("550")
    assert aapl.market_value_base is None
    assert aapl.unavailable_reason == "missing_fx_rate"
    assert valuation.is_complete is False


def test_quote_in_a_different_currency_is_not_used():
    quotes = {**QUOTES, "AAPL": quote("AAPL", "110", "EUR")}

    aapl = value_positions(POSITIONS, quotes, {"USD": USD_TRY}, "TRY").positions[0]

    assert aapl.market_value is None
    assert aapl.unavailable_reason == "quote_currency_mismatch"


def test_unknown_base_cost_withholds_base_pnl_only():
    positions = [position("AAPL", "USD", "5", "500", None)]

    valuation = value_positions(positions, QUOTES, {"USD": USD_TRY}, "TRY")

    assert valuation.positions[0].market_value_base == D("19250")
    assert valuation.positions[0].unrealized_pnl_base is None
    assert valuation.total_market_value == D("19250")
    assert valuation.total_unrealized_pnl is None


def test_fx_rate_must_convert_into_the_base_currency():
    wrong = FxRate(base="USD", quote="EUR", rate=D("0.9"), as_of=date(2026, 1, 9), source="test")

    with pytest.raises(ValueError, match="USD/TRY"):
        value_positions(POSITIONS, QUOTES, {"USD": wrong}, "TRY")


def test_empty_portfolio_is_complete_with_zero_totals():
    valuation = value_positions([], {}, {}, "TRY")

    assert valuation.positions == ()
    assert valuation.is_complete is True
    assert valuation.total_market_value == D("0")


def test_allocation_groups_weights_by_a_supplied_classification():
    valuation = value_positions(POSITIONS, QUOTES, {"USD": USD_TRY}, "TRY")

    by_market = allocation_by(valuation, {"THYAO": "BIST", "AAPL": "US"})
    by_currency = allocation_by(valuation, {p.symbol: p.currency for p in valuation.positions})

    assert [(s.group, s.market_value_base) for s in by_market] == [("US", D("19250")), ("BIST", D("1200"))]
    assert sum(s.weight for s in by_market) == D("1")
    assert [s.group for s in by_currency] == ["USD", "TRY"]


def test_allocation_is_unavailable_for_an_incomplete_valuation():
    valuation = value_positions(POSITIONS, {}, {}, "TRY")

    assert allocation_by(valuation, {}) is None


def test_concentration_metrics():
    result = concentration({"A": D("0.5"), "B": D("0.3"), "C": D("0.2")})

    # HHI = 0.25 + 0.09 + 0.04
    assert result.hhi == D("0.38")
    assert (result.largest_symbol, result.largest_weight) == ("A", D("0.5"))
    assert result.effective_holdings.quantize(D("0.0001")) == D("2.6316")
    assert concentration({}) is None


# ------------------------------------------------------------ review fixes

def test_rounding_remainder_never_lands_on_a_zero_value_position():
    names = ["A", "B", "C", "D", "E", "F", "G", "Z"]
    positions = [position(name, "TRY", "1", "1", "1") for name in names]
    quotes = {name: quote(name, "1", "TRY") for name in names[:-1]}
    quotes["Z"] = quote("Z", "0.0000000000001", "TRY")

    valuation = value_positions(positions, quotes, {}, "TRY")
    weights = [p.weight for p in valuation.positions]

    assert all(weight >= D("0") for weight in weights)
    assert sum(weights) == D("1")
    assert weights[-1] == D("0E-10")


def test_weights_helper_puts_the_remainder_on_the_largest_amount():
    from quant._math import weights_summing_to_one

    weights = weights_summing_to_one([D(1)] * 7 + [D(0)])

    assert weights[-1] == D("0")
    assert sum(weights) == D("1")
    assert weights_summing_to_one([D(0), D(0)]) is None


@pytest.mark.parametrize("price", ["0", "-5"])
def test_non_positive_quote_price_is_not_used(price):
    quotes = {**QUOTES, "AAPL": quote("AAPL", price, "USD")}

    valuation = value_positions(POSITIONS, quotes, {"USD": USD_TRY}, "TRY")

    assert valuation.positions[0].market_value is None
    assert valuation.positions[0].unavailable_reason == "invalid_quote_price"
    assert valuation.total_market_value is None


def test_quote_for_another_symbol_is_not_used():
    quotes = {**QUOTES, "AAPL": quote("MSFT", "110", "USD")}

    aapl = value_positions(POSITIONS, quotes, {"USD": USD_TRY}, "TRY").positions[0]

    assert aapl.market_value is None
    assert aapl.unavailable_reason == "quote_symbol_mismatch"


def test_valuation_does_not_depend_on_the_callers_decimal_context():
    from decimal import localcontext

    expected = value_positions(POSITIONS, QUOTES, {"USD": USD_TRY}, "TRY")
    with localcontext() as ctx:
        ctx.prec = 3
        actual = value_positions(POSITIONS, QUOTES, {"USD": USD_TRY}, "TRY")
        slices = allocation_by(actual, {"THYAO": "BIST", "AAPL": "US"})

    assert actual == expected
    assert slices == allocation_by(expected, {"THYAO": "BIST", "AAPL": "US"})
