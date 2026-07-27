import sys
import os
import pytest
from fastapi.testclient import TestClient

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "tradie-lite-bridge"}


def test_session_endpoint(client):
    res = client.get("/session")
    assert res.status_code == 200
    data = res.json()
    assert "eat_time" in data
    assert "kill_zone" in data
    assert "tradeable" in data
    assert isinstance(data["tradeable"], bool)


def test_trade_logging_flow(client, mock_trades_csv):
    # 1. Verify stats are empty initially
    res = client.get("/journal-stats")
    assert res.status_code == 200
    assert res.json() == {"trades": 0, "wins": 0, "win_rate": 0.0, "total_usd": 0.0}
    
    # 2. Log a winning trade
    trade_win = {
        "entry_time": "2026-07-13T10:00:00+03:00",
        "exit_time": "2026-07-13T10:30:00+03:00",
        "direction": "LONG",
        "entry": 1.0850,
        "sl": 1.0825,
        "tp": 1.0900,
        "exit_price": 1.0900,
        "result_pips": 50.0,
        "result_usd": 10.0,
        "risk_usd": 5.0,
        "planned_r": 2.0,
        "setup": "FVG",
        "rule_followed": True,
        "rule_break_notes": "",
        "notes": "Winning trade"
    }
    res = client.post("/log-trade", json=trade_win)
    assert res.status_code == 200
    assert res.json() == {"logged": True, "r_multiple": 2.0}
    
    # Check stats after first trade
    res = client.get("/journal-stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["trades"] == 1
    assert stats["wins"] == 1
    assert stats["win_rate"] == 100.0
    assert stats["total_usd"] == 10.0
    assert stats["average_r"] == 2.0
    assert stats["rule_followed_trades"] == 1
    assert stats["rule_broken_trades"] == 0
    assert stats["discipline_cost_usd"] == 0.0
    
    # 3. Log a losing trade
    trade_loss = {
        "entry_time": "2026-07-13T15:00:00+03:00",
        "exit_time": "2026-07-13T15:15:00+03:00",
        "direction": "SHORT",
        "entry": 1.0800,
        "sl": 1.0830,
        "tp": 1.0740,
        "exit_price": 1.0830,
        "result_pips": -30.0,
        "result_usd": -5.0,
        "risk_usd": 5.0,
        "planned_r": 2.0,
        "setup": "Sweep High",
        "rule_followed": False,
        "rule_break_notes": "overleveraged",
        "notes": "Losing trade"
    }
    res = client.post("/log-trade", json=trade_loss)
    assert res.status_code == 200
    assert res.json() == {"logged": True, "r_multiple": -1.0}
    
    # Check stats after second trade
    res = client.get("/journal-stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["trades"] == 2
    assert stats["wins"] == 1
    assert stats["win_rate"] == 50.0
    assert stats["total_usd"] == 5.0
    assert stats["average_r"] == 0.5
    assert stats["rule_followed_trades"] == 1
    assert stats["rule_broken_trades"] == 1
    assert stats["discipline_cost_usd"] == 15.0
    assert "10:00" in stats["win_rate_by_hour_eat"]
    assert "15:00" in stats["win_rate_by_hour_eat"]
    assert "Monday" in stats["win_rate_by_weekday"]
    
    # 4. Verify CSV contents on disk
    assert os.path.exists(mock_trades_csv)
    with open(mock_trades_csv, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    assert len(lines) == 3  # Header + 2 trade lines
    assert "BUY" in lines[1]
    assert "SELL" in lines[2]
