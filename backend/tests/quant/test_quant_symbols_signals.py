"""Symbol normaliser, instrument universe and the canonical quote enrichment."""
import math
import statistics
from datetime import date, datetime, timedelta
from decimal import Decimal as D

import pytest

from quant.indicators import (
    INDICATOR_METHOD,
    annualized_volatility_pct,
    daily_indicators,
    rsi,
    sma,
)
from quant.signals import classify_volatility, enrich_quote, indicator_label, is_buyable, is_favorable
from quant.symbols import instrument_seed, normalize_symbol
from quant.types import DailyClose
from quant.universe import BIST_SYMBOLS, COMMODITIES_SYMBOLS, GLOBAL_SYMBOLS


@pytest.mark.parametrize(
    "raw, hint, expected",
    [
        ("THYAO.IS", None, ("THYAO", "BIST", "THYAO.IS", "TRY", "equity")),
        ("thyao", None, ("THYAO", "BIST", "THYAO.IS", "TRY", "equity")),
        (" Thyao.is ", None, ("THYAO", "BIST", "THYAO.IS", "TRY", "equity")),
        ("AAPL", None, ("AAPL", "US", "AAPL", "USD", "equity")),
        ("aapl", "US", ("AAPL", "US", "AAPL", "USD", "equity")),
        ("XYZQ", "US", ("XYZQ", "US", "XYZQ", "USD", "equity")),
        ("XYZQ", "GLOBAL", ("XYZQ", "US", "XYZQ", "USD", "equity")),
        ("XYZQ", None, ("XYZQ", "BIST", "XYZQ.IS", "TRY", "equity")),
        ("XYZQ", "BIST100", ("XYZQ", "BIST", "XYZQ.IS", "TRY", "equity")),
        ("GC=F", None, ("GC=F", "CMDTY", "GC=F", "USD", "commodity")),
        ("gc=f", "COMMODITY", ("GC=F", "CMDTY", "GC=F", "USD", "commodity")),
        ("USDTRY=X", None, ("USDTRY=X", "FX", "USDTRY=X", "TRY", "fx")),
        ("BRK-B", "US", ("BRK-B", "US", "BRK-B", "USD", "equity")),
    ],
)
def test_normalize_symbol(raw, hint, expected):
    result = normalize_symbol(raw, hint)

    assert (result.symbol, result.exchange, result.provider_symbol,
            result.currency, result.asset_class) == expected


def test_both_spellings_of_a_bist_symbol_resolve_to_one_identity():
    assert normalize_symbol("THYAO") == normalize_symbol("THYAO.IS") == normalize_symbol("thyao.is", "BIST")


def test_explicit_suffix_wins_over_a_conflicting_hint():
    assert normalize_symbol("THYAO.IS", "US").exchange == "BIST"


@pytest.mark.parametrize("raw", ["", "   ", "THY AO", "../etc", "A" * 21, "THYAO;DROP", ".IS", "=F", None, 42])
def test_invalid_symbols_are_rejected(raw):
    with pytest.raises(ValueError):
        normalize_symbol(raw)


def test_unknown_market_hint_is_rejected():
    with pytest.raises(ValueError, match="market_hint"):
        normalize_symbol("THYAO", "NASDAQ")


def test_no_bist_symbol_collides_with_a_global_symbol():
    bist_stems = {s[:-3] for s in BIST_SYMBOLS}

    assert bist_stems.isdisjoint(GLOBAL_SYMBOLS)


def test_instrument_seed_covers_the_whole_universe_once():
    seed = instrument_seed()
    keys = [(i.symbol, i.exchange) for i in seed]

    assert len(keys) == len(set(keys))
    assert len(seed) == len(BIST_SYMBOLS) + len(GLOBAL_SYMBOLS) + len(COMMODITIES_SYMBOLS)
    by_key = {(i.symbol, i.exchange): i for i in seed}
    assert by_key[("THYAO", "BIST")].provider_symbol == "THYAO.IS"
    assert by_key[("GC=F", "CMDTY")].name == "Gold (USD)"


def test_analysis_module_still_exports_the_same_universe_objects():
    pytest.importorskip("pandas")
    import analysis

    assert analysis.BIST_SYMBOLS is BIST_SYMBOLS
    assert analysis.GLOBAL_SYMBOLS is GLOBAL_SYMBOLS
    assert analysis.COMMODITIES_SYMBOLS is COMMODITIES_SYMBOLS


@pytest.mark.parametrize("raw", ["ſAP", "ß", "ﬁ", "ııı=X", "FOO=BAR", "A=B=C", "AAPL=FX", "THYAO\n.IS"])
def test_lookalike_letters_and_open_ended_equals_symbols_are_rejected(raw):
    with pytest.raises(ValueError):
        normalize_symbol(raw)


