from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from common.errors import AppError
from marketdata.exchange_provider import ExchangeProvider


def test_ticker_cache_hits():
    # Mocking yfinance since we don't pass exchanges anymore
    with patch("yfinance.Ticker") as mock_ticker:
        mock_inst = MagicMock()
        mock_inst.history.return_value = pd.DataFrame(
            {"Open": [100.0], "High": [110.0], "Low": [90.0], "Close": [105.0], "Volume": [1000.0]}, index=[pd.Timestamp.now()]
        )
        mock_ticker.return_value = mock_inst

        provider = ExchangeProvider()
        ticker = provider.fetch_ticker("AAPL")
        assert ticker["last"] == 105.0

        # Second call should hit cache (mock_ticker called once)
        provider.fetch_ticker("AAPL")
        assert mock_ticker.call_count == 1


def test_fetch_ohlcv_formatting():
    with patch("yfinance.Ticker") as mock_ticker:
        mock_inst = MagicMock()
        mock_inst.history.return_value = pd.DataFrame(
            {"Open": [100.0], "High": [110.0], "Low": [90.0], "Close": [105.0], "Volume": [1000.0]}, index=[pd.Timestamp.now()]
        )
        mock_ticker.return_value = mock_inst

        provider = ExchangeProvider()
        ohlcv = provider.fetch_ohlcv("AAPL", timeframe="1h", limit=1)
        assert len(ohlcv) == 1
        assert len(ohlcv[0]) == 6  # [ts, o, h, l, c, v]
        assert ohlcv[0][4] == 105.0


def _frame_with_an_unfinished_bar():
    nan = float("nan")
    return pd.DataFrame(
        {"Open": [1.14, nan], "High": [1.142, nan], "Low": [1.138, nan], "Close": [1.1392, nan], "Volume": [0.0, 0.0]},
        index=[pd.Timestamp("2026-09-24"), pd.Timestamp("2026-09-25")],
    )


def test_a_bar_without_a_price_is_never_read_as_one():
    """Yahoo lists a session whose data is not final with NaN prices (seen for AAPL on Saturday 2026-09-26,
    UAT BE-32). The quote answered price NaN and the bars kept the row; both now skip it."""
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = _frame_with_an_unfinished_bar()
        provider = ExchangeProvider()
        assert provider.fetch_ticker("EURUSD")["last"] == 1.1392
        assert [bar[4] for bar in provider.fetch_ohlcv("EURUSD", timeframe="1d", limit=5)] == [1.1392]


def test_a_history_without_a_priced_bar_is_no_data():
    nan = float("nan")
    frame = pd.DataFrame({"Open": [nan], "High": [nan], "Low": [nan], "Close": [nan], "Volume": [0.0]}, index=[pd.Timestamp("2026-09-25")])
    with patch("yfinance.Ticker") as mock_ticker:
        mock_ticker.return_value.history.return_value = frame
        with pytest.raises(AppError) as err:
            ExchangeProvider().fetch_ticker("EURUSD")
    assert err.value.code == "data_not_found"
