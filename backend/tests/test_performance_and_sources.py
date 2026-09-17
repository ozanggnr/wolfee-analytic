from unittest.mock import patch, MagicMock
from backend.analysis import BIST_SYMBOLS, GLOBAL_SYMBOLS
from backend.data_sources.turkish_market import fetch_bist_stock, fetch_turkish_gold
from backend.data_sources.global_market import fetch_global_stock
from backend.ai_service import _generate_with_gemini, get_market_insight


def test_defunct_symbols_removed():
    delisted_bist = [
        "IPEKE.IS", "KOZAA.IS", "KOZAL.IS", "QNBFB.IS", "DENIZ.IS",
        "ADANA.IS", "BOLUC.IS", "SODA.IS", "MRTGG.IS", "METUR.IS", "KERVT.IS"
    ]
    for sym in delisted_bist:
        assert sym not in BIST_SYMBOLS, f"{sym} should have been removed from BIST_SYMBOLS"

    delisted_global = ["SQ", "BK", "SGEN", "EXAS", "EA", "LBRDK"]
    for sym in delisted_global:
        assert sym not in GLOBAL_SYMBOLS, f"{sym} should have been removed from GLOBAL_SYMBOLS"


def test_fetch_bist_stock_handles_fast_info_keyerror():
    with patch("backend.data_sources.turkish_market.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.fast_info.last_price = None
        mock_instance.history.return_value = MagicMock(empty=True)
        mock_ticker.return_value = mock_instance

        result = fetch_bist_stock("TEST.IS")
        assert result is None


def test_fetch_global_stock_handles_fast_info_keyerror():
    with patch("backend.data_sources.global_market.yf.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.fast_info.last_price = None
        mock_instance.history.return_value = MagicMock(empty=True)
        mock_ticker.return_value = mock_instance

        result = fetch_global_stock("TEST")
        assert result is None


def test_turkish_gold_parser_html_mock():
    mock_html = """
    <html>
    <body>
      <table>
        <tr><th>Sembol</th><th>Alis</th><th>Satis</th><th>Fark (%)</th></tr>
        <tr>
          <td><a href="/altin/gram-altin-fiyati/">ALTIN (TL/GR)</a></td>
          <td>6.834,17</td>
          <td>6.835,07</td>
          <td>%+2,48</td>
        </tr>
        <tr>
          <td><a href="/altin/ceyrek-altin-fiyati/">Ceyrek Altin</a></td>
          <td>11.063,00</td>
          <td>11.150,00</td>
          <td>%+1,98</td>
        </tr>
      </table>
    </body>
    </html>
    """
    with patch("backend.data_sources.turkish_market.httpx.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.text = mock_html
        mock_resp.raise_for_status = MagicMock()
        mock_client.return_value.__enter__.return_value.get.return_value = mock_resp

        results = fetch_turkish_gold()
        assert results is not None
        assert len(results) == 2
        assert results[0]["gold_type"] == "gram_altin"
        assert results[0]["buying_price"] == 6834.17
        assert results[0]["selling_price"] == 6835.07
        assert results[0]["change_pct"] == 2.48
        assert results[1]["gold_type"] == "ceyrek_altin"
        assert results[1]["buying_price"] == 11063.0


def test_gemini_fallback_when_unconfigured():
    with patch.dict("os.environ", {}, clear=True):
        res = _generate_with_gemini("test prompt")
        assert res is None

        insight = get_market_insight([{"symbol": "THYAO.IS", "change_pct": 2.5, "price": 310.0}])
        assert "Wolfee AI" in insight


def test_persistent_session_cookies_and_caching_headers():
    from starlette.testclient import TestClient
    from backend.main import app
    from backend.security_middleware import set_auth_cookies, SESSION_DURATION_DAYS
    from fastapi import Response

    # Verify set_auth_cookies produces persistent Lax cookie with 30-day max_age
    resp = Response()
    set_auth_cookies(resp, "test_session_id_12345678901234567890")
    cookie_header = resp.headers.get("set-cookie", "")
    assert "wolfee_session=test_session_id" in cookie_header
    assert "samesite=lax" in cookie_header.lower()
    assert f"max-age={60 * 60 * 24 * SESSION_DURATION_DAYS}" in cookie_header.lower()

    # Verify caching headers injected by SecurityMiddleware
    client = TestClient(app)
    static_res = client.get("/js/config.js")
    assert "Cache-Control" in static_res.headers
    assert "public" in static_res.headers["Cache-Control"]
    assert "max-age=86400" in static_res.headers["Cache-Control"]
