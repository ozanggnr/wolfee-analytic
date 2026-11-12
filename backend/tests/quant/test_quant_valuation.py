"""Hand-checked valuation, multi-currency conversion and allocation tests."""
from datetime import date, datetime, timezone
from decimal import Decimal as D

import pytest

from quant.allocation import allocation_by, concentration
from quant.types import CurrencyAmount, Freshness, FxRate, Position, PriceQuote
from quant.valuation import convert_amounts, value_positions

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


def test_missing_quote_is_reported_and_the_rest_is_still_totalled():
    valuation = value_positions(POSITIONS, {"THYAO": QUOTES["THYAO"]}, {"USD": USD_TRY}, "TRY")
    aapl, thyao = valuation.positions

    assert aapl.market_value is None and aapl.market_value_base is None
    assert aapl.unavailable_reason == "missing_quote"
    assert aapl.weight is None
    assert thyao.market_value == D("1200")
    assert thyao.weight == D("1")
    assert valuation.is_complete is False
    # Only THYAO is counted: value 1200, cost 1000. Nothing is assumed for AAPL.
    assert valuation.total_market_value == D("1200")
    assert valuation.total_cost_basis == D("1000")
    assert valuation.total_unrealized_pnl == D("200")
    assert valuation.unvalued_symbols == ("AAPL",)


def test_missing_fx_rate_marks_only_that_position_and_the_rest_still_totals():
    # REQ-14 / D3. Four holdings, no EUR rate:
    #   THYAO 10 x 120          =  1200 TRY, cost  1000
    #   AAPL   5 x 110 USD x 35 = 19250 TRY, cost 15000
    #   MSFT   2 x 250 USD x 35 = 17500 TRY, cost 12000
    #   SAP    1 x 120 EUR      -> no rate, left out
    positions = POSITIONS + [
        position("MSFT", "USD", "2", "400", "12000"),
        position("SAP", "EUR", "1", "100", "3600"),
    ]
    quotes = {**QUOTES, "MSFT": quote("MSFT", "250", "USD"), "SAP": quote("SAP", "120", "EUR")}

    valuation = value_positions(positions, quotes, {"USD": USD_TRY}, "TRY")
    by_symbol = {p.symbol: p for p in valuation.positions}
    sap = by_symbol["SAP"]

    assert sap.market_value == D("120") and sap.unrealized_pnl == D("20")
    assert sap.market_value_base is None and sap.unrealized_pnl_base is None
    assert sap.unavailable_reason == "missing_fx_rate"
    assert sap.weight is None
    assert [by_symbol[s].unavailable_reason for s in ("AAPL", "MSFT", "THYAO")] == [None, None, None]

    assert valuation.is_complete is False
    assert valuation.unvalued_symbols == ("SAP",)
    assert valuation.total_market_value == D("37950")
    assert valuation.total_cost_basis == D("28000")
    assert valuation.total_unrealized_pnl == D("9950")
    # Weights are shares of the 37950 that could be valued.
    assert by_symbol["THYAO"].weight == D("0.0316205534")     # 1200 / 37950
    assert sum(by_symbol[s].weight for s in ("AAPL", "MSFT", "THYAO")) == D("1")


def test_totals_are_withheld_when_no_position_can_be_valued():
    valuation = value_positions(POSITIONS, {}, {}, "TRY")

    assert valuation.is_complete is False
    assert valuation.unvalued_symbols == ("AAPL", "THYAO")
    assert valuation.total_market_value is None
    assert valuation.total_cost_basis is None
    assert valuation.total_unrealized_pnl is None
    assert all(p.weight is None for p in valuation.positions)


def test_partial_cost_and_pnl_are_withheld_when_a_valued_position_has_no_base_cost():
    positions = POSITIONS + [position("MSFT", "USD", "2", "400", None)]
    quotes = {"THYAO": QUOTES["THYAO"], "MSFT": quote("MSFT", "250", "USD")}

    valuation = value_positions(positions, quotes, {"USD": USD_TRY}, "TRY")

    assert valuation.unvalued_symbols == ("AAPL",)
    assert valuation.total_market_value == D("18700")          # 1200 + 17500
    assert valuation.total_cost_basis is None
    assert valuation.total_unrealized_pnl is None


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


