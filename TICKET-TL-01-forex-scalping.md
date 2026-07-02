# TICKET TL-01: Tradie Lite — Forex Scalping System (CRT + Kill Zones + FVG + VWAP)

**Project:** Tradie Lite
**Author:** Isaac Njoroge
**Priority:** HIGH
**Type:** Full-stack implementation (local-first)
**Timezone reference:** Nairobi, EAT (UTC+3)
**Primary instrument:** EUR/USD
**Broker:** Exness (Demo Standard, MT5) — login `436594984`, server `ExnessKE-MT5Trial9`
**Primary interface:** Claude Code (TradingView MCP reads charts directly)
**Trading mode:** Manual execution, AI-assisted (Claude reads & signals; you place the trade)

---

## 1. Objective

Build a lightweight, local-first forex scalping system that connects Claude to TradingView (via MCP), Finnhub, and yfinance, so you can scalp EUR/USD during the London/NY kill zones using the CRT + Kill Zone + FVG + VWAP stack. Claude reads the live chart directly through the TradingView MCP — no screenshots required in the normal flow. Everything built here promotes into the full Tradie microservices project without rewrites.

**Scope boundary:** This ticket delivers a *signal + confirmation* system. Claude reads charts and returns entry/SL/TP. It does NOT auto-execute. You execute on Exness MT5 manually. Auto-execution is a later ticket with proper guardrails.

**Profitability principle:** The system is designed to make you trade **less and better**. Every trade pays spread; net profit comes from selectivity (A-plus setups only), not frequency. The whole pipeline is tuned to filter OUT marginal trades.

---

## 2. The Strategy Stack (Definition of "the setup")

This is the exact logic encoded in the Pine Script and used in every Claude analysis.

### Layer 1 — Kill Zone Filter (MUST HAVE)
Only trade during high-liquidity sessions. Skip everything else.

| Kill Zone | New York (ET) | **Nairobi (EAT)** | Priority |
|---|---|---|---|
| London Open | 02:00–05:00 | **09:00–12:00** | Active |
| NY Open | 07:00–10:00 | **14:00–17:00** | Active |
| London/NY Overlap | 08:00–11:00 | **15:00–18:00** | 🔥 BEST |

**Avoid entirely:** Asian session and the 12:00–15:00 EAT midday dead zone. Low volume = choppy price that ignores SMC structure and bleeds you through spread.

### Layer 2 — HTF Bias (H4 CRT range + M15 structure + VWAP)
- **CRT (Candle Range Theory):** Mark the H4 candle range (High/Low). Breakout + re-entry into range = reversal signal (traps retail breakout traders).
- **VWAP:** Only LONG above VWAP, only SHORT below VWAP.
- **Market structure:** BOS (continuation) / CHoCH (reversal) on M15.

### Layer 3 — Entry Trigger (M5)
- **FVG** forms in bias direction → enter on retest of the gap.
- **Liquidity sweep** of a prior high/low must happen first, then rejection.
- **Trade M5, not M1.** M1 setups die inside the analyze-and-execute window; M5 survives it. This is a profitability decision, not a preference.

### Layer 4 — Confirmation (gate before entry)
- **Spread < 1.5 pips** on EUR/USD (above this, cost structure is bad — skip).
- **No high-impact news** in the next 30 minutes (Finnhub calendar).
- Not correlated with an existing open position.

### The canonical trade sequence
```
1. Mark H4 CRT range (High / Low) at session start
2. Wait for a kill zone
3. Price sweeps range high/low (liquidity grab)
4. Price creates an FVG on M5 in the reversal direction
5. Price re-enters the range (CRT confirmation)
6. ENTRY on FVG retest
   - SL: beyond the sweep extreme (max ~50 pips)
   - TP: 2R, or the opposite range level
```

### Realistic expectations (mature, well-executed system)
| Combo | Est. win rate | R:R |
|---|---|---|
| Kill Zone + CRT + FVG | 60–65% | 2:1 |
| Kill Zone + VWAP + FVG | 55–60% | 2:1 |
| Full stack | 60–68% | 1.5–2:1 |

**Data limits:** Forex is decentralized — no real volume. Footprint, Delta, and true Volume Profile are excluded by design. VWAP uses tick volume as proxy. Everything is OHLC-based — exactly what carries into automated Tradie.

