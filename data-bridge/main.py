import os
import csv
import json
import time
import logging
import statistics
import threading
from collections import defaultdict
import requests
import yfinance as yf
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from pydantic import BaseModel, field_validator, model_validator
from dotenv import load_dotenv

load_dotenv()

# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("tradie-lite-bridge")

app = FastAPI(title="Tradie Lite Data Bridge")

FINNHUB_KEY = os.getenv("FINNHUB_API_KEY")
YF_SYMBOL = os.getenv("YF_SYMBOL", "EURUSD=X")
TRADES_CSV = os.path.join(os.path.dirname(__file__), "trades.csv")

csv_lock = threading.Lock()


def _sanitize_csv_val(val: str) -> str:
    if isinstance(val, str) and val.startswith(("=", "+", "-", "@")):
        return "'" + val
    return val


@app.get("/health")
def health():
    return {"status": "ok", "service": "tradie-lite-bridge"}


@app.get("/price")
def get_price(interval: str = "5m", period: str = "1d"):
    """OHLCV bars. interval: 1m,5m,15m,1h. period: 1d,5d."""
    try:
        df = yf.Ticker(YF_SYMBOL).history(period=period, interval=interval)
    except Exception as e:
        logger.error(f"Error fetching yfinance history for {YF_SYMBOL}: {str(e)}")
        return {"error": f"Failed to fetch market data: {type(e).__name__}", "symbol": YF_SYMBOL}
        
    if df.empty:
        return {"error": "no data", "symbol": YF_SYMBOL}
    
    df = df.tail(60).reset_index()
    df.columns = [str(c).lower() for c in df.columns]
    
    # Convert datetime and any other non-serializable objects to string to guarantee serializability
    for col in df.columns:
        if df[col].dtype == 'object' or 'datetime' in str(df[col].dtype):
            df[col] = df[col].astype(str)
            
    # Replace NaN with None so they serialize to null in JSON instead of raising ValueError
    df = df.astype(object).where(df.notnull(), None)
            
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
            except Exception as ex:
                logger.warning(f"Failed to read fresh calendar cache: {str(ex)}")
                
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
            logger.warning(f"Failed to fetch fresh calendar, attempting stale cache fallback: {str(e)}")
            # Fallback to stale cache if web request fails
            if os.path.exists(CALENDAR_CACHE):
                try:
                    with open(CALENDAR_CACHE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as ex:
                    logger.warning(f"Failed to read stale calendar cache: {str(ex)}")
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
        try:
            event_dt = datetime.fromisoformat(date_str)
            event_eat = event_dt.astimezone(eat_tz)
        except (ValueError, TypeError) as ex:
            logger.warning(f"Skipping malformed calendar event date '{date_str}': {str(ex)}")
            continue
        
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
        url = "https://finnhub.io/api/v1/news?category=forex"
        headers = {"X-Finnhub-Token": FINNHUB_KEY}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return {"headlines": r.json()[:10]}
    except Exception as e:
        logger.error(f"Error fetching Finnhub news: {str(e)}")
        return {"headlines": [], "error": f"Failed to fetch news: {type(e).__name__}"}


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


FIELDNAMES = [
    "timestamp", "entry_time", "exit_time", "direction", "entry", "sl", "tp",
    "exit_price", "result_pips", "result_usd", "risk_usd", "r_multiple",
    "planned_r", "setup", "rule_followed", "rule_break_notes", "notes",
]


class Trade(BaseModel):
    entry_time: str
    exit_time: str
    direction: str
    entry: float
    sl: float
    tp: float
    exit_price: float
    result_pips: float
    result_usd: float
    risk_usd: float = 5.0
    planned_r: float = 2.0
    setup: str
    rule_followed: bool
    rule_break_notes: str = ""
    notes: str = ""

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        d = v.upper().strip()
        if d in ("LONG", "BUY"):
            return "BUY"
        elif d in ("SHORT", "SELL"):
            return "SELL"
        raise ValueError("direction must be 'BUY', 'SELL', 'LONG', or 'SHORT'")

    @field_validator("entry", "sl", "tp", "exit_price", "risk_usd")
    @classmethod
    def validate_positive(cls, v: float) -> float:
        if v <= 0.0:
            raise ValueError("Value must be strictly positive")
        return v

    @model_validator(mode="after")
    def validate_trade_relationships(self) -> 'Trade':
        direction = self.direction.upper().strip()
        if direction in ("LONG", "BUY"):
            if self.sl >= self.entry:
                raise ValueError("For BUY/LONG trade, Stop Loss must be less than Entry price")
            if self.tp <= self.entry:
                raise ValueError("For BUY/LONG trade, Take Profit must be greater than Entry price")
        elif direction in ("SHORT", "SELL"):
            if self.sl <= self.entry:
                raise ValueError("For SELL/SHORT trade, Stop Loss must be greater than Entry price")
            if self.tp >= self.entry:
                raise ValueError("For SELL/SHORT trade, Take Profit must be less than Entry price")
        return self


@app.post("/log-trade")
def log_trade(t: Trade):
    """Append a fully detailed trade to the journal CSV. r_multiple is
    computed automatically from result_usd / risk_usd — this is the
    realized R, compared against planned_r (normally 2.0) to see if
    execution matched the plan."""
    r_multiple = round(t.result_usd / t.risk_usd, 2) if t.risk_usd else 0.0
    eat_tz = timezone(timedelta(hours=3))

    with csv_lock:
        new_file = not os.path.exists(TRADES_CSV)
        header_matches = False
        if not new_file:
            try:
                with open(TRADES_CSV, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line == ",".join(FIELDNAMES):
                        header_matches = True
            except Exception as ex:
                logger.warning(f"Could not read existing CSV header: {ex}")

        if new_file or not header_matches:
            with open(TRADES_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=FIELDNAMES)
                w.writeheader()

        with open(TRADES_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES)
            w.writerow({
                "timestamp": datetime.now(eat_tz).isoformat(),
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "direction": t.direction,
                "entry": t.entry,
                "sl": t.sl,
                "tp": t.tp,
                "exit_price": t.exit_price,
                "result_pips": t.result_pips,
                "result_usd": t.result_usd,
                "risk_usd": t.risk_usd,
                "r_multiple": r_multiple,
                "planned_r": t.planned_r,
                "setup": _sanitize_csv_val(t.setup),
                "rule_followed": t.rule_followed,
                "rule_break_notes": _sanitize_csv_val(t.rule_break_notes),
                "notes": _sanitize_csv_val(t.notes),
            })
    return {"logged": True, "r_multiple": r_multiple}


def safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _load_trades():
    with csv_lock:
        if not os.path.exists(TRADES_CSV):
            return []
        with open(TRADES_CSV, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))


@app.get("/journal-stats")
def journal_stats():
    """Full journal analytics: win rate, average R (expected value),
    rule-break P&L split, win rate by hour of day, win rate by weekday."""
    rows = _load_trades()
    if not rows:
        return {"trades": 0, "wins": 0, "win_rate": 0.0, "total_usd": 0.0}

    total = len(rows)
    wins = [r for r in rows if safe_float(r.get("result_usd")) > 0]
    losses = [r for r in rows if safe_float(r.get("result_usd")) <= 0]
    r_values = [safe_float(r.get("r_multiple")) for r in rows]
    total_usd = sum(safe_float(r.get("result_usd")) for r in rows)

    # Expected value (average R)
    average_r = round(statistics.mean(r_values), 2) if r_values else 0.0

    # Rule-break P&L split — isolates the cost of indiscipline
    followed = [r for r in rows if r.get("rule_followed") in ("True", "true", True)]
    broken = [r for r in rows if r.get("rule_followed") in ("False", "false", False)]
    followed_usd = round(sum(safe_float(r.get("result_usd")) for r in followed), 2)
    broken_usd = round(sum(safe_float(r.get("result_usd")) for r in broken), 2)

    # Win rate by hour of day (EAT), from entry_time
    by_hour = defaultdict(lambda: {"trades": 0, "wins": 0})
    by_weekday = defaultdict(lambda: {"trades": 0, "wins": 0})
    eat_tz = timezone(timedelta(hours=3))

    for r in rows:
        entry_time_str = r.get("entry_time")
        if not entry_time_str:
            continue
        try:
            dt = datetime.fromisoformat(entry_time_str)
            if dt.tzinfo is not None:
                dt = dt.astimezone(eat_tz)
        except (ValueError, KeyError, TypeError):
            continue
        hour_key = f"{dt.hour:02d}:00"
        weekday_key = dt.strftime("%A")
        won = safe_float(r.get("result_usd")) > 0
        by_hour[hour_key]["trades"] += 1
        by_hour[hour_key]["wins"] += 1 if won else 0
        by_weekday[weekday_key]["trades"] += 1
        by_weekday[weekday_key]["wins"] += 1 if won else 0

    win_rate_by_hour = {
        h: {"trades": v["trades"], "wins": v["wins"],
            "win_rate": round(v["wins"] / v["trades"] * 100, 1)}
        for h, v in sorted(by_hour.items())
    }
    win_rate_by_weekday = {
        d: {"trades": v["trades"], "wins": v["wins"],
            "win_rate": round(v["wins"] / v["trades"] * 100, 1)}
        for d, v in by_weekday.items()
    }

    return {
        "trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / total * 100, 1),
        "total_usd": round(total_usd, 2),
        "average_r": average_r,
        "planned_r_target": safe_float(rows[0].get("planned_r")) if rows else 2.0,
        "rule_followed_trades": len(followed),
        "rule_followed_usd": followed_usd,
        "rule_broken_trades": len(broken),
        "rule_broken_usd": broken_usd,
        "discipline_cost_usd": round(followed_usd - broken_usd if broken else 0.0, 2),
        "win_rate_by_hour_eat": win_rate_by_hour,
        "win_rate_by_weekday": win_rate_by_weekday,
    }


@app.get("/weekly-review")
def weekly_review():
    """Losing trades from the last 7 days — the raw material for the
    Sunday review habit. Returns them with rule-break flags so you can
    see at a glance whether losses came from bad setups or broken rules."""
    rows = _load_trades()
    eat_tz = timezone(timedelta(hours=3))
    cutoff = datetime.now(eat_tz) - timedelta(days=7)
    recent_losses = []
    for r in rows:
        exit_time_str = r.get("exit_time")
        if not exit_time_str:
            continue
        try:
            exit_dt = datetime.fromisoformat(exit_time_str)
            if exit_dt.tzinfo is None:
                exit_dt = exit_dt.replace(tzinfo=eat_tz)
        except (ValueError, KeyError, TypeError):
            continue
        if exit_dt >= cutoff and safe_float(r.get("result_usd")) <= 0:
            recent_losses.append(r)
    return {
        "period": "last_7_days",
        "losing_trades": recent_losses,
        "count": len(recent_losses),
    }
