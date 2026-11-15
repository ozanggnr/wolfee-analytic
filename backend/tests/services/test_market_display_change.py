"""REQ-31 (d): a null change_pct (no previous close) stays null on the card and is
"Not available" in the export, never 0.0 %; the card no longer sends estimated_fields.
"""
import os
import sys
from types import SimpleNamespace

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services.market_display import NOT_AVAILABLE, portfolio_export_row, stock_card  # noqa: E402

ROW = dict(symbol="THYAO", name="THYAO", price=320.25, change_pct=None, volume=1e6, day_high=None, day_low=None,
           open_price=None, previous_close=None, bid=0, ask=0, rsi=None, ma_20=None, volatility=None,
           currency="TRY", market_type="BIST", prediction=None, reason=None, is_favorable=None, is_buyable=None,
           market_cap=0, extra_data={})


def test_the_card_keeps_a_null_change_null_and_has_no_estimated_fields():
    card = stock_card(SimpleNamespace(**ROW))

    assert card["change_pct"] is None  # was 0
    assert "estimated_fields" not in card


def test_the_card_keeps_a_real_change():
    assert stock_card(SimpleNamespace(**{**ROW, "change_pct": -1.25}))["change_pct"] == -1.25


def test_the_export_shows_an_unknown_change_as_not_available():
    row = portfolio_export_row({"symbol": "THYAO", "price": 320.25, "change_pct": None}, "daily", "2026-11-15")

    assert (row["Change %"], row["Change Amt"], row["Start Price"], row["Trend"]) == (NOT_AVAILABLE,) * 4
    assert row["Current Price"] == 320.25


def test_the_export_uses_the_provider_previous_close_as_start_price():
    row = portfolio_export_row({"symbol": "THYAO", "price": 320.25, "change_pct": None, "previous_close": 319.25},
                               "daily", "2026-11-15")

    assert row["Start Price"] == 319.25 and row["Change %"] == NOT_AVAILABLE


def test_the_export_keeps_a_real_change():
    row = portfolio_export_row({"symbol": "THYAO", "price": 200.0, "change_pct": 2.5}, "daily", "2026-11-15")

    assert (row["Change %"], row["Change Amt"], row["Start Price"]) == (2.5, 5.0, 195.0)
    assert row["Trend"].startswith("📈 UP")
