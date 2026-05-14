# Polymarket Copy-Trading Bot — Project Specification

## Overview

A Python-based paper trading bot that monitors the top 50 most profitable Polymarket traders in the Crypto category, filters out noise (inactive/smurf accounts), detects consensus positions, and automatically copies trades. Includes a Discord webhook notification system and a Streamlit dashboard for visual monitoring.

---

## Project Structure

```
polymarket-bot/
├── core/
│   ├── fetcher.py            # Polymarket API data fetching
│   ├── filter.py             # Trader filtering & scoring
│   ├── consensus.py          # Position consensus engine
│   ├── trader.py             # Paper trade execution logic
│   └── scheduler.py          # Trade polling loop & timing
├── notifications/
│   └── discord_webhook.py    # Discord notification dispatcher
├── dashboard/
│   └── app.py                # Streamlit UI
├── data/
│   ├── db.py                 # SQLite database interface
│   └── models.py             # Data models / schemas
├── config/
│   └── settings.py           # Environment config (loaded from .env)
├── tests/
│   └── ...                   # Unit tests per module
├── .env.example
├── requirements.txt
├── README.md
└── spec.md                   # This file
```

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.11+ | Core runtime |
| API Client | `httpx` (async) | Non-blocking HTTP requests to Polymarket |
| Scheduling | `APScheduler` | Periodic polling (configurable interval, default 30s) |
| Concurrency | `asyncio` + `asyncio.gather` | Parallel fetching of trader positions |
| Database | `SQLite` via `aiosqlite` | Local persistence for trades, traders, signals |
| ORM / Schemas | `pydantic` v2 | Data validation and typed models |
| Notifications | Discord Webhooks (`httpx`) | Trade open/close alerts |
| Dashboard | `Streamlit` | Visual UI |
| Charting | `plotly` | Interactive charts inside Streamlit |
| Config | `python-dotenv` | Environment variable management |
| Logging | `loguru` | Structured logging to file + stdout |
| Testing | `pytest` + `pytest-asyncio` | Unit and integration tests |

---

## Module Specifications

---

### 1. `core/fetcher.py` — Polymarket Data Fetcher

**Responsibility:** Fetch leaderboard and active positions from the Polymarket API.

**Key functions:**
- `get_top_traders(category: str, limit: int) -> list[Trader]`
  - Hits the Polymarket Leaderboard API (CLOB or Gamma API)
  - Filters by category: `"Crypto"`
  - Returns top N traders sorted by 30-day profit (PnL)
  - Fields to capture per trader: `address`, `username`, `total_pnl_30d`, `num_trades_30d`, `last_active_timestamp`, `win_rate`, `avg_position_size`

- `get_active_positions(trader_address: str) -> list[Position]`
  - Fetches currently open positions for a given wallet address
  - Fields: `market_id`, `market_title`, `outcome`, `size`, `entry_price`, `timestamp_opened`

- `get_market_metadata(market_id: str) -> Market`
  - Fetches market resolution time, current price, and liquidity

**Notes:**
- Use `asyncio.gather` to fetch all 50 traders' positions concurrently
- Implement retry logic with exponential backoff (max 3 retries)
- Cache market metadata for 60 seconds to reduce API calls
- Respect Polymarket rate limits (add configurable delay between batches)

---

### 2. `core/filter.py` — Trader Filter & Scoring Engine

**Responsibility:** Remove noise from the top-50 list to ensure only high-quality, active signal providers are used.

**Filter criteria (all configurable via `settings.py`):**

| Filter | Default Rule | Reason |
|---|---|---|
| Activity | Last trade within 14 days | Remove inactive accounts |
| Minimum trades | ≥ 10 trades in last 30 days | Remove low-sample accounts |
| Position size | Avg position > $50 (notional) | Remove dust/smurf accounts |
| Win rate floor | Win rate ≥ 40% | Remove lucky outliers with 1 big win |
| PnL consistency | PnL not from a single trade > 80% of total | Detect single-trade flukes |
| Account age | Wallet first trade > 30 days ago | Remove freshly created smurf wallets |
| Diversity | Trades across ≥ 3 different markets | Remove single-market manipulators |

**Key functions:**
- `filter_traders(traders: list[Trader]) -> list[Trader]`
  - Applies all filters above sequentially
  - Returns cleaned list with a `quality_score` (0–100) per trader

- `score_trader(trader: Trader) -> float`
  - Composite score weighting: PnL (40%), win rate (25%), activity (20%), diversity (15%)

---

### 3. `core/consensus.py` — Position Consensus Engine

**Responsibility:** Determine if a meaningful majority of filtered traders hold the same position on a market, and produce a trade signal.

**Key functions:**
- `detect_consensus(positions_by_trader: dict[str, list[Position]]) -> list[Signal]`
  - Groups positions by `market_id` + `outcome`
  - Counts how many traders hold each position
  - Returns a `Signal` when consensus threshold is met

