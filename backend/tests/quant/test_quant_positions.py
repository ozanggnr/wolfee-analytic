"""Hand-checked ledger replay tests: holdings, cost basis, realised P/L, cash."""
from datetime import date
from decimal import Decimal as D, localcontext

import pytest

from quant.positions import build_positions, cash_summary, realized_pnl
from quant.types import CostBasisMethod, LedgerError, Transaction, TransactionType as T

FIFO = CostBasisMethod.FIFO
WAVG = CostBasisMethod.WEIGHTED_AVERAGE


def tx(id_, type_, day, quantity="0", price=None, fee="0", symbol="THYAO",
       currency="TRY", fx=None, voids=None):
    return Transaction(
        id=id_,
        type=type_,
        trade_date=date(2026, 1, day),
        currency=currency,
        quantity=D(quantity),
        price=None if price is None else D(price),
        fee=D(fee),
        symbol=symbol,
        fx_rate_to_base=None if fx is None else D(fx),
        voids_transaction_id=voids,
    )


# Two buys then a partial sell. Worked by hand:
#   lot 1: 10 x 100 + 5 fee  = 1005
#   lot 2: 10 x 120 + 5 fee  = 1205
#   sell : 15 x 150 - 15 fee = 2235 net proceeds
TWO_BUYS_ONE_SELL = [
    tx(1, T.BUY, 2, "10", "100", "5"),
    tx(2, T.BUY, 5, "10", "120", "5"),
    tx(3, T.SELL, 9, "15", "150", "15"),
]


def test_fifo_consumes_oldest_lots_first():
    realized = realized_pnl(TWO_BUYS_ONE_SELL, FIFO)

    # lot 1 fully sold: proceeds 2235 x 10/15 = 1490, cost 1005
    # lot 2 half sold : proceeds 2235 - 1490  = 745,  cost 1205 x 5/10 = 602.5
    assert [(r.quantity, r.cost, r.proceeds, r.pnl) for r in realized] == [
        (D("10"), D("1005"), D("1490"), D("485")),
        (D("5"), D("602.5"), D("745"), D("142.5")),
    ]
    assert [r.buy_transaction_id for r in realized] == [1, 2]
    assert all(r.sell_transaction_id == 3 for r in realized)
    assert realized[0].acquired == date(2026, 1, 2)
    assert realized[0].disposed == date(2026, 1, 9)


def test_fifo_remaining_position_keeps_unsold_cost():
    (position,) = build_positions(TWO_BUYS_ONE_SELL, FIFO)

    assert position.symbol == "THYAO"
    assert position.currency == "TRY"
    assert position.quantity == D("5")
    assert position.cost_basis == D("602.5")
    assert position.average_cost == D("120.5")


def test_weighted_average_pools_cost():
    realized = realized_pnl(TWO_BUYS_ONE_SELL, WAVG)
    (position,) = build_positions(TWO_BUYS_ONE_SELL, WAVG)

    # pool: 20 units costing 2210 -> 110.5 each; 15 sold cost 1657.5
    assert len(realized) == 1
    assert realized[0].cost == D("1657.5")
    assert realized[0].proceeds == D("2235")
    assert realized[0].pnl == D("577.5")
    assert realized[0].buy_transaction_id is None
    assert position.quantity == D("5")
    assert position.cost_basis == D("552.5")
    assert position.average_cost == D("110.5")


def test_cost_and_proceeds_are_conserved_when_fractions_do_not_divide_evenly():
    ledger = [
        tx(1, T.BUY, 2, "3", "10", "1"),      # cost 31
        tx(2, T.BUY, 3, "3", "11", "1"),      # cost 34
        tx(3, T.SELL, 4, "4", "12", "1"),     # proceeds 47; splits 3/4 and 1/4
    ]

    realized = realized_pnl(ledger, FIFO)
    (position,) = build_positions(ledger, FIFO)

    assert sum(r.proceeds for r in realized) == D("47")
    assert sum(r.cost for r in realized) + position.cost_basis == D("65")


def test_fully_sold_position_is_not_reported_as_a_holding():
    ledger = [tx(1, T.BUY, 2, "10", "100"), tx(2, T.SELL, 3, "10", "90")]

    assert build_positions(ledger, FIFO) == []
    assert realized_pnl(ledger, FIFO)[0].pnl == D("-100")


