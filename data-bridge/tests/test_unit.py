import sys
import os
import pytest
import pandas as pd
import numpy as np
import datetime as dt
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

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
    # Inject NaN values to test serialization handling
    mock_data["High"][0] = np.nan
    mock_data["Volume"][5] = np.nan
    
    dates = pd.date_range(start="2026-07-02 09:00:00", periods=60, freq="5min", tz="UTC", name="Datetime")
    mock_df = pd.DataFrame(mock_data, index=dates)
    
    mock_ticker_instance = MagicMock()
    mock_ticker_instance.history.return_value = mock_df
    mock_yf_ticker.return_value = mock_ticker_instance
    
    res = main.get_price(interval="5m", period="1d")
    assert "bars" in res
    assert res["symbol"] == main.YF_SYMBOL
    assert len(res["bars"]) == 60
    
    # Assert NaN values got replaced with None
    assert res["bars"][0]["high"] is None
    assert res["bars"][5]["volume"] is None
    
    # Assert normal values remain floats (NOT converted to strings)
    assert res["bars"][0]["open"] == 1.0850
    assert isinstance(res["bars"][0]["open"], float)
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


def test_trade_model_validation():
    # Helper to construct valid base payload
    def make_valid_payload(**kwargs):
        payload = {
            "entry_time": "2026-07-02T10:00:00+03:00",
            "exit_time": "2026-07-02T10:30:00+03:00",
            "direction": "LONG",
            "entry": 1.0850,
            "sl": 1.0825,
            "tp": 1.0900,
            "exit_price": 1.0900,
            "result_pips": 50.0,
            "result_usd": 5.0,
            "risk_usd": 5.0,
            "planned_r": 2.0,
            "setup": "FVG",
            "rule_followed": True,
            "rule_break_notes": "",
            "notes": ""
        }
        payload.update(kwargs)
        return payload

    # 1. Valid LONG/BUY trade
    t_long = main.Trade(**make_valid_payload(direction="LONG", entry=1.0850, sl=1.0825, tp=1.0900))
    assert t_long.direction == "BUY"
    
    # 2. Valid SHORT/SELL trade
    t_short = main.Trade(**make_valid_payload(direction="SHORT", entry=1.0800, sl=1.0830, tp=1.0740, exit_price=1.0740))
    assert t_short.direction == "SELL"
    
    # 3. Invalid direction
    with pytest.raises(ValidationError):
        main.Trade(**make_valid_payload(direction="UP"))
        
    # 4. Negative values
    with pytest.raises(ValidationError):
        main.Trade(**make_valid_payload(entry=-1.0850))
        
    # 5. Invalid LONG SL (SL >= entry)
    with pytest.raises(ValidationError):
        main.Trade(**make_valid_payload(direction="LONG", entry=1.0850, sl=1.0860, tp=1.0900))
        
    # 6. Invalid LONG TP (TP <= entry)
    with pytest.raises(ValidationError):
        main.Trade(**make_valid_payload(direction="LONG", entry=1.0850, sl=1.0825, tp=1.0840))
        
    # 7. Invalid SHORT SL (SL <= entry)
    with pytest.raises(ValidationError):
        main.Trade(**make_valid_payload(direction="SHORT", entry=1.0800, sl=1.0790, tp=1.0740))
        
    # 8. Invalid SHORT TP (TP >= entry)
    with pytest.raises(ValidationError):
        main.Trade(**make_valid_payload(direction="SHORT", entry=1.0800, sl=1.0830, tp=1.0810))

    # 9. Invalid risk_usd (<= 0)
    with pytest.raises(ValidationError):
        main.Trade(**make_valid_payload(risk_usd=-5.0))
    with pytest.raises(ValidationError):
        main.Trade(**make_valid_payload(risk_usd=0.0))


def test_csv_sanitization():
    assert main._sanitize_csv_val("=1+1") == "'=1+1"
    assert main._sanitize_csv_val("+CMD") == "'+CMD"
    assert main._sanitize_csv_val("-SUM()") == "'-SUM()"
    assert main._sanitize_csv_val("@SUM()") == "'@SUM()"
    assert main._sanitize_csv_val("Normal text") == "Normal text"


def test_csv_migration_preserves_old_records(mock_trades_csv):
    # Write a legacy 9-column CSV file
    legacy_header = "timestamp,direction,entry,sl,tp,setup,result_pips,result_usd,notes\n"
    legacy_row = "2026-07-01T12:00:00,LONG,1.0800,1.0780,1.0840,Legacy Setup,40.0,4.0,Old Trade Note\n"
    with open(mock_trades_csv, "w", encoding="utf-8") as f:
        f.write(legacy_header)
        f.write(legacy_row)
        
    # Trigger _ensure_csv_file
    main._ensure_csv_file()
    
    # Verify backup exists and migrated CSV preserves legacy record under new FIELDNAMES schema
    backup_path = f"{mock_trades_csv}.bak"
    assert os.path.exists(backup_path)
    
    rows = main._load_trades()
    assert len(rows) == 1
    assert rows[0]["direction"] == "LONG"
    assert rows[0]["result_usd"] == "4.0"
    assert rows[0]["risk_usd"] == "5.0"