**DEFERRED to v2:** Inversion FVG. High-probability in theory but easy to misidentify; misreads cost money. Run the core stack first, add Inversion FVG once the journal proves the core profitable.

---

## 3. Architecture / Pipeline

```
┌────────────────────────────────────────────────────────────────┐
│                      TRADIE LITE PIPELINE                       │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  TradingView Desktop ──MCP(CDP:9222)──┐                         │
│   • EURUSD M15 (bias)                 │                         │
│   • EURUSD M5 (entry)                 ▼                         │
│   • Pine Script scanner        ┌──────────────┐                 │
│   • Native alerts ───push────► │  CLAUDE CODE │ ◄── you chat    │
│                                │  (interface  │     here        │
│  Data Bridge (FastAPI:5052) ──►│   + brain)   │                 │
│   • yfinance (price/OHLCV)     └──────┬───────┘                 │
│   • Finnhub (news/calendar)           │                         │
│   • /log-trade (journal)              │ signal (entry/SL/TP)    │
│                                       │                         │
│  MT5 MCP (READ-ONLY) ──────────────► (balance/positions only)  │
│   • Exness Demo                       │                         │
│                                       ▼                         │
│                              YOU execute manually               │
│                                on Exness MT5                     │
└────────────────────────────────────────────────────────────────┘
```

**Design principles**
- **Claude reads charts directly via the TradingView MCP** — no screenshot in the normal flow. Screenshot to Claude Desktop is an optional, rare visual gut-check only.
- **Claude Code is the interface** (the MCP lives there).
- **Pine Script is the real-time scanner, not Claude.** TradingView native alerts watch 24/7 for free; Claude does the on-demand pre-trade read when an alert fires.
- **MT5 MCP is READ-ONLY** — balance and positions. No order execution routed through it.
- **Local-first:** no cloud, no Kafka, no DB. Everything promotable to full Tradie.

---

## 4. Everything You Need to Download / Install

| # | Item | Where | Notes |
|---|---|---|---|
| 1 | **Node.js v18+** | nodejs.org | For TradingView MCP. Verify: `node --version` |
| 2 | **Python 3.11+** | python.org | Verify: `python --version` |
| 3 | **Claude Code** | `npm install -g @anthropic-ai/claude-code` | **Your primary interface** — hosts the MCPs |
| 4 | **Claude Desktop** | claude.ai/download | Optional — only for rare screenshot gut-checks |
| 5 | **TradingView Desktop app** | tradingview.com/desktop | Browser version has no debug port. Paid plan needed for real-time data |
| 6 | **MT5 Desktop** | Already installed ✅ | Logged in to Exness demo |
| 7 | **TradingView MCP** | `git clone https://github.com/tradesdontlie/tradingview-mcp.git` | Community-maintained. See §9 risk note |
| 8 | **metatrader-mcp-server** | `pip install metatrader-mcp-server` | READ-ONLY: balance/positions |
| 9 | **Bridge deps** | `pip install fastapi uvicorn yfinance requests python-dotenv` | Data bridge |
| 10 | **Finnhub API key** | finnhub.io (free tier) | News, calendar |

---

## 5. Repository Structure

```
tradie-lite/
├── README.md
├── .env                          # SECRET — never commit
├── .env.example                  # Template — commit this
├── .gitignore
│
├── data-bridge/
│   ├── main.py                   # FastAPI: price, calendar, news, session, log-trade
│   ├── requirements.txt
│   └── trades.csv                # Journal (auto-created, gitignored)
│
├── pinescript/
│   └── tradie_lite_scalper.pine  # The scanner (paste into TradingView)
│
├── claude-config/
│   └── mcp.json                  # Claude Code MCP config
│
├── prompts/
│   ├── morning_news_check.md
│   ├── bias_analysis.md
│   └── pre_trade_check.md
│
├── reference/
│   └── position_size_table.md    # Tape this to your monitor
│
└── scripts/
    ├── launch_tradingview_debug.bat
    ├── start_data_bridge.bat
    └── start_session.bat          # One-click session start
```

---

## 6. Configuration — `.env` and `.env.example`