def test_transactions_are_replayed_by_trade_date_then_id_regardless_of_input_order():
    shuffled = [TWO_BUYS_ONE_SELL[2], TWO_BUYS_ONE_SELL[0], TWO_BUYS_ONE_SELL[1]]

    assert realized_pnl(shuffled, FIFO) == realized_pnl(TWO_BUYS_ONE_SELL, FIFO)
    assert build_positions(shuffled, FIFO) == build_positions(TWO_BUYS_ONE_SELL, FIFO)


def test_split_multiplies_quantity_and_keeps_total_cost():
    ledger = [
        tx(1, T.BUY, 2, "10", "100"),
        tx(2, T.SPLIT, 5, "2"),               # 2-for-1
        tx(3, T.SELL, 9, "5", "60"),
    ]

    (position,) = build_positions(ledger, FIFO)
    (lot,) = realized_pnl(ledger, FIFO)

    # 20 units costing 1000 -> 50 each; 5 sold cost 250, proceeds 300
    assert position.quantity == D("15")
    assert position.cost_basis == D("750")
    assert position.average_cost == D("50")
    assert (lot.cost, lot.proceeds, lot.pnl) == (D("250"), D("300"), D("50"))


def test_voided_transaction_and_its_reversal_are_both_ignored():
    ledger = [
        tx(1, T.BUY, 2, "10", "100"),
        tx(2, T.BUY, 3, "99", "1"),           # entered by mistake
        tx(3, T.BUY, 4, "0", voids=2),        # reversal row
    ]

    (position,) = build_positions(ledger, FIFO)

    assert position.quantity == D("10")
    assert position.cost_basis == D("1000")


def test_base_currency_amounts_use_the_fx_rate_stored_on_each_trade():
    ledger = [
        tx(1, T.BUY, 2, "10", "100", symbol="AAPL", currency="USD", fx="30"),
        tx(2, T.SELL, 9, "4", "110", symbol="AAPL", currency="USD", fx="35"),
    ]

    (lot,) = realized_pnl(ledger, FIFO)
    (position,) = build_positions(ledger, FIFO)

    # cost 400 USD x 30 = 12000; proceeds 440 USD x 35 = 15400
    assert lot.pnl == D("40")
    assert (lot.cost_base, lot.proceeds_base, lot.pnl_base) == (D("12000"), D("15400"), D("3400"))
    assert position.cost_basis == D("600")
    assert position.cost_basis_base == D("18000")


def test_base_currency_amounts_are_none_when_a_trade_has_no_stored_rate():
    ledger = [
        tx(1, T.BUY, 2, "10", "100", symbol="AAPL", currency="USD"),
        tx(2, T.SELL, 9, "4", "110", symbol="AAPL", currency="USD", fx="35"),
    ]

    (lot,) = realized_pnl(ledger, FIFO)
    (position,) = build_positions(ledger, FIFO)

    assert lot.pnl == D("40")
    assert lot.cost_base is None and lot.pnl_base is None
    assert position.cost_basis_base is None


def test_positions_are_returned_sorted_by_symbol():
    ledger = [
        tx(1, T.BUY, 2, "1", "10", symbol="THYAO"),
        tx(2, T.BUY, 2, "1", "10", symbol="AKBNK"),
    ]

    assert [p.symbol for p in build_positions(ledger, FIFO)] == ["AKBNK", "THYAO"]


@pytest.mark.parametrize(
    "ledger, message",
    [
        ([tx(1, T.SELL, 2, "1", "10")], "exceeds"),
        ([tx(1, T.BUY, 2, "5", "10"), tx(2, T.SELL, 3, "6", "10")], "exceeds"),
        ([tx(1, T.BUY, 2, "5")], "price"),
        ([tx(1, T.BUY, 2, "0", "10")], "quantity"),
        ([tx(1, T.BUY, 2, "5", "10", fee="-1")], "fee"),
        ([tx(1, T.BUY, 2, "5", "10", symbol=None)], "symbol"),
        ([tx(1, T.BUY, 2, "5", "10"), tx(1, T.BUY, 3, "5", "10")], "duplicate"),
        ([tx(1, T.BUY, 2, "5", "10"), tx(2, T.BUY, 3, "5", "10", currency="USD")], "currency"),
        ([tx(1, T.BUY, 2, "5", "10"), tx(2, T.BUY, 3, "0", voids=7)], "unknown"),
        ([tx(1, T.BUY, 2, "5", "10"), tx(2, T.BUY, 3, "0", voids=1), tx(3, T.BUY, 4, "0", voids=2)], "reversal"),
        ([tx(1, T.BUY, 2, "5", "10"), tx(2, T.SPLIT, 3, "0")], "ratio"),
    ],
)
def test_invalid_ledgers_are_rejected(ledger, message):
    with pytest.raises(LedgerError, match=message):
        build_positions(ledger, FIFO)