@patch("main.requests.get")
def test_forex_news_exception(mock_get):
    mock_get.side_effect = Exception("Connection Timeout")
    with patch("main.FINNHUB_KEY", "mock_key"):
        res = main.forex_news()
        assert len(res["headlines"]) == 0
        assert "error" in res
        assert "Failed to fetch news" in res["error"]


@patch("main.requests.get")
def test_economic_calendar_skips_malformed_date(mock_get):
    # Nairobi timezone (UTC+3)
    today_str = dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime("%Y-%m-%d")
    
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"title": "Valid Event", "country": "USD", "date": f"{today_str}T08:30:00-04:00", "impact": "High"},
        {"title": "Malformed Event", "country": "EUR", "date": "invalid-date-format", "impact": "Low"}
    ]
    mock_get.return_value = mock_response
    
    # Force mock_get to run (avoiding cache hits by patching os.path.exists to return False)
    with patch("main.os.path.exists", return_value=False):
        res = main.economic_calendar()
        assert res["date"] == today_str
        assert len(res["all_today"]) == 1
        assert res["all_today"][0]["event"] == "Valid Event"


def test_journal_stats_calculations():
    mock_trades = [
        # Win, rule followed, Monday, 10:00
        {
            "timestamp": "2026-07-13T10:00:00",
            "entry_time": "2026-07-13T10:00:00+03:00",
            "exit_time": "2026-07-13T10:30:00+03:00",
            "direction": "BUY",
            "entry": "1.0850",
            "sl": "1.0825",
            "tp": "1.0900",
            "exit_price": "1.0900",
            "result_pips": "50.0",
            "result_usd": "5.0",
            "risk_usd": "5.0",
            "r_multiple": "1.0",
            "planned_r": "2.0",
            "setup": "FVG",
            "rule_followed": "True",
            "rule_break_notes": "",
            "notes": ""
        },
        # Loss, rule broken, Monday, 15:00
        {
            "timestamp": "2026-07-13T15:00:00",
            "entry_time": "2026-07-13T15:00:00+03:00",
            "exit_time": "2026-07-13T15:15:00+03:00",
            "direction": "SELL",
            "entry": "1.0800",
            "sl": "1.0830",
            "tp": "1.0740",
            "exit_price": "1.0830",
            "result_pips": "-30.0",
            "result_usd": "-3.0",
            "risk_usd": "5.0",
            "r_multiple": "-0.6",
            "planned_r": "2.0",
            "setup": "Sweep",
            "rule_followed": "False",
            "rule_break_notes": "entered late",
            "notes": ""
        }
    ]
    with patch("main._load_trades", return_value=mock_trades):
        stats = main.journal_stats()
        assert stats["trades"] == 2
        assert stats["wins"] == 1
        assert stats["losses"] == 1
        assert stats["win_rate"] == 50.0
        assert stats["total_usd"] == 2.0
        assert stats["average_r"] == 0.2
        assert stats["rule_followed_trades"] == 1
        assert stats["rule_followed_usd"] == 5.0
        assert stats["rule_broken_trades"] == 1
        assert stats["rule_broken_usd"] == -3.0
        assert stats["discipline_cost_usd"] == 8.0
        assert "10:00" in stats["win_rate_by_hour_eat"]
        assert "15:00" in stats["win_rate_by_hour_eat"]
        assert "Monday" in stats["win_rate_by_weekday"]


def test_weekly_review_filtering():
    eat_tz = dt.timezone(dt.timedelta(hours=3))
    now = dt.datetime.now(eat_tz)
    
    mock_trades = [
        # Loss within 7 days
        {
            "exit_time": (now - dt.timedelta(days=2)).isoformat(),
            "result_usd": "-3.0"
        },
        # Loss older than 7 days
        {
            "exit_time": (now - dt.timedelta(days=10)).isoformat(),
            "result_usd": "-2.0"
        },
        # Win within 7 days (should be ignored since it's a win)
        {
            "exit_time": (now - dt.timedelta(days=1)).isoformat(),
            "result_usd": "5.0"
        }
    ]
    with patch("main._load_trades", return_value=mock_trades):
        review = main.weekly_review()
        assert review["count"] == 1
        assert review["losing_trades"][0]["result_usd"] == "-3.0"