### `.env.example` (commit this)
```env
# ── Finnhub ──────────────────────────────────
FINNHUB_API_KEY=your_finnhub_key_here

# ── Exness MT5 (Demo, READ-ONLY use) ─────────
MT5_LOGIN=436594984
MT5_PASSWORD=your_trading_password_here
MT5_SERVER=ExnessKE-MT5Trial9

# ── Data Bridge ──────────────────────────────
BRIDGE_PORT=5052

# ── Trading Params (mechanical risk rules) ───
PRIMARY_SYMBOL=EURUSD
YF_SYMBOL=EURUSD=X
RISK_PERCENT=1.0
MAX_TRADES_PER_DAY=3
MAX_DAILY_LOSS_PERCENT=3.0
MAX_CONSECUTIVE_LOSSES=2
MAX_SL_PIPS=50
MAX_SPREAD_PIPS=1.5
ACCOUNT_BALANCE=500
```

### `.gitignore`
```
.env
__pycache__/
*.pyc
node_modules/
tradingview-mcp/
.venv/
data-bridge/trades.csv
```

**Critical:** the real `.env` holds your MT5 trading password and Finnhub key. It must be in `.gitignore` before your first commit. If pushed by accident, reset both immediately.

---

## 7. Data Bridge — `data-bridge/main.py`

```python
import os
import csv
import requests
import yfinance as yf
from datetime import datetime, timedelta
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
    return {"symbol": YF_SYMBOL, "interval": interval,
            "bars": df.to_dict(orient="records")}


@app.get("/calendar")
def economic_calendar():
    """Today's high-impact economic events (news filter)."""
    url = f"https://finnhub.io/api/v1/calendar/economic?token={FINNHUB_KEY}"
    r = requests.get(url, timeout=10)
    data = r.json().get("economicCalendar", [])
    today = datetime.now().strftime("%Y-%m-%d")
    todays = [e for e in data if e.get("time", "").startswith(today)]
    high = [e for e in todays if str(e.get("impact")) in ("high", "3")]
    return {"date": today, "high_impact": high, "all_today": todays}


@app.get("/news")
def forex_news():
    url = f"https://finnhub.io/api/v1/news?category=forex&token={FINNHUB_KEY}"
    r = requests.get(url, timeout=10)
    return {"headlines": r.json()[:10]}


@app.get("/session")
def current_session():
    """Which kill zone are we in right now (EAT)?"""
    now = datetime.utcnow() + timedelta(hours=3)
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
    with open(TRADES_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "direction", "entry", "sl", "tp",
                        "setup", "result_pips", "result_usd", "notes"])
        w.writerow([datetime.now().isoformat(), t.direction, t.entry, t.sl,
                    t.tp, t.setup, t.result_pips, t.result_usd, t.notes])
    return {"logged": True}


@app.get("/journal-stats")
def journal_stats():
    """Quick P&L summary from the journal."""
    if not os.path.exists(TRADES_CSV):
        return {"trades": 0}
    with open(TRADES_CSV) as f:
        rows = list(csv.DictReader(f))
    wins = [r for r in rows if float(r["result_usd"]) > 0]
    total_usd = sum(float(r["result_usd"]) for r in rows)
    return {"trades": len(rows), "wins": len(wins),
            "win_rate": round(len(wins) / len(rows) * 100, 1) if rows else 0,
            "total_usd": round(total_usd, 2)}
```

### `data-bridge/requirements.txt`
```
fastapi
uvicorn
yfinance
requests
python-dotenv
pydantic
```

Run: `uvicorn main:app --port 5052`

---

## 8. TradingView Setup + Pine Script + Alerts

### 8a. Chart layout (TradingView Desktop)
- **EUR/USD M15** — bias chart. Add: EMA 9, EMA 21, VWAP, RSI(14).
- **EUR/USD M5** — execution chart. Add: EMA 9, EMA 21, VWAP, RSI(14), + the Tradie Pine Script.

### 8b. The Pine Script — `pinescript/tradie_lite_scalper.pine`

Paste into TradingView → Pine Editor → New → paste → Save → Add to Chart.