def test_float_amounts_are_rejected_to_keep_arithmetic_exact():
    bad = Transaction(id=1, type=T.BUY, trade_date=date(2026, 1, 2), currency="TRY",
                      quantity=10.0, price=D("1"), symbol="THYAO")

    with pytest.raises(LedgerError, match="Decimal"):
        build_positions([bad], FIFO)


def test_cash_summary_tracks_balance_dividends_and_fees_per_currency():
    ledger = [
        tx(1, T.DEPOSIT, 1, "5000", symbol=None),
        tx(2, T.BUY, 2, "10", "100", "5"),                    # -1005
        tx(3, T.DIVIDEND, 3, "10", "2", "0.3"),               # +19.7 net of withholding
        tx(4, T.FEE, 4, fee="1.5", symbol=None),              # -1.5
        tx(5, T.SELL, 5, "5", "120", "5"),                    # +595
        tx(6, T.WITHDRAWAL, 6, "100", symbol=None),           # -100
        tx(7, T.DEPOSIT, 7, "50", symbol=None, currency="USD"),
    ]

    summary = cash_summary(ledger)

    assert [(c.currency, c.amount) for c in summary.balances] == [("TRY", D("4508.2")), ("USD", D("50"))]
    assert [(c.currency, c.amount) for c in summary.dividends] == [("TRY", D("19.7"))]
    assert [(c.currency, c.amount) for c in summary.fees] == [("TRY", D("11.5"))]
    assert [(c.currency, c.amount) for c in summary.net_deposits] == [("TRY", D("4900")), ("USD", D("50"))]


def test_same_input_always_gives_the_same_output():
    assert realized_pnl(TWO_BUYS_ONE_SELL, FIFO) == realized_pnl(list(TWO_BUYS_ONE_SELL), FIFO)


# ------------------------------------------------------------ review fixes

def test_results_do_not_depend_on_the_callers_decimal_context():
    from decimal import localcontext

    expected = (realized_pnl(TWO_BUYS_ONE_SELL, FIFO), build_positions(TWO_BUYS_ONE_SELL, FIFO),
                cash_summary(TWO_BUYS_ONE_SELL))
    with localcontext() as ctx:
        ctx.prec = 3
        actual = (realized_pnl(TWO_BUYS_ONE_SELL, FIFO), build_positions(TWO_BUYS_ONE_SELL, FIFO),
                  cash_summary(TWO_BUYS_ONE_SELL))

    assert actual == expected


def test_large_amounts_multiply_exactly():
    ledger = [
        tx(1, T.BUY, 2, "1000000.123456", "99999999.12345678"),
        tx(2, T.SELL, 3, "1000000.123456", "99999999.12345678"),
    ]

    (lot,) = realized_pnl(ledger, FIFO)

    with localcontext() as ctx:
        ctx.prec = 60
        exact = D("1000000.123456") * D("99999999.12345678")
    assert lot.cost == exact
    assert len(lot.cost.as_tuple().digits) > 28
    assert lot.pnl == D("0")
    assert build_positions(ledger, FIFO) == []


@pytest.mark.parametrize("field", ["quantity", "price", "fee"])
def test_absurdly_large_amounts_are_rejected_with_the_transaction_id(field):
    values = {"quantity": "3", "price": "10", "fee": "0", field: "1E+25"}

    with pytest.raises(LedgerError, match="transaction 1 .*too large"):
        build_positions([tx(1, T.BUY, 2, values["quantity"], values["price"], values["fee"])], FIFO)
