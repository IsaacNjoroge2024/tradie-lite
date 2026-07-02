import sys
import os
import pytest
import pandas as pd
import numpy as np
import datetime as dt
from unittest.mock import MagicMock, patch

# Ensure the parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main


def test_safe_float():
    assert main.safe_float("1.23") == 1.23
    assert main.safe_float(5.5) == 5.5
    assert main.safe_float("invalid") == 0.0
    assert main.safe_float(None) == 0.0


@patch("main.datetime")
def test_current_session(mock_datetime):
    # Nairobi timezone (UTC+3)
    eat_tz = dt.timezone(dt.timedelta(hours=3))
    
    # Test case 1: London Open (09:00 to 12:00 EAT)
    mock_datetime.now.return_value = dt.datetime(2026, 7, 2, 10, 30, tzinfo=eat_tz)
    res = main.current_session()
    assert res["kill_zone"] == "LONDON_OPEN"
    assert res["tradeable"] is True
    
    # Test case 2: NY Open (14:00 to 17:00 EAT)
    # Note: 14:00 is NY Open. 15:00-18:00 is overlap priority.
    mock_datetime.now.return_value = dt.datetime(2026, 7, 2, 14, 30, tzinfo=eat_tz)
    res = main.current_session()
    assert res["kill_zone"] == "NY_OPEN"
    assert res["tradeable"] is True
    
    # Test case 3: London/NY Overlap (15:00 to 18:00 EAT)
    mock_datetime.now.return_value = dt.datetime(2026, 7, 2, 15, 30, tzinfo=eat_tz)
    res = main.current_session()
    assert res["kill_zone"] == "OVERLAP_BEST"
    assert res["tradeable"] is True
    
    # Test case 4: Outside kill zone
    mock_datetime.now.return_value = dt.datetime(2026, 7, 2, 20, 30, tzinfo=eat_tz)
    res = main.current_session()
    assert res["kill_zone"] == "OUTSIDE_KILLZONE"
    assert res["tradeable"] is False


@patch("main.yf.Ticker")
def test_get_price(mock_yf_ticker):
    # Setup mock dataframe from yfinance
    mock_data = {
        "Open": [1.0850] * 60,
        "High": [1.0860] * 60,
        "Low": [1.0840] * 60,
        "Close": [1.0855] * 60,
        "Volume": [100] * 60
    }
    dates = pd.date_range(start="2026-07-02 09:00:00", periods=60, freq="5min", tz="UTC", name="Datetime")
    mock_df = pd.DataFrame(mock_data, index=dates)
    
    mock_ticker_instance = MagicMock()
    mock_ticker_instance.history.return_value = mock_df
    mock_yf_ticker.return_value = mock_ticker_instance
    
    res = main.get_price(interval="5m", period="1d")
    assert "bars" in res
    assert res["symbol"] == main.YF_SYMBOL
    assert len(res["bars"]) == 60
    assert res["bars"][0]["open"] == 1.0850
    assert "date" in res["bars"][0] or "datetime" in res["bars"][0]
    
    # Test empty dataframe case
    mock_ticker_instance.history.return_value = pd.DataFrame()
    res = main.get_price()
    assert "error" in res


@patch("main.requests.get")
def test_economic_calendar(mock_get):
    # Nairobi timezone (UTC+3)
    today_str = dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime("%Y-%m-%d")
    
    # Setup mock HTTP response for Forex Factory feed
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"title": "US NFP", "country": "USD", "date": f"{today_str}T08:30:00-04:00", "impact": "High"},
        {"title": "EU CPI", "country": "EUR", "date": f"{today_str}T03:00:00-04:00", "impact": "Low"},
        {"title": "Yesterday high news", "country": "USD", "date": "2026-07-01T12:00:00-04:00", "impact": "High"}
    ]
    mock_get.return_value = mock_response
    
    res = main.economic_calendar()
    assert res["date"] == today_str
    assert len(res["high_impact"]) == 1
    assert res["high_impact"][0]["event"] == "US NFP"
    assert len(res["all_today"]) == 2
        
    # Test exception case when no cache is available
    mock_get.side_effect = Exception("HTTP Timeout")
    with patch("main.os.path.exists", return_value=False):
        res = main.economic_calendar()
        assert "error" in res


@patch("main.requests.get")
def test_forex_news(mock_get):
    # Setup mock HTTP response
    mock_response = MagicMock()
    mock_response.json.return_value = [{"headline": f"Headline {i}"} for i in range(15)]
    mock_get.return_value = mock_response
    
    with patch("main.FINNHUB_KEY", "mock_key"):
        res = main.forex_news()
        assert len(res["headlines"]) == 10
        assert res["headlines"][0]["headline"] == "Headline 0"
        
    # Test missing key case
    with patch("main.FINNHUB_KEY", "your_finnhub_key_here"):
        res = main.forex_news()
        assert "warning" in res
        assert len(res["headlines"]) == 0
