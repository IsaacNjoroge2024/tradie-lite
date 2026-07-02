import os
import csv
import json
import time
import requests
import yfinance as yf
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Tradie Lite Data Bridge")

FINNHUB_KEY = os.getenv("FINNHUB_API_KEY")
YF_SYMBOL = os.getenv("YF_SYMBOL", "EURUSD=X")
TRADES_CSV = os.path.join(os.path.dirname(__file__), "trades.csv")


@app.get("/health")
def health():
    return {"status": "ok", "service": "tradie-lite-bridge"}


@app.get("/price")
def get_price(interval: str = "5m", period: str = "1d"):
    """OHLCV bars. interval: 1m,5m,15m,1h. period: 1d,5d."""
    df = yf.Ticker(YF_SYMBOL).history(period=period, interval=interval)
    if df.empty:
        return {"error": "no data", "symbol": YF_SYMBOL}
    
    df = df.tail(60).reset_index()
    df.columns = [str(c).lower() for c in df.columns]
    
    # Convert datetime and any other non-serializable objects to string to guarantee serializability
    for col in df.columns:
        if df[col].dtype == 'object' or 'datetime' in str(df[col].dtype):
            df[col] = df[col].astype(str)
            
    return {"symbol": YF_SYMBOL, "interval": interval,
            "bars": df.to_dict(orient="records")}


CALENDAR_CACHE = os.path.join(os.path.dirname(__file__), "calendar_cache.json")
CACHE_DURATION = 3600  # 1 hour cache duration


@app.get("/calendar")
def economic_calendar():
    """Today's economic events from Forex Factory (free feed with caching)."""
    eat_tz = timezone(timedelta(hours=3))
    today_eat = datetime.now(eat_tz)
    today_str = today_eat.strftime("%Y-%m-%d")
    
    data = None
    
    # Attempt to read from local cache if it is fresh
    if os.path.exists(CALENDAR_CACHE):
        mtime = os.path.getmtime(CALENDAR_CACHE)
        if time.time() - mtime < CACHE_DURATION:
            try:
                with open(CALENDAR_CACHE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
                
    # Fetch fresh data if cache is missing or expired
    if not data:
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            
            # Update local cache file
            with open(CALENDAR_CACHE, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            # Fallback to stale cache if web request fails
            if os.path.exists(CALENDAR_CACHE):
                try:
                    with open(CALENDAR_CACHE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    pass
            if not data:
                return {
                    "date": today_str,
                    "high_impact": [],
                    "all_today": [],
                    "error": f"Failed to fetch calendar and no cache available: {str(e)}"
                }
                
    todays = []
    high = []
    
    for e in data:
        date_str = e.get("date")
        if not date_str:
            continue
        event_dt = datetime.fromisoformat(date_str)
        event_eat = event_dt.astimezone(eat_tz)
        
        if event_eat.strftime("%Y-%m-%d") == today_str:
            event_mapped = {
                "event": e.get("title"),
                "time": event_eat.strftime("%Y-%m-%d %H:%M EAT"),
                "impact": e.get("impact"),
                "country": e.get("country")
            }
            todays.append(event_mapped)
            if e.get("impact") == "High":
                high.append(event_mapped)
                
    return {"date": today_str, "high_impact": high, "all_today": todays}


@app.get("/news")
def forex_news():
    if not FINNHUB_KEY or FINNHUB_KEY == "your_finnhub_key_here":
        return {
            "headlines": [], 
            "warning": "Finnhub API key not configured"
        }
        
    try:
        url = f"https://finnhub.io/api/v1/news?category=forex&token={FINNHUB_KEY}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return {"headlines": r.json()[:10]}
    except Exception as e:
        return {"headlines": [], "error": str(e)}


@app.get("/session")
def current_session():
    """Which kill zone are we in right now (EAT)?"""
    # UTC+3 timezone for Nairobi (EAT)
    eat_tz = timezone(timedelta(hours=3))
    now = datetime.now(eat_tz)
    hour = now.hour
    
    if 9 <= hour < 12:
        zone = "LONDON_OPEN"
    elif 15 <= hour < 18:
        zone = "OVERLAP_BEST"
    elif 14 <= hour < 17:
        zone = "NY_OPEN"
    else:
        zone = "OUTSIDE_KILLZONE"
        
    return {"eat_time": now.strftime("%H:%M"), "kill_zone": zone,
            "tradeable": zone != "OUTSIDE_KILLZONE"}


class Trade(BaseModel):
    direction: str
    entry: float
    sl: float
    tp: float
    setup: str
    result_pips: float = 0.0
    result_usd: float = 0.0
    notes: str = ""


@app.post("/log-trade")
def log_trade(t: Trade):
    """Append a trade to the journal CSV."""
    new = not os.path.exists(TRADES_CSV)
    eat_tz = timezone(timedelta(hours=3))
    with open(TRADES_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "direction", "entry", "sl", "tp",
                        "setup", "result_pips", "result_usd", "notes"])
        w.writerow([datetime.now(eat_tz).isoformat(), t.direction, t.entry, t.sl,
                    t.tp, t.setup, t.result_pips, t.result_usd, t.notes])
    return {"logged": True}


def safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


@app.get("/journal-stats")
def journal_stats():
    """Quick P&L summary from the journal."""
    if not os.path.exists(TRADES_CSV):
        return {"trades": 0, "wins": 0, "win_rate": 0.0, "total_usd": 0.0}
        
    with open(TRADES_CSV, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        
    if not rows:
        return {"trades": 0, "wins": 0, "win_rate": 0.0, "total_usd": 0.0}
        
    wins = [r for r in rows if safe_float(r.get("result_usd")) > 0]
    total_usd = sum(safe_float(r.get("result_usd")) for r in rows)
    
    return {"trades": len(rows), "wins": len(wins),
            "win_rate": round(len(wins) / len(rows) * 100, 1),
            "total_usd": round(total_usd, 2)}