# ------------------------------------------------------- convert_amounts

def amount(currency, value):
    return CurrencyAmount(currency, D(value))


def test_amounts_are_converted_to_try_and_totalled():
    eur_try = FxRate(base="EUR", quote="TRY", rate=D("38.5"), as_of=date(2026, 1, 9), source="test")

    result = convert_amounts(
        [amount("USD", "100"), amount("TRY", "250"), amount("EUR", "10")],
        {"USD": USD_TRY, "EUR": eur_try},
    )

    # 100 x 35 = 3500; 250 stays 250; 10 x 38.5 = 385
    assert [(i.currency, i.amount, i.amount_base) for i in result.items] == [
        ("USD", D("100"), D("3500")), ("TRY", D("250"), D("250")), ("EUR", D("10"), D("385")),
    ]
    assert result.items[0].fx_rate is USD_TRY
    assert result.items[1].fx_rate is None                    # base currency needs no rate
    assert result.base_currency == "TRY"
    assert result.total_base == D("4135")
    assert result.is_complete is True
    assert result.missing_currencies == ()


def test_amount_without_a_rate_is_marked_and_the_rest_still_totals():
    result = convert_amounts(
        [amount("USD", "100"), amount("TRY", "250"), amount("EUR", "10"), amount("GBP", "1")],
        {"USD": USD_TRY},
    )
    usd, try_, eur, gbp = result.items

    assert (eur.amount_base, eur.unavailable_reason) == (None, "missing_fx_rate")
    assert (gbp.amount_base, gbp.unavailable_reason) == (None, "missing_fx_rate")
    assert usd.unavailable_reason is None and try_.unavailable_reason is None
    assert result.total_base == D("3750")                     # 3500 + 250 only
    assert result.is_complete is False
    assert result.missing_currencies == ("EUR", "GBP")


def test_negative_amounts_convert_with_their_sign():
    result = convert_amounts([amount("USD", "-50"), amount("TRY", "1000")], {"USD": USD_TRY})

    assert result.items[0].amount_base == D("-1750")
    assert result.total_base == D("-750")


def test_no_amounts_total_zero_and_nothing_convertible_totals_none():
    assert convert_amounts([], {}).total_base == D("0")
    assert convert_amounts([], {}).is_complete is True

    nothing = convert_amounts([amount("USD", "100")], {})
    assert nothing.total_base is None
    assert nothing.is_complete is False


def test_convert_amounts_rejects_bad_input():
    with pytest.raises(ValueError, match="USD/TRY"):
        convert_amounts([amount("USD", "1")], {"USD": USD_TRY}, base_currency="EUR")
    with pytest.raises(ValueError, match="positive"):
        zero = FxRate(base="USD", quote="TRY", rate=D("0"), as_of=date(2026, 1, 9), source="test")
        convert_amounts([amount("USD", "1")], {"USD": zero})
    with pytest.raises(ValueError, match="Decimal"):
        convert_amounts([CurrencyAmount("USD", 1.5)], {"USD": USD_TRY})
    with pytest.raises(ValueError, match="currency"):
        convert_amounts([amount("usd", "1")], {"USD": USD_TRY})


def test_convert_amounts_does_not_depend_on_the_callers_decimal_context():
    from decimal import localcontext

    amounts = [amount("USD", "123456789.123456"), amount("TRY", "0.01")]
    expected = convert_amounts(amounts, {"USD": USD_TRY})
    with localcontext() as ctx:
        ctx.prec = 3
        assert convert_amounts(amounts, {"USD": USD_TRY}) == expected
    assert expected.total_base == D("4320987619.330960")      # 123456789.123456 x 35 + 0.01


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
    assert valuation.is_complete is False
    assert valuation.total_market_value == D("1200")           # THYAO only


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