```pine
//@version=5
indicator("Tradie Lite Scalper — CRT+KillZone+FVG+VWAP", overlay=true, max_bars_back=500)

// ═══ INPUTS ═══
killZoneOnly = input.bool(true, "Only signal during kill zones")
struct_lb    = input.int(10, "Structure lookback")
sweep_lb     = input.int(20, "Liquidity sweep lookback")

// ═══ KILL ZONE (UTC bar time) ═══
// London 07:00-10:00 UTC | NY 12:00-15:00 UTC | Overlap 12:00-16:00 UTC
h = hour(time, "UTC")
inLondon  = h >= 7  and h < 10
inNY      = h >= 12 and h < 15
inOverlap = h >= 12 and h < 16
inKillZone = inLondon or inNY or inOverlap
killOk = not killZoneOnly or inKillZone

// ═══ EMA + VWAP BIAS ═══
ema9  = ta.ema(close, 9)
ema21 = ta.ema(close, 21)
vwapV = ta.vwap(hlc3)
plot(ema9,  "EMA 9",  color=color.yellow, linewidth=1)
plot(ema21, "EMA 21", color=color.blue,   linewidth=2)
plot(vwapV, "VWAP",   color=color.orange, linewidth=2)
bullBias = ema9 > ema21 and close > vwapV
bearBias = ema9 < ema21 and close < vwapV

// ═══ RSI ═══
rsi = ta.rsi(close, 14)

// ═══ MARKET STRUCTURE (BOS) ═══
swingHigh = ta.highest(high, struct_lb)
swingLow  = ta.lowest(low,  struct_lb)
bullBOS = close > swingHigh[1] and close[1] <= swingHigh[1]
bearBOS = close < swingLow[1]  and close[1] >= swingLow[1]
plotshape(bullBOS, "BOS Up",   shape.triangleup,   location.belowbar, color.green, size=size.tiny)
plotshape(bearBOS, "BOS Down", shape.triangledown, location.abovebar, color.red,   size=size.tiny)

// ═══ FVG ═══
bullFVG = low[0] > high[2]
bearFVG = high[0] < low[2]
if bullFVG
    box.new(bar_index-2, low[0], bar_index, high[2], border_color=color.new(color.green,60), bgcolor=color.new(color.green,88))
if bearFVG
    box.new(bar_index-2, high[0], bar_index, low[2], border_color=color.new(color.red,60), bgcolor=color.new(color.red,88))

// ═══ LIQUIDITY SWEEP (condition only — folded into signal, not alerted separately) ═══
recHigh = ta.highest(high, sweep_lb)[1]
recLow  = ta.lowest(low,  sweep_lb)[1]
sweepHigh = high > recHigh and close < recHigh
sweepLow  = low  < recLow  and close > recLow
plotshape(sweepHigh, "Sweep H", shape.xcross, location.abovebar, color.purple, size=size.small)
plotshape(sweepLow,  "Sweep L", shape.xcross, location.belowbar, color.purple, size=size.small)

// ═══ COMPOSITE SIGNAL ═══
longSig  = killOk and bullBias and rsi > 45 and rsi < 68 and (bullBOS or bullFVG or sweepLow)
shortSig = killOk and bearBias and rsi < 55 and rsi > 32 and (bearBOS or bearFVG or sweepHigh)
plotshape(longSig,  "LONG",  shape.labelup,   location.belowbar, color.green, text="BUY",  size=size.normal, textcolor=color.white)
plotshape(shortSig, "SHORT", shape.labeldown, location.abovebar, color.red,   text="SELL", size=size.normal, textcolor=color.white)

// ═══ ALERTS (two only — sweep is folded into the directional signals) ═══
alertcondition(longSig,  "Tradie LONG",  "TRADIE LONG {{ticker}} @ {{close}} — run pre-trade check before entry")
alertcondition(shortSig, "Tradie SHORT", "TRADIE SHORT {{ticker}} @ {{close}} — run pre-trade check before entry")
```

### 8c. Alerts (your 24/7 scanner)
For LONG and SHORT (two alerts only — no separate sweep alert):
1. Right-click M5 chart → **Add alert**.
2. **Condition:** `Tradie Lite Scalper` → `Tradie LONG` (then repeat for SHORT).
3. **Trigger:** **Once Per Bar Close** (non-repainting — avoids false intrabar alerts).
4. **Notifications:** App notification + Popup + (optional) Email. Enable TradingView mobile push for phone alerts.
5. **Name:** `EURUSD LONG M5` / `EURUSD SHORT M5`.

---

## 9. Claude Code MCP Config — `claude-config/mcp.json`

