# Tradie Lite — Full Documentation & Conversation Log

*Compiled from all Tradie Lite discussions (primary source: https://claude.ai/chat/e9056545-314a-48a6-b22e-9783adac049b)*

---

## 1. What Tradie Lite Is

Tradie Lite is a **lightweight, local-first, daily-use system** for **manual EUR/USD scalping with AI assistance**, built as the fast-to-deploy companion to the larger, fully automated **Tradie** project (microservices architecture: Spring Boot, Kafka, TimescaleDB, Python FastAPI, IBKR, MT5).

- **No Kafka, no TimescaleDB, no microservices.** Just the minimum pipes needed to connect Claude to data sources and TradingView so Isaac can trade manually with AI assistance every day.
- **Primary instrument:** EUR/USD
- **Primary interface:** **Claude Code** (not Claude Desktop) — the MCPs live there
- **Broker:** Exness — Demo Standard account, MT5, login `436594984`, server `ExnessKE-MT5Trial9`
- **Timezone reference:** Nairobi, EAT (UTC+3)
- **Trading mode:** Manual execution, AI-assisted — Claude reads charts and returns entry/SL/TP; Isaac places every trade himself
- **Purpose:** To make money. The system exists to help Isaac trade **less and better**, not to automate trading away from him prematurely.

**Scope boundary:** Tradie Lite delivers a *signal + confirmation* system only. It does **not** auto-execute trades. Auto-execution is a later ticket, reserved for the full Tradie project once there's a proven, profitable track record.

---

## 2. What Carries Over Into Full Tradie

Nothing built for Tradie Lite is throwaway — it's designed as Tradie's strategy core, de-risked and validated by hand first.

| Tradie Lite component | Full Tradie microservice | Change required |
|---|---|---|
| `data-bridge/main.py` | Market Data Service | Wrap endpoints as Kafka producers |
| `/log-trade` + `/journal-stats` | Trade Journal / Analytics Service | Move CSV to TimescaleDB |
| Pine Script (manual alerts) | Strategy Engine | Port logic to Spring Boot signal detection |
| Manual Exness execution | Order Executor | MT5 bridge + auto-execution guardrails |
| Claude prompt files | Strategy Engine ↔ Claude API | Move prompts into service calls |
| `.env` | AWS Parameter Store / K8s secrets | Same keys, managed storage |
| Local kill-zone check | Scheduler / session service | Same time logic, cron-driven |

---

## 3. Core Architecture Decisions

- **Claude Code is the interface** — the TradingView MCP and MT5 MCP both live inside it, so Claude reads charts **directly**, without needing screenshots in the normal flow.
- **Pine Script is the real-time scanner, not Claude.** TradingView's native alerts watch the chart 24/7 for free; Claude only does the on-demand pre-trade read when an alert fires. This avoids wasting AI calls on constant chart-watching.
- **MT5 MCP is kept READ-ONLY** — balance and open positions only. No order execution is routed through it in this phase.
- **Claude Desktop is demoted to an optional screenshot backup** — used only rarely, for a visual gut-check on a specific zone.
- **Local-first:** no cloud, no Kafka, no database. Everything here is promotable into full Tradie later without rewrites.

---

## 4. The Strategy Stack (Definition of "the setup")

This is the exact logic encoded in the Pine Script and used in every Claude analysis.

### Layer 1 — Kill Zone Filter (MUST HAVE)
Only trade during high-liquidity sessions; skip everything else.

| Kill Zone | New York (ET) | **Nairobi (EAT)** | Priority |
|---|---|---|---|
| London Open | 02:00–05:00 | **09:00–12:00** | Good |
| NY Open | 07:00–10:00 | **14:00–17:00** | Good |
| London/NY Overlap | 08:00–11:00 | **15:00–18:00** | 🔥 BEST |

**Avoid entirely:** Asian session (roughly 02:00–09:00 EAT) and NY afternoon. Low volume = choppy price that ignores SMC structure.

### Layer 2 — HTF Bias (H4 CRT range + M15 structure + VWAP)
- **CRT (Candle Range Theory):** Mark the H4 candle range (High/Low). A breakout followed by re-entry into the range = reversal signal (traps retail breakout traders).
- **VWAP:** Only LONG above VWAP, only SHORT below VWAP.
- **Market structure:** BOS (Break of Structure = continuation) / CHoCH (Change of Character = reversal) on M15.

### Layer 3 — Entry Trigger (M5/M1)
- **FVG (Fair Value Gap)** forms in the bias direction → enter on retest of the gap.
- **Inversion FVG** (a filled FVG that then acts as opposite S/R) = highest-probability entry — **deferred to v2**.
- **Liquidity sweep** of a previous high/low must happen first, then rejection. Folded into the directional (LONG/SHORT) signals rather than given a standalone alert.

### Layer 4 — Confirmation (gate before entry)
- Spread acceptable (< 1.5 pips on EUR/USD).
- No high-impact news in the next 30 minutes (checked via the data bridge's `/calendar` endpoint, powered by Finnhub).
- Not correlated with an existing open position.

### The Canonical Trade Sequence
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

### Worked Example (EUR/USD)
```
4:00 AM NY: CRT Range marked
            High: 1.0850
            Low: 1.0800

8:30 AM NY (Kill Zone):
            Price spikes to 1.0862 (sweeps high)
            Creates bearish FVG: 1.0855–1.0858
            Closes back at 1.0845 (inside range)

8:35 AM: ENTRY
            SELL @ 1.0855 (FVG retest)
            SL: 1.0865 (above sweep)
            TP: 1.0815 (2R)

Result: +40 pips, 2R win
```

### Realistic Expectations (win rate / R:R by combo)

| Combo | Est. win rate | R:R |
|---|---|---|
| Kill Zone + CRT + FVG | 60–65% | 2:1 |
| Kill Zone + Inversion FVG | 65–70% | 2:1 |
| Kill Zone + VWAP + FVG | 55–60% | 2:1 |
| Full stack | 60–68% | 1.5–2:1 |

**Data limitation note:** Forex is decentralized — there's no real traded volume. Footprint charts, Delta, and true Volume Profile are **not available** and are excluded by design (they require tick data / Sierra Chart, or are only partially available via IBKR). VWAP uses tick volume as a proxy. FVG, CRT, and structure only need OHLC candle data, which Tradie Lite has.

| Tool | Requires | Available in Tradie Lite? |
|---|---|---|
| Footprint Charts | Tick data, Sierra Chart | ❌ No |
| Delta | Tick data, order flow | ❌ No |
| Volume Profile | Real volume (not tick volume) | ⚠️ Partial (IBKR only) |
| VWAP | Intraday data | ✅ Yes |
| FVG | OHLC candles | ✅ Yes |
| CRT | OHLC candles | ✅ Yes |

---

## 5. Everything Needed to Download / Install

| # | Item | Where | Notes |
|---|---|---|---|
| 1 | Node.js v18+ | nodejs.org | For TradingView MCP. Verify: `node --version` |
| 2 | Python 3.11+ | python.org | Verify: `python --version` |
| 3 | **Claude Code** | `npm install -g @anthropic-ai/claude-code` | Primary interface — hosts the MCPs |
| 4 | Claude Desktop | claude.ai/download | Optional — rare screenshot gut-checks only |
| 5 | TradingView Desktop app | tradingview.com/desktop | Browser version has no debug port; paid plan needed for real-time data |
| 6 | MT5 Desktop | (already installed) | Logged in to Exness demo |
| 7 | TradingView MCP | `git clone https://github.com/tradesdontlie/tradingview-mcp.git` | Community-maintained — see risk note below |
| 8 | `metatrader-mcp-server` | `pip install metatrader-mcp-server` | READ-ONLY: balance/positions |
| 9 | Bridge dependencies | `pip install fastapi uvicorn yfinance requests python-dotenv` | For the data bridge |
| 10 | Finnhub API key | finnhub.io (free tier) | News, economic calendar |

**Risk note on the TradingView MCP:** it is **not affiliated with or endorsed by TradingView**, and programmatic control **may conflict with TradingView's Terms of Use**. No community bans reported to date, but this is an accepted risk. Only run the debug port during active sessions, and keep it bound to localhost. `metatrader-mcp-server` is third-party — worth checking its GitHub before trusting it.

---

## 6. Repository Structure

```
tradie-lite/
├── README.md                  # Setup + daily workflow guide
├── .env                        # SECRET — API keys, MT5 credentials — never commit
├── .env.example                 # Template (committed to repo)
├── .gitignore                  # Excludes .env, trades.csv, __pycache__, node_modules
│
├── data-bridge/                # Python FastAPI — yfinance + Finnhub
│   ├── main.py                 # All endpoints: price, calendar, news, session, log-trade, journal-stats
│   ├── requirements.txt
│   ├── trades.csv              # Journal (auto-created, gitignored)
│   └── start.sh / start.bat
│
├── pinescript/
│   └── tradie_lite_scalper.pine   # The scanner — paste into TradingView
│
├── tradingview-mcp/             # Git submodule or cloned repo
│   └── (cloned from github.com/tradesdontlie/tradingview-mcp)
│
├── claude-config/
│   └── mcp.json                 # MCP config for Claude Code (MT5 + TradingView)
│
├── prompts/                     # Saved Claude prompts for daily use
│   ├── morning_news_check.md
│   ├── bias_analysis.md
│   └── pre_trade_check.md
│
├── reference/
│   └── position_size_table.md    # Tape this to your monitor
│
└── scripts/
    ├── launch_tradingview_debug.bat   # Launches TV in debug mode
    ├── start_data_bridge.bat          # Starts FastAPI bridge
    └── start_session.bat              # Runs both at once — one-click session start
```

### Data bridge endpoints confirmed
`/health`, `/price`, `/calendar`, `/session`, `/log-trade`, `/journal-stats` — all return valid JSON.

### `start_session.bat` (what "deploy to prod" means for Tradie Lite)
Since this is a local tool (not a web app), "prod" simply means it runs reliably every day with one click:

```batch
@echo off
echo Starting Tradie Lite session...

:: Start TradingView in debug mode
start "" "C:\Program Files\TradingView\TradingView.exe" --remote-debugging-port=9222

:: Start data bridge
start cmd /k "cd /d %~dp0data-bridge && uvicorn main:app --port 5052"

:: Open Claude Code
start cmd /k "claude"

echo Tradie Lite is ready. Open TradingView and Claude Code.
```

Double-click that every morning and the full stack is running.

---

## 7. Pine Script — the Scanner

- Two alerts only: **LONG** and **SHORT**, both **bar-close triggered**.
- The **standalone sweep alert was removed** — liquidity sweep confirmation is folded into the directional (LONG/SHORT) signals rather than firing separately.
- Plots EMAs, VWAP, FVG zones, and sweeps; prints BUY/SELL labels on the chart.
- The Pine Script runs as TradingView's native 24/7 scanner — it watches the market, not Isaac and not Claude. Claude only steps in for the on-demand pre-trade read once an alert fires.

---

## 8. Risk Management & Position Sizing (mechanical — Isaac sets, the system enforces)

Risk rules are **fixed in advance**, never negotiated per trade. This is what stops a losing streak from becoming a blown account.

- **Risk per trade:** 1% = 5 USD on a 500 USD balance.
- **Max 3 trades/day.** Hard cap.
- **Stop after 2 consecutive losses.**
- **Daily loss limit:** 3% = 15 USD. Hit it → session over.
- **SL never wider than ~50 pips.** Wider → skip the trade.

### Position-size reference table (`reference/position_size_table.md` — tape to monitor)
On 0.01 lots EUR/USD (~0.10 USD/pip), SL distance sets risk:

| SL distance | Risk at 0.01 lots | OK? |
|---|---|---|
| 25 pips | 2.50 USD | ✅ |
| 40 pips | 4.00 USD | ✅ |
| 50 pips | 5.00 USD | ✅ (max) |
| 70 pips | 7.00 USD | ❌ skip or resize |

**Rule: SL wider than ~50 pips → the setup is wrong, or Isaac skips.** No mental math under pressure. Tradie Lite enforces the limits Isaac sets; it does not decide risk on his behalf.

---

## 9. The Three Claude Prompts

### `prompts/morning_news_check.md`
Calls the data bridge's `/calendar` endpoint to surface today's high-impact news, so Isaac can mark red-news windows as no-trade times.

### `prompts/bias_analysis.md`
Claude reads EUR/USD M15 (structure, EMA/VWAP values, H4 CRT range, any FVG/Order Block zones already visible) directly via the TradingView MCP, and returns a **one-line session bias** to hold for the day. No screenshot needed.

### `prompts/pre_trade_check.md`
```
Pine Script fired a [LONG/SHORT] signal on EUR/USD M5.
Confirm against the full stack — answer each yes/no:
1. Kill zone active?
2. Matches M15 session bias + VWAP?
3. Valid liquidity sweep before the move?
4. FVG retest present?
5. RSI supportive?
6. Current EUR/USD spread under 1.5 pips?
Also call bridge /calendar — any red news in the next 30 min?

If ALL yes: give entry, SL (beyond sweep extreme, max 50 pips), TP (2R), R:R.
If ANY no: SKIP and name the failed check. Be strict — default to skip.
```

The **"be strict, default to skip"** wording is deliberate — Claude's job is to filter OUT marginal trades, because profitability depends on trading less, not more.

---

## 10. End-to-End Daily Workflow (MCP-native, Claude Code, Nairobi EAT)

1. **08:45** — one-click `start_session.bat` launches TradingView (debug mode) + data bridge. Open **Claude Code**.
2. **09:00** — Run the **news check** prompt. Claude calls `/calendar`, gives red-news times. Write these down as no-trade windows.
3. **09:00** — Run the **bias** prompt. Claude reads EUR/USD M15 **directly via the TradingView MCP** — structure, EMA/VWAP values, H4 CRT range. Returns a one-line session bias. No screenshot.
4. **Wait.** The Pine Script alert is the 24/7 scanner — it watches, not Isaac, not Claude. Most of the session is waiting.
5. **Alert fires** (e.g. "EURUSD LONG M5"). Quick glance: kill zone active? Matches session bias? If obviously not, ignore it.
6. **If it looks valid** — run the **pre-trade** prompt. Claude reads the live M5 + M15 **via the MCP**, checks the full stack + spread, calls `/calendar` for imminent news, and returns entry / SL / TP / R:R — or SKIP. (Screenshot to Claude Desktop only for an optional, rare visual gut-check on a specific zone.)
7. **Execute on Exness MT5 manually.** Volume 0.01, type in SL and TP, click Buy/Sell. Manual — faster and safer than routing through Claude.
8. **Set and walk away.** Let SL/TP do the work. Don't babysit or close early out of fear — that throws away planned profit.
9. **Log the trade immediately** via `/log-trade` (or spreadsheet): entry, SL, TP, setup, result.
10. **18:00 — hard stop.** Close anything open. Check `/journal-stats` for the session's P&L.

**On asking Claude Code to place the trade:** the MT5 MCP *can* technically send orders, but this is deliberately **not enabled**. Manual execution is faster in practice than describing the order and waiting, and it removes a category of money-losing errors (wrong symbol, wrong size, an order firing when it shouldn't). Automate execution only when building full Tradie, with proper guardrails and a profitable track record behind it. **For now: Claude reads and signals, Isaac executes.**

---

## 11. Trading Hours & Trade Count — the Profit-Critical Rules

**Don't trade the full 09:00–18:00 span straight through.** That window contains the kill zones, but it isn't an instruction to trade the whole time. Trading the dead midday hours is how morning gains get given back.

- **09:00–12:00** (London Open) — active, watch for setups.
- **12:00–15:00** — dead zone for EUR/USD. Step away. Not a trading window.
- **15:00–18:00** (London/NY overlap) — the best window. Most quality setups land here. 🔥

**How many trades? 1–3 per day, A-plus setups only — hard cap of 3. Not "as many as possible."**

This is the single most important profitability point in the whole system: **trading as many times as possible during the session is the fastest way to lose money, not make it.** "Scalping" refers to the small *size* of the moves targeted, not high *frequency*. Every trade pays the spread; high frequency multiplies cost drag and exposure to bad fills. **Zero trades in a day is a valid, and often correct, outcome** — it means no A-plus setup appeared, and that's the system working as intended, not a failure.

---

## 12. Isaac's Exness Demo Account (MT5 connection)

- **Login:** `436594984`
- **Server:** `ExnessKE-MT5Trial9`
- Successfully connected during the session after resolving a trading-password issue.
- MT5 MCP is configured **read-only** for this phase — it can report balance and open positions, but no orders are routed through it.

---

## 13. Instrument Choice: Why EUR/USD, Not Gold or Stocks (Yet)

**Gold (XAU/USD)** — highest opportunity, highest risk. Big potential moves (50–150 pips in minutes on M1/M5), but scalping gold is unforgiving: slippage, spread widening (50+ pips during major news releases), and slower execution can destroy an edge fast. On a 0.01 lot / 500 USD demo balance, that volatility cuts both ways.

**Forex (EUR/USD)** — most controllable, best fit for where Tradie Lite is right now. The entire system (SL/TP tables, 25–50 pip stop assumptions, 1% risk = 5 USD math) is calibrated around EUR/USD's typical pip behavior. Gold's larger dollar-denominated swings would require rebuilding the position-sizing table from scratch.

**Stocks** — not a fit for the current scalping setup. Session-specific liquidity (US market hours only), wider spreads outside the open/close windows, and Exness's stock CFD offering isn't built around the tight ICT/SMC scalping stack developed here.

**Recommendation:** Stay on EUR/USD until Tradie Lite is proven in the trade journal. Testing a new instrument at the same time as validating the strategy itself means testing two unknowns at once. Once the EUR/USD journal shows consistent, disciplined execution over several weeks, **gold becomes a natural v2 addition** — same CRT + Kill Zone + FVG + VWAP stack, just with a rebuilt position-size table for gold's pip value and wider SL/TP assumptions to match its structure.

---

## 14. Claude Cowork / Computer Use — Ruled Out for This Use Case

Isaac asked whether Cowork's screen-viewing capability could watch MT5/TradingView directly.

- Cowork has a **Computer Use** capability (research preview, Pro/Max plans) that can take screenshots, read the screen, and click/type on the user's behalf.
- **Anthropic explicitly restricts trading and investment platforms from computer use by default** — official guidance calls out investment/trading platforms as a blocked category and separately warns against using computer use for stock trading or investment transactions.
- Additional reasons it wouldn't be a good fit even if unblocked: it runs outside the sandboxed VM (sees everything on screen, not just the intended app); it's slower than a direct MCP integration; and it's a research preview with acknowledged reliability limits on complex multi-step workflows.
- **Conclusion:** the MCP-based setup (TradingView MCP for chart data, Isaac for execution) is the better-fitted approach — not a workaround for a missing capability. Cowork remains useful for non-trading tasks, just not this system.

---

## 15. Acceptance Criteria (Definition of Done)

- [ ] Repo created; `.gitignore` excludes `.env` and `trades.csv` (verified before first commit).
- [ ] Node 18+, Python 3.11+, Claude Code installed and version-checked.
- [ ] Data bridge runs; `/health`, `/price`, `/calendar`, `/session`, `/log-trade`, `/journal-stats` all return valid JSON.
- [ ] Finnhub key works (calendar returns today's events).
- [ ] TradingView Desktop launches in debug mode; `tv_health_check` passes in Claude Code.
- [ ] Claude reads EUR/USD M5 + M15 live via the MCP (no screenshot needed).
- [ ] MT5 MCP connects READ-ONLY; Claude can read the 500 USD demo balance and positions.
- [ ] Pine Script compiles; plots EMAs/VWAP/FVG/sweeps; prints BUY/SELL labels; two alerts (LONG/SHORT) fire on bar close.
- [ ] Position-size table printed and visible.
- [ ] All 3 prompt files saved and tested against a live chart.
- [ ] One full session completed end-to-end: news check → bias → alert → pre-trade check → manual entry with SL/TP → `/log-trade`.

---

## 16. Build Order (Fastest Path to Trading)

1. Repo + `.env` + `.gitignore` + position-size table (45 min)
2. Data bridge — paste `main.py`, `pip install`, run, hit `/health` (45 min)
3. Finnhub key → test `/calendar` (15 min)
4. Pine Script → paste into TradingView, add to chart, verify plots (30 min)
5. Alerts → create LONG/SHORT alerts, test one fires on bar close (20 min)
6. TradingView MCP → clone, `npm install`, debug-launch, `tv_health_check` (45 min)
7. MT5 MCP (read-only) → `pip install`, config, read balance (30 min)
8. Prompt files + `start_session.bat` (30 min)
9. One full dry-run session, end-to-end

**Total build time ≈ 4–5 focused hours across 2–3 days.**

---

## 17. Key Decisions Log

| Decision | Outcome |
|---|---|
| Interface | Claude Code (primary), Claude Desktop (optional screenshot backup only) |
| Chart reading | TradingView MCP — direct, no screenshots in normal flow |
| Scanner | Pine Script native TradingView alerts (24/7, free), not Claude polling |
| MT5 MCP scope | Read-only (balance/positions) — auto-execution explicitly excluded |
| Inversion FVG | Deferred to v2 |
| Standalone sweep alert | Removed — folded into directional LONG/SHORT signals |
| Journal | `/log-trade` and `/journal-stats` endpoints added to the data bridge |
| Trade cadence | 1–3 A-plus trades/day, hard cap 3; zero is a valid daily outcome |
| Trading window | Concentrate on 15:00–18:00 EAT overlap; avoid the 12:00–15:00 dead zone |
| Instrument | EUR/USD only until proven; gold is a v2 addition |
| Cowork/Computer Use | Ruled out — Anthropic blocks trading platforms from computer use by default |
| Build estimate | 4–5 hours across 2–3 days |

---

## 18. Is Tradie Lite a Good Idea?

**Yes — with the MCP-native workflow.** The system is designed as a money-making tool, not a learning exercise: direct chart reading via MCP (no screenshot bottleneck), Claude Code as the interface, mechanical risk rules that Isaac sets and the system enforces, manual execution on MT5 for speed and safety, and ruthless selectivity on trade entries. The core job of Tradie Lite is to make Isaac trade **less and better** during the London/NY overlap window — that's where the money is, and that's what the whole pipeline is tuned to protect.