**Signal data model:**
```python
class Signal(BaseModel):
    market_id: str
    market_title: str
    outcome: str                  # e.g. "YES" / "NO" / "BTC UP"
    trader_count: int             # how many traders hold this
    total_filtered_traders: int   # denominator
    consensus_pct: float          # trader_count / total * 100
    avg_entry_price: float        # average entry price of signal traders
    market_closes_at: datetime    # market resolution time
    signal_strength: str          # "STRONG" / "MODERATE" / "WEAK"
    generated_at: datetime
```

**Thresholds (configurable):**
- `STRONG`: ≥ 70% of filtered traders agree
- `MODERATE`: 50–69%
- `WEAK`: 35–49%
- Below 35%: no signal generated

**Time-window guard:**
- Skip any market resolving in < 2 minutes (too late to enter)
- Skip any market resolving in > 24 hours (configurable max horizon)

---

### 4. `core/trader.py` — Paper Trade Execution Engine

**Responsibility:** Execute simulated trades based on signals, manage open positions, and close them when markets resolve.

**Paper trade logic:**
- All trades are virtual (no real money)
- Each paper trade gets a fixed stake per trade (configurable, default `$100` virtual)
- Track: entry price, entry time, outcome, resolution price, PnL

**Key functions:**
- `open_trade(signal: Signal) -> PaperTrade`
  - Records the trade to DB with status `OPEN`
  - Uses `avg_entry_price` from signal as entry

- `close_trade(trade_id: str, resolution: str, resolution_price: float) -> PaperTrade`
  - Marks trade as `CLOSED`
  - Calculates PnL based on paper stake and price movement

- `get_open_trades() -> list[PaperTrade]`

- `check_and_close_expired_trades()`
  - Polls markets with open trades
  - Closes any that have resolved

**PaperTrade data model:**
```python
class PaperTrade(BaseModel):
    id: str
    market_id: str
    market_title: str
    outcome: str
    entry_price: float
    stake: float                  # virtual dollars
    signal_strength: str
    consensus_pct: float
    trader_count: int
    status: Literal["OPEN", "CLOSED", "EXPIRED"]
    opened_at: datetime
    closed_at: datetime | None
    resolution: str | None        # "WIN" / "LOSS" / "N/A"
    pnl: float | None
    exit_price: float | None
```

---

### 5. `core/scheduler.py` — Polling Loop & Orchestrator

**Responsibility:** Orchestrate the full pipeline on a timed interval with minimal latency.

**Pipeline (runs every N seconds, default 30s):**
```
1. fetch_top_traders()
2. filter_traders()
3. gather all active positions concurrently (asyncio.gather)
4. detect_consensus()
5. for each new STRONG/MODERATE signal:
   a. check if already have open trade on same market+outcome → skip if yes
   b. open_trade()
   c. send discord notification (TRADE OPENED)
6. check_and_close_expired_trades()
   a. for each newly closed trade → send discord notification (TRADE CLOSED)
```

**Performance targets:**
- Full pipeline execution target: < 5 seconds end-to-end
- Concurrent position fetching must use async HTTP (not threading)
- Deduplication check before opening any trade (avoid double entries)

---

### 6. `notifications/discord_webhook.py` — Discord Notifier

**Responsibility:** Send formatted embed messages to a Discord channel via webhook.

**Notification types:**

**TRADE OPENED embed:**
- Color: Green (`0x00ff88`)
- Fields: Market title, outcome, consensus %, number of traders agreeing, signal strength, entry price, virtual stake, market closes at

**TRADE CLOSED embed:**
- Color: Green (win) or Red (loss) or Grey (expired/void)
- Fields: Market title, outcome, result (WIN/LOSS), entry price, exit price, PnL ($), PnL (%), duration held

**BOT STATUS embeds (optional):**
- Bot started / stopped
- Pipeline error alerts
- Daily summary (total paper PnL, win rate, trades today)

**Key functions:**
- `send_trade_opened(trade: PaperTrade)`
- `send_trade_closed(trade: PaperTrade)`
- `send_bot_status(status: str, message: str)`
- `send_daily_summary(stats: DailyStats)`

---

### 7. `data/db.py` — Database Layer

**Responsibility:** Persist all data using SQLite via `aiosqlite`.

**Tables:**

```sql
traders          -- cached filtered trader list + scores
signals          -- all generated signals (with or without trade)
paper_trades     -- all paper trades (open and closed)
market_cache     -- cached market metadata (TTL-based)
daily_stats      -- aggregated daily performance stats
```

**Key operations:**
- Upsert traders on each fetch cycle
- Insert signals with dedup check
- Full CRUD for paper trades
- Query helpers for dashboard (trades by date, win rate, PnL curve)

---

### 8. `dashboard/app.py` — Streamlit Dashboard

**Responsibility:** Real-time visual monitoring of bot performance and active positions.

**Pages / Sections:**

#### 📊 Overview
- Total paper PnL (all time)
- Win rate %
- Total trades opened / closed
- Active open trades count
- PnL curve chart (cumulative, plotly line chart)
- Daily PnL bar chart