def test_long_ledgers_replay_in_linear_time():
    import time

    from quant.positions import realized_pnl
    from quant.types import CostBasisMethod, Transaction, TransactionType as T

    day = date(2026, 1, 2)
    buys = [Transaction(i, T.BUY, day, "TRY", D(1), D(10), symbol="X") for i in range(1, 20001)]
    sells = [Transaction(i, T.SELL, day, "TRY", D("0.5"), D(11), symbol="X") for i in range(20001, 40001)]

    started = time.perf_counter()
    realized = realized_pnl(buys + sells, CostBasisMethod.FIFO)

    assert len(realized) == 20000
    assert time.perf_counter() - started < 10     # 20k buys alone took ~4 s when lots were copied per row


# ------------------------------------------------ indicators from history (D4)

START = date(2026, 1, 1)


def history(closes):
    return [DailyClose(START + timedelta(days=i), D(str(close))) for i, close in enumerate(closes)]


RISING = history(range(100, 121))                              # 21 closes: 100, 101, ... 120
ALTERNATING_15 = history([100, 110] * 7 + [100])               # 14 moves: 7 x +10, 7 x -10
NULL_FIELDS = ("rsi", "ma_20", "volatility", "volatility_pct", "prediction", "reason",
               "is_favorable", "is_buyable", "indicators_as_of", "indicator_method")


@pytest.mark.parametrize("no_history", [None, [], ()])
def test_no_history_gives_no_indicators(no_history):
    result = daily_indicators(no_history)

    assert (result.as_of, result.observations) == (None, 0)
    assert (result.rsi_14, result.sma_20, result.volatility_pct) == (None, None, None)


def test_known_closes_give_known_indicators():
    result = daily_indicators(RISING)
    closes = [point.close for point in RISING]
    returns = [(101 + i) / (100 + i) - 1 for i in range(20)]

    assert result.as_of == date(2026, 1, 21)
    assert result.observations == 21
    assert result.rsi_14 == D("100")                           # no losing day at all
    assert result.sma_20 == D("110.5")                         # mean of 101..120
    assert float(result.volatility_pct) == pytest.approx(statistics.stdev(returns) * math.sqrt(252) * 100)
    # The same primitives, the same windows.
    assert result.rsi_14 == rsi(closes, 14)
    assert result.sma_20 == sma(closes, 20)
    assert result.volatility_pct == annualized_volatility_pct(closes, 20)


def test_each_indicator_is_none_until_its_window_is_filled():
    fifteen = daily_indicators(ALTERNATING_15)
    fourteen = daily_indicators(ALTERNATING_15[:14])
    twenty = daily_indicators(RISING[:20])

    # 7 gains of 10 and 7 losses of 10: average gain equals average loss, so RSI is exactly 50.
    assert fifteen.rsi_14 == D("50")
    assert (fifteen.sma_20, fifteen.volatility_pct) == (None, None)
    assert fourteen.rsi_14 is None
    assert twenty.sma_20 == D("109.5")                         # mean of 100..119
    assert twenty.volatility_pct is None


def test_history_order_does_not_matter_but_dates_must_be_unique_calendar_dates():
    assert daily_indicators(list(reversed(RISING))) == daily_indicators(RISING)
    with pytest.raises(ValueError, match="same date"):
        daily_indicators(RISING + [DailyClose(START, D("99"))])
    with pytest.raises(ValueError, match="calendar dates"):
        daily_indicators([DailyClose(datetime(2026, 1, 1, 12, 0), D("99"))])
    with pytest.raises(ValueError, match="Decimal"):
        daily_indicators([DailyClose(START, 99.5)])
    with pytest.raises(ValueError, match="positive"):
        daily_indicators([DailyClose(START, D("0"))])


# --------------------------------------------------------- enrich_quote (D4)

def test_without_history_nothing_is_estimated():
    raw = {"symbol": "X", "price": 123.45, "change_pct": 6.0, "day_high": 0, "day_low": 0}

    result = enrich_quote(raw, "BIST", "TRY")

    assert {field: result[field] for field in NULL_FIELDS} == dict.fromkeys(NULL_FIELDS)
    assert (result["day_high"], result["day_low"]) == (None, None)
    assert (result["price"], result["change_pct"]) == (123.45, 6.0)
    assert (result["currency"], result["market_type"]) == ("TRY", "BIST")


def test_old_estimates_already_in_the_data_are_not_passed_through():
    raw = {"symbol": "X", "price": 100.0, "change_pct": 1.0, "rsi": 53.0, "ma_20": 99.5,
           "volatility": "LOW", "prediction": "PURCHASABLE — rising +1.0%", "is_buyable": True}

    result = enrich_quote(raw, "GLOBAL", "USD")

    assert {field: result[field] for field in NULL_FIELDS} == dict.fromkeys(NULL_FIELDS)


