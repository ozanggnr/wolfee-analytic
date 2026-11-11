"""Hand-checked indicator and risk-metric tests."""
from datetime import date
from decimal import Decimal as D

import pytest

from quant.indicators import RsiMethod, annualized_volatility_pct, rsi, sma
from quant.risk import risk_metrics
from quant.types import DatedValue

Q4 = D("0.0001")


def closes(*values):
    return [D(str(v)) for v in values]


def test_wilder_rsi_matches_hand_calculation():
    # deltas +1 +1 -1 +2, period 2
    # seed: gain 1, loss 0 -> (0.5, 0.5) -> (1.25, 0.25); RSI = 100 x 1.25 / 1.5
    assert rsi(closes(10, 11, 12, 11, 13), period=2).quantize(Q4) == D("83.3333")


def test_simple_average_rsi_matches_the_existing_export_formula():
    # last two deltas -1 +2 -> mean gain 1, mean loss 0.5; RSI = 100 x 1 / 1.5
    result = rsi(closes(10, 11, 12, 11, 13), period=2, method=RsiMethod.SIMPLE)

    assert result.quantize(Q4) == D("66.6667")


def test_rsi_is_100_when_there_are_no_losses_and_0_when_no_gains():
    assert rsi(closes(1, 2, 3, 4), period=3) == D("100")
    assert rsi(closes(4, 3, 2, 1), period=3) == D("0")


def test_rsi_is_none_rather_than_estimated():
    assert rsi(closes(1, 2, 3), period=14) is None          # not enough history
    assert rsi(closes(5, 5, 5, 5), period=3) is None        # flat: 0 / 0 is undefined
    assert rsi([], period=14) is None


def test_default_rsi_period_is_14():
    series = closes(*range(1, 16))                          # 14 deltas, all gains

    assert rsi(series) == D("100")
    assert rsi(series[:-1]) is None


def test_sma_is_the_mean_of_the_last_window():
    assert sma(closes(1, 2, 3, 4), 2) == D("3.5")
    assert sma(closes(1, 2, 3, 4), 4) == D("2.5")
    assert sma(closes(1, 2, 3), 4) is None


def test_annualized_volatility_matches_hand_calculation():
    # returns +10% -10% +10%; sample variance 1/75; x sqrt(252) -> sqrt(3.36) = 1.833030
    result = annualized_volatility_pct(closes(100, 110, 99, "108.9"), window=3)

    assert result.quantize(Q4) == D("183.3030")


def test_annualized_volatility_needs_a_full_window():
    assert annualized_volatility_pct(closes(100, 110, 99), window=3) is None


@pytest.mark.parametrize("bad", [[1.5, 2.5, 3.5], [D("1"), D("0"), D("2")], [D("1"), D("-1")]])
def test_indicators_reject_floats_and_non_positive_prices(bad):
    with pytest.raises(ValueError):
        sma(bad, 2)


@pytest.mark.parametrize("call", [lambda: rsi(closes(1, 2), period=0), lambda: sma(closes(1, 2), 0)])
def test_indicators_reject_non_positive_windows(call):
    with pytest.raises(ValueError):
        call()


def values(*rows):
    return [
        DatedValue(date=date(2026, 1, day), value=D(str(value)), net_flow=D(str(flow)))
        for day, value, flow in rows
    ]


def test_risk_metrics_match_hand_calculation():
    series = values((1, 100, 0), (2, 110, 0), (3, 99, 0), (4, "108.9", 0))

    result = risk_metrics(series)

    assert result.observations == 4
    assert result.period_return_pct.quantize(Q4) == D("8.9000")
    assert result.annualized_volatility_pct.quantize(Q4) == D("183.3030")
    # peak 110 on day 2, trough 99 on day 3 -> 10% drawdown
    assert result.max_drawdown_pct.quantize(Q4) == D("10.0000")
    assert result.max_drawdown_peak == date(2026, 1, 2)
    assert result.max_drawdown_trough == date(2026, 1, 3)


def test_deposits_are_not_counted_as_performance():
    # 100 grows to 110, then 100 is deposited the same day -> value 210, return 10%
    result = risk_metrics(values((1, 100, 0), (2, 210, 100)))

    assert result.period_return_pct == D("10")
    assert result.max_drawdown_pct == D("0")
    assert result.annualized_volatility_pct is None          # one return is not enough


def test_risk_metrics_sort_by_date():
    series = values((1, 100, 0), (2, 110, 0), (3, 99, 0), (4, "108.9", 0))

    assert risk_metrics(list(reversed(series))) == risk_metrics(series)


def test_risk_metrics_with_too_little_history_return_none_fields():
    result = risk_metrics(values((1, 100, 0)))

    assert result.observations == 1
    assert result.period_return_pct is None
    assert result.max_drawdown_pct is None
    assert risk_metrics([]).observations == 0


@pytest.mark.parametrize(
    "rows",
    [
        ((1, 100, 0), (1, 110, 0)),      # duplicate date
        ((1, 0, 0), (2, 110, 0)),        # cannot compute a return from zero
        ((1, -5, 0), (2, 110, 0)),
    ],
)
def test_risk_metrics_reject_unusable_series(rows):
    with pytest.raises(ValueError):
        risk_metrics(values(*rows))


# ------------------------------------------------------------ review fixes

def test_indicators_and_risk_do_not_depend_on_the_callers_decimal_context():
    from decimal import localcontext

    series = closes(10, 11, 12, 11, 13, 12.5, 14, 13.2, 15, 14.1, 13.9, 15.5, 16, 15.2, 17, 16.4)
    points = values((1, 100, 0), (2, 110, 0), (3, 99, 0), (4, "108.9", 0))
    expected = (rsi(series), sma(series, 5), annualized_volatility_pct(series, window=10), risk_metrics(points))
    with localcontext() as ctx:
        ctx.prec = 4
        actual = (rsi(series), sma(series, 5), annualized_volatility_pct(series, window=10), risk_metrics(points))

    assert actual == expected


def test_a_withdrawal_larger_than_the_days_value_is_rejected():
    # value 40 after "adding" 50 would mean the holdings were worth -10
    with pytest.raises(ValueError, match="net_flow"):
        risk_metrics(values((1, 100, 0), (2, 40, 50)))


@pytest.mark.parametrize("periods", [0, -1, 2.5])
def test_risk_metrics_reject_invalid_periods_per_year(periods):
    with pytest.raises(ValueError, match="periods_per_year"):
        risk_metrics(values((1, 100, 0), (2, 110, 0)), periods_per_year=periods)