Copy to `C:\Users\User\.claude\mcp.json` (create `.claude` if needed).

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "node",
      "args": ["C:\\Users\\User\\tradie-lite\\tradingview-mcp\\src\\server.js"]
    },
    "mt5": {
      "command": "python",
      "args": ["-m", "metatrader_mcp_server"],
      "env": {
        "MT5_LOGIN": "436594984",
        "MT5_PASSWORD": "your_trading_password_here",
        "MT5_SERVER": "ExnessKE-MT5Trial9"
      }
    }
  }
}
```

**Launch TradingView in debug mode** — `scripts/launch_tradingview_debug.bat`:
```bat
@echo off
start "" "C:\Program Files\TradingView\TradingView.exe" --remote-debugging-port=9222
```

**Verify:** run `claude`, ask: `Use tv_health_check to verify TradingView is connected.`

### ⚠️ Security / ToS notes
- The TradingView MCP drives the desktop app via Chrome DevTools Protocol on `localhost:9222`. It is **not affiliated with or endorsed by TradingView**, and programmatic control **may conflict with TradingView's Terms of Use**. No community bans reported to date, but you accept that risk.
- Only run the debug port during sessions; keep it bound to localhost.
- Keep the **MT5 MCP read-only** — do not enable order execution through it in this phase.
- `metatrader-mcp-server` is third-party — check its GitHub before trusting it.

---

## 10. Risk Management & Position Sizing (mechanical — you set, system enforces)

Risk rules are **fixed in advance**, never negotiated per trade. This is what stops a losing streak from becoming a blown account.

- **Risk per trade:** 1% = 5 USD on 500 balance.
- **Max 3 trades/day.** Hard cap.
- **Stop after 2 consecutive losses.**
- **Daily loss limit 3% = 15 USD.** Hit it → session over.
- **SL never wider than ~50 pips.** Wider → skip the trade.

### `reference/position_size_table.md` (tape to monitor)
On 0.01 lots EUR/USD (~0.10 USD/pip), SL distance sets your risk:

| SL distance | Risk at 0.01 lots | OK? |
|---|---|---|
| 25 pips | 2.50 USD | ✅ |
| 40 pips | 4.00 USD | ✅ |
| 50 pips | 5.00 USD | ✅ (max) |
| 70 pips | 7.00 USD | ❌ skip or resize |

**Rule: SL wider than ~50 pips → the setup is wrong or you skip.** No mental math under pressure. Tradie Lite enforces the limits you set; it does not decide risk for you.

---

## 11. End-to-End Daily Workflow (MCP-native, Claude Code, Nairobi EAT)

1. **08:45** — one-click `start_session.bat` (TV debug + data bridge). Open **Claude Code**.
2. **09:00** — Run the **news check** prompt. Claude calls `/calendar`; write down red-news no-trade windows.
3. **09:00** — Run the **bias** prompt. Claude reads EUR/USD M15 **directly via the TradingView MCP** — structure, EMA/VWAP values, H4 CRT range. Returns a one-line session bias. No screenshot.
4. **You wait.** The Pine Script alert is your 24/7 scanner — it watches, not you. Most of the session is waiting.
5. **Alert fires** ("EURUSD LONG M5"). Quick glance: kill zone active? Matches session bias? If obviously not, ignore.
6. **If it looks valid** — run the **pre-trade** prompt. Claude reads live M5+M15 **via the MCP**, checks the full stack + spread, calls `/calendar` for imminent news, returns entry / SL / TP / R:R — or SKIP. (Screenshot to Claude Desktop only if you want a visual gut-check on a specific zone — optional, rare.)
7. **You execute on Exness MT5 yourself.** Volume 0.01, type SL and TP, click Buy/Sell. Manual — faster and safer than routing through Claude.
8. **Set and walk away.** Let SL/TP work. Don't close early out of fear — that throws away planned profit.
9. **Log the trade** immediately via `/log-trade` (or spreadsheet): entry, SL, TP, setup, result.
10. **18:00** — hard stop. Close anything open. Check `/journal-stats` for the session P&L.

**On auto-execution:** the MT5 MCP *can* send orders, but it stays read-only this phase. Manual execution is faster than describing an order and waiting, and removes money-losing errors (wrong symbol/size, mis-fires). Automate only when building full Tradie with guardrails and a profitable track record.

### Trading hours & trade count
- **09:00–12:00** London Open — active.
- **12:00–15:00** — dead zone. Step away. Not a trading window.
- **15:00–18:00** overlap — **best window**, most quality setups.

**1–3 A-plus trades per day. Hard cap 3. NOT "as many as you can."** Selectivity is the profit engine — "scalping" refers to small target moves, not high frequency. Each trade pays spread; high frequency multiplies cost drag and bad-fill exposure. Most profitable days are 1–2 clean trades. Three good setups + ten skips = a winning day. Ten trades = a losing pattern regardless of that day's result.

---

## 12. The Three MCP-Native Prompts (Claude Code)

**`prompts/morning_news_check.md`**
```
Call the Tradie Lite data bridge at http://localhost:5052.
GET /calendar and /session. List today's high-impact EUR/USD or USD events
with EAT times, and confirm the current kill zone.
Verdict in 3 lines: safe to scalp today? Which exact time windows must I avoid?
```

**`prompts/bias_analysis.md`**
```
Using the TradingView MCP, read my EUR/USD M15 chart directly.
From the live data (EMA9 vs EMA21, price vs VWAP, recent structure):
- Bias bullish or bearish?
- H4 CRT range high/low?
- Likely liquidity sweep targets in the next 3 hours?
Give me ONE line to hold as my session bias.
```

**`prompts/pre_trade_check.md`**
```
Pine fired a [LONG/SHORT] on EUR/USD M5.
Using the TradingView MCP, read the live M5 and M15 charts. Answer each yes/no:
1. Kill zone active? 2. Matches M15 session bias + VWAP?
3. Valid liquidity sweep before the move? 4. FVG retest present? 5. RSI supportive?
6. Current EUR/USD spread under 1.5 pips?
Also call bridge /calendar — any red news in the next 30 min?
If ALL yes: give entry, SL (beyond sweep extreme, max 50 pips), TP (2R), R:R.
If ANY no: SKIP and name the failed check. Be strict — default to skip.
```

The "be strict, default to skip" wording is deliberate — Claude's job is to filter OUT marginal trades, because profitability depends on trading less, not more.

---

## 13. How This Promotes Into Full Tradie

| Tradie Lite component | Full Tradie microservice | Change required |
|---|---|---|
| `data-bridge/main.py` | Market Data Service | Wrap endpoints as Kafka producers |
| `/log-trade` + `/journal-stats` | Trade Journal / Analytics Service | Move CSV to TimescaleDB |
| Pine Script (manual alerts) | Strategy Engine | Port logic to Spring Boot signal detection |
| Manual Exness execution | Order Executor | MT5 bridge + auto-execution guardrails |
| Claude prompt files | Strategy Engine ↔ Claude API | Move prompts into service calls |
| `.env` | AWS Parameter Store / K8s secrets | Same keys, managed storage |

Nothing is throwaway. Tradie Lite is Tradie's strategy core, de-risked and validated by hand.

---

## 14. Acceptance Criteria

- [ ] Repo created; `.gitignore` excludes `.env` and `trades.csv` (verified before first commit).
- [ ] Node 18+, Python 3.11+, Claude Code installed and version-checked.
- [ ] Data bridge runs; `/health`, `/price`, `/calendar`, `/session`, `/log-trade`, `/journal-stats` return valid JSON.
- [ ] Finnhub key works (calendar returns today's events).
- [ ] TradingView Desktop launches in debug mode; `tv_health_check` passes in Claude Code.
- [ ] Claude reads EUR/USD M5 + M15 live via the MCP (no screenshot).
- [ ] MT5 MCP connects READ-ONLY; Claude reads the 500 USD balance and positions.
- [ ] Pine Script compiles; plots EMAs/VWAP/FVG/sweeps; prints BUY/SELL; two alerts fire on bar close.
- [ ] Position-size table printed and visible.
- [ ] All 3 prompts saved and tested against the live chart.
- [ ] One full session completed end-to-end: news → bias → alert → pre-trade → manual entry with SL/TP → `/log-trade`.

---

## 15. Build Order (fastest path to trading)

1. Repo + `.env` + `.gitignore` + position-size table (45 min)
2. Data bridge — paste `main.py`, `pip install`, run, hit `/health` (45 min)
3. Finnhub key → test `/calendar` (15 min)
4. Pine Script → paste, add to chart, verify plots (30 min)
5. Alerts → LONG/SHORT, test one fires on bar close (20 min)
6. TradingView MCP → clone, `npm install`, debug-launch, `tv_health_check` (45 min)
7. MT5 MCP (read-only) → `pip install`, config, read balance (30 min)
8. Prompt files + `start_session.bat` (30 min)
9. One full dry-run session

Total build ≈ 4–5 focused hours across 2–3 days.
