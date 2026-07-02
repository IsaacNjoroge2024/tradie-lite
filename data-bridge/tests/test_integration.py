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
        "direction": "LONG",
        "entry": 1.0850,
        "sl": 1.0825,
        "tp": 1.0900,
        "setup": "Kill Zone + FVG",
        "result_pips": 50.0,
        "result_usd": 5.00,
        "notes": "Winning LONG trade"
    }
    res = client.post("/log-trade", json=trade_win)
    assert res.status_code == 200
    assert res.json() == {"logged": True}
    
    # Check stats after first trade
    res = client.get("/journal-stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["trades"] == 1
    assert stats["wins"] == 1
    assert stats["win_rate"] == 100.0
    assert stats["total_usd"] == 5.00
    
    # 3. Log a losing trade
    trade_loss = {
        "direction": "SHORT",
        "entry": 1.0800,
        "sl": 1.0830,
        "tp": 1.0740,
        "setup": "Sweep High",
        "result_pips": -30.0,
        "result_usd": -3.00,
        "notes": "Losing SHORT trade"
    }
    res = client.post("/log-trade", json=trade_loss)
    assert res.status_code == 200
    assert res.json() == {"logged": True}
    
    # Check stats after second trade
    res = client.get("/journal-stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["trades"] == 2
    assert stats["wins"] == 1
    assert stats["win_rate"] == 50.0
    assert stats["total_usd"] == 2.00
    
    # 4. Verify CSV contents on disk
    assert os.path.exists(mock_trades_csv)
    with open(mock_trades_csv, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    assert len(lines) == 3  # Header + 2 trade lines
    assert "LONG" in lines[1]
    assert "SHORT" in lines[2]
