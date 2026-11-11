"""Symbol normaliser, instrument universe and the canonical quote enrichment."""
import pytest

from quant.signals import enrich_quote
from quant.symbols import instrument_seed, normalize_symbol
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


def _legacy_enrich(data: dict, market_type: str, currency: str) -> dict:
    """Verbatim copy of workers._enrich_stock_data at commit de0575a (the oracle)."""
    price = data.get('price', 0)
    change_pct = data.get('change_pct', 0)

    rsi = data.get('rsi', 0)
    if not rsi or rsi == 0:
        rsi = 50 + (change_pct * 3)
        rsi = max(5, min(95, rsi))

    ma_20 = data.get('ma_20', 0)
    if not ma_20 or ma_20 == 0:
        ma_20 = price * (1 - change_pct / 200) if price else 0

    volatility = 'HIGH' if abs(change_pct) > 5 else 'MEDIUM' if abs(change_pct) > 2 else 'LOW'

    if change_pct > 5 and rsi < 70:
        prediction = f"PURCHASABLE — strong momentum +{change_pct:.1f}%"
    elif change_pct > 2 and rsi < 65:
        prediction = f"PURCHASABLE — positive trend +{change_pct:.1f}%"
    elif change_pct > 0.5 and rsi < 60:
        prediction = f"PURCHASABLE — rising +{change_pct:.1f}%"
    elif rsi < 35:
        prediction = "ACCUMULATE — oversold, potential bounce"
    elif change_pct >= 0 and rsi < 55:
        prediction = "ACCUMULATE — steady upward movement"
    elif change_pct >= 0 and rsi < 65:
        prediction = "WATCH TO BUY — conditions improving"
    elif rsi > 72 and change_pct > 3:
        prediction = f"TAKE PROFITS — up {change_pct:.1f}%, overbought"
    elif rsi > 65:
        prediction = "WATCH TO BUY — slightly overbought, wait for pullback"
    elif change_pct < -2:
        prediction = f"AVOID FOR NOW — declining {change_pct:.1f}%"
    elif change_pct < 0 and rsi > 40:
        prediction = "WATCH TO BUY — minor dip, monitor closely"
    elif change_pct < 0 and rsi < 40:
        prediction = "ACCUMULATE — dip into value zone"
    else:
        prediction = "WATCH TO BUY — neutral, awaiting direction"

    data.update({
        'currency': currency,
        'market_type': market_type,
        'rsi': round(rsi, 2),
        'ma_20': round(ma_20, 2) if ma_20 else 0,
        'volatility': volatility,
        'prediction': prediction,
        'reason': prediction,
        'is_favorable': change_pct > 0,
        'is_buyable': change_pct > 0.5 and rsi < 65,
    })
    return data


def _grid():
    changes = [x / 4 for x in range(-48, 49)]                 # -12% .. +12% in 0.25 steps
    supplied_rsi = [0, 20, 34.9, 35, 39.9, 40, 54.9, 55, 59.9, 60, 64.9, 65, 69.9, 70, 72, 72.1, 90]
    for change in changes:
        for supplied in supplied_rsi:
            yield {"symbol": "X", "price": 123.45, "change_pct": change, "rsi": supplied}
    yield {"symbol": "X", "price": 0, "change_pct": 0}
    yield {"symbol": "X", "price": 50.0, "change_pct": 1.0, "ma_20": 48.0}
    yield {"symbol": "X"}


def test_enrich_quote_reproduces_the_existing_worker_logic_exactly():
    for raw in _grid():
        expected = _legacy_enrich(dict(raw), "BIST", "TRY")

        assert enrich_quote(raw, "BIST", "TRY") == expected, raw


def test_enrich_quote_does_not_mutate_its_input():
    raw = {"symbol": "X", "price": 10.0, "change_pct": 1.0}

    enrich_quote(raw, "GLOBAL", "USD")

    assert raw == {"symbol": "X", "price": 10.0, "change_pct": 1.0}


@pytest.mark.parametrize("raw", ["ſAP", "ß", "ﬁ", "ııı=X", "FOO=BAR", "A=B=C", "AAPL=FX", "THYAO\n.IS"])
def test_lookalike_letters_and_open_ended_equals_symbols_are_rejected(raw):
    with pytest.raises(ValueError):
        normalize_symbol(raw)


def test_long_ledgers_replay_in_linear_time():
    import time
    from datetime import date
    from decimal import Decimal as D

    from quant.positions import realized_pnl
    from quant.types import CostBasisMethod, Transaction, TransactionType as T

    day = date(2026, 1, 2)
    buys = [Transaction(i, T.BUY, day, "TRY", D(1), D(10), symbol="X") for i in range(1, 20001)]
    sells = [Transaction(i, T.SELL, day, "TRY", D("0.5"), D(11), symbol="X") for i in range(20001, 40001)]

    started = time.perf_counter()
    realized = realized_pnl(buys + sells, CostBasisMethod.FIFO)

    assert len(realized) == 20000
    assert time.perf_counter() - started < 10     # 20k buys alone took ~4 s when lots were copied per row