#### 🔴 Live Signals (auto-refresh every 30s)
- Table of latest signals with: market, outcome, consensus %, trader count, signal strength
- Color-coded by signal strength

#### 📂 Open Trades
- Table: market, outcome, entry price, current price (live fetch), unrealized PnL, time open, signal strength

#### ✅ Trade History
- Filterable table: date range, win/loss, signal strength
- Per-trade detail expandable row

#### 👥 Trader Leaderboard
- Table of filtered top traders: address (truncated), quality score, 30d PnL, win rate, last active, trades/month

#### ⚙️ Settings Panel (read-only display of active config)
- Consensus threshold, polling interval, stake size, active filters

**Technical notes:**
- Use `st.cache_data(ttl=30)` for DB query caching
- Use `st.rerun()` with `time.sleep` loop for live refresh
- All charts use `plotly` via `st.plotly_chart(use_container_width=True)`

---

### 9. `config/settings.py` — Configuration

All settings loaded from `.env` file:

```env
# Polymarket
POLYMARKET_API_BASE=https://clob.polymarket.com
POLYMARKET_GAMMA_API=https://gamma-api.polymarket.com
TRADER_CATEGORY=Crypto
TOP_TRADERS_LIMIT=50
POLLING_INTERVAL_SECONDS=30

# Filtering
MIN_TRADES_30D=10
MIN_AVG_POSITION_USD=50
MIN_WIN_RATE=0.40
MAX_SINGLE_TRADE_PNL_RATIO=0.80
MIN_ACCOUNT_AGE_DAYS=30
MIN_MARKET_DIVERSITY=3
LAST_ACTIVE_DAYS=14

# Consensus
CONSENSUS_STRONG_THRESHOLD=0.70
CONSENSUS_MODERATE_THRESHOLD=0.50
CONSENSUS_WEAK_THRESHOLD=0.35
MIN_MARKET_TIME_REMAINING_SECONDS=120
MAX_MARKET_HORIZON_HOURS=24

# Paper Trading
PAPER_STAKE_PER_TRADE=100.0
PAPER_CURRENCY=USD

# Discord
DISCORD_WEBHOOK_URL=
DISCORD_NOTIFY_WEAK_SIGNALS=false

# Misc
LOG_LEVEL=INFO
DB_PATH=./data/polymarket_bot.db
DASHBOARD_PORT=8501
```

---

## Data Flow Diagram

```
Polymarket API
     │
     ▼
[fetcher.py] ──── top 50 traders + positions (async, parallel)
     │
     ▼
[filter.py] ───── apply activity / smurf / quality filters
     │
     ▼
[consensus.py] ── group positions, count agreement, emit Signals
     │
     ▼
[trader.py] ────── open/close PaperTrades, calculate PnL
     │          │
     │          ▼
     │    [db.py] ── persist everything to SQLite
     │
     ▼
[discord_webhook.py] ── notify on open/close
     │
     ▼
[dashboard/app.py] ──── Streamlit reads from SQLite, displays live
```

---

## Paper Trading Phase (Weeks 1–4)

**Goal:** Validate strategy before spending real money.

**Success criteria to evaluate after 4 weeks:**
- Win rate ≥ 55% on STRONG signals
- Positive cumulative paper PnL
- Average signal → entry latency < 5 seconds
- At least 30 closed trades for statistical significance

**Metrics to track:**
- Win rate by signal strength (STRONG / MODERATE / WEAK)
- Win rate by time-to-market-resolution bucket (< 1h, 1–6h, 6–24h)
- Win rate by consensus % bucket
- Average PnL per trade
- Drawdown curve

---

## Key Constraints & Edge Cases

- **Duplicate signals:** Never open two trades on the same `market_id + outcome` simultaneously
- **Market resolution lag:** Polymarket resolution can be delayed; mark as `EXPIRED` after 1h past resolution time with no result
- **API unavailability:** Bot must not crash; log errors and retry on next cycle
- **Smurf detection is heuristic:** The filter reduces noise but cannot guarantee 100% clean signals; thresholds must be tunable
- **Short-window markets (< 5 min):** By the time consensus is detected, entry may be impossible; the 2-minute guard handles most cases but monitor missed entries
- **Price slippage (paper trading):** Use `avg_entry_price` of signal traders as proxy; in real trading this will differ

---

## Future Considerations (Post Paper Phase)

- Real trade execution via Polymarket CLOB API (limit orders)
- Per-signal position sizing (Kelly criterion based on consensus %)
- Multi-category support (Sports, Politics, etc.)
- ML-based signal scoring layer
- Backtesting module against historical Polymarket data
- Telegram notification alternative
- Docker deployment + GitHub Actions CI

---

## Dependencies (`requirements.txt`)

```
httpx[asyncio]>=0.27
aiosqlite>=0.20
pydantic>=2.6
APScheduler>=3.10
python-dotenv>=1.0
loguru>=0.7
streamlit>=1.35
plotly>=5.20
pytest>=8.0
pytest-asyncio>=0.23
```

---

*Spec version: 1.0 — Paper trading phase*
