import os
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def mock_trades_csv(monkeypatch, tmp_path):
    # Route main.TRADES_CSV to a temporary file path
    temp_csv = tmp_path / "test_trades.csv"
    import main
    monkeypatch.setattr(main, "TRADES_CSV", str(temp_csv))
    return temp_csv

@pytest.fixture(autouse=True)
def mock_calendar_cache(monkeypatch, tmp_path):
    # Route main.CALENDAR_CACHE to a temporary file path to isolate tests
    temp_cache = tmp_path / "test_calendar_cache.json"
    import main
    monkeypatch.setattr(main, "CALENDAR_CACHE", str(temp_cache))
    return temp_cache

@pytest.fixture
def client():
    import main
    return TestClient(main.app)