def test_with_history_indicators_and_labels_are_real():
    raw = {"symbol": "X", "price": 120.0, "change_pct": 4.0, "day_high": 121.0, "day_low": 118.5}

    result = enrich_quote(raw, "GLOBAL", "USD", RISING)

    assert result["rsi"] == 100.0
    assert result["ma_20"] == 110.5
    assert result["volatility_pct"] == 0.79                    # 0.788, checked against statistics.stdev above
    assert result["volatility"] == "LOW"
    assert result["prediction"] == result["reason"] == "RSI above 70 (overbought)"
    assert (result["is_favorable"], result["is_buyable"]) == (True, False)
    assert (result["day_high"], result["day_low"]) == (121.0, 118.5)
    assert result["indicators_as_of"] == "2026-01-21"
    assert result["indicator_method"] == INDICATOR_METHOD


def test_short_history_gives_only_what_it_supports():
    raw = {"symbol": "X", "price": 100.0, "change_pct": 0.2}

    result = enrich_quote(raw, "BIST", "TRY", ALTERNATING_15)

    assert result["rsi"] == 50.0
    assert (result["ma_20"], result["volatility"], result["volatility_pct"]) == (None, None, None)
    assert result["prediction"] == "RSI between 30 and 70"         # 15 closes: no 20-day average yet
    assert (result["is_favorable"], result["is_buyable"]) == (True, False)
    assert result["indicators_as_of"] == "2026-01-15"


def test_history_too_short_for_rsi_gives_no_labels():
    result = enrich_quote({"symbol": "X", "change_pct": 3.0}, "BIST", "TRY", ALTERNATING_15[:10])

    assert {field: result[field] for field in NULL_FIELDS} == dict.fromkeys(NULL_FIELDS)


def test_the_two_flags_need_the_days_change_too():
    result = enrich_quote({"symbol": "X", "price": 100.0}, "BIST", "TRY", RISING)

    assert result["rsi"] == 100.0
    assert result["prediction"] == "RSI above 70 (overbought)"     # describes the RSI alone
    assert (result["is_favorable"], result["is_buyable"]) == (None, None)


def test_enrich_quote_does_not_mutate_its_input():
    raw = {"symbol": "X", "price": 10.0, "change_pct": 1.0}

    enrich_quote(raw, "GLOBAL", "USD", RISING)

    assert raw == {"symbol": "X", "price": 10.0, "change_pct": 1.0}


@pytest.mark.parametrize(
    "rsi_value, price, ma_20, expected",
    [
        (29.99, 100.0, 100.0, "RSI below 30 (oversold)"),       # the RSI band wins over the average
        (70.01, 100.0, 100.0, "RSI above 70 (overbought)"),
        (30.0, None, None, "RSI between 30 and 70"),            # 30 and 70 themselves are inside the band
        (70.0, None, None, "RSI between 30 and 70"),
        (50.0, 100.0, None, "RSI between 30 and 70"),           # no 20-day average yet
        (50.0, 100.0, 100.0, "Near 20-day average"),
        (50.0, 102.0, 100.0, "Near 20-day average"),            # 2 % away is still near
        (50.0, 98.0, 100.0, "Near 20-day average"),
        (50.0, 103.0, 100.0, "Above 20-day average"),
        (50.0, 97.0, 100.0, "Below 20-day average"),
    ],
)
def test_labels_describe_the_indicators(rsi_value, price, ma_20, expected):
    assert indicator_label(rsi_value, price, ma_20) == expected


def test_no_label_tells_the_reader_what_to_do():
    labels = {indicator_label(r, p, 100.0) for r in (10.0, 50.0, 90.0) for p in (None, 90.0, 100.0, 110.0)}

    assert len(labels) == 6
    for label in labels:
        for word in ("BUY", "PURCHAS", "ACCUMULATE", "PROFIT", "AVOID", "WATCH", "HOLD", "SELL", "WAIT"):
            assert word not in label.upper()


def test_labels_are_none_without_their_inputs():
    assert indicator_label(None) is None and indicator_label(None, 100.0, 100.0) is None
    assert is_buyable(3.0, None) is None and is_favorable(3.0, None) is None
    assert (is_buyable(3.0, 50.0), is_buyable(3.0, 70.0), is_buyable(0.4, 50.0)) == (True, False, False)
    assert (is_favorable(0.1, 50.0), is_favorable(-0.1, 50.0)) == (True, False)


def test_volatility_label_comes_from_annualised_volatility():
    assert [classify_volatility(v) for v in (None, 0.79, 24.99, 25, 49.99, 50, 120)] == [
        None, "LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH",
    ]


# ------------------------------------------------ daily change (data_sources.provided)

def test_daily_change_is_none_without_a_previous_close():
    from data_sources.provided import daily_change_pct

    # (320.25 - 310) / 310 = 3.306...% -> 3.31
    assert daily_change_pct(320.25, 310.0) == 3.31
    assert daily_change_pct(310.0, 310.0) == 0.0               # a real "unchanged" stays 0.0
    for previous_close in (None, 0, 0.0, -1.0, float("nan")):
        assert daily_change_pct(320.25, previous_close) is None
    assert daily_change_pct(None, 310.0) is None
