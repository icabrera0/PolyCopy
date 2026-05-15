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

**API Architecture (three separate backends):**

| API | Base URL | Purpose |
|---|---|---|
| Data API | `https://data-api.polymarket.com` | Leaderboard, positions, activity |
| Gamma API | `https://gamma-api.polymarket.com` | Market metadata (category, status) |
| CLOB API | `https://clob.polymarket.com` | Live pricing (fill + unrealized PnL) |

**Verified Endpoints:**

- **Leaderboard** — Data API `GET /v1/leaderboard?category=CRYPTO&timePeriod=MONTH&orderBy=PNL&limit=100`
  - Returns: `rank`, `proxyWallet`, `userName`, `pnl`, `vol` — nothing else
  - ⚠ No win rate, trade count, or position data in this response
  - ⚠ **Pagination:** API caps at ~20 results per page; paginate with `offset=0/20/40/60/80`, verify at runtime

- **Positions** — Data API `GET /v1/positions?user={proxyWallet}`
  - Returns: `conditionId`, `asset` (token_id), `outcome`, `avgPrice`, `size`, `title`, `slug`, `endDate`
  - Does not filter by category — use Gamma API to confirm Crypto tag

- **Activity** — Data API `GET /v1/activity?user={proxyWallet}&limit=50`
  - Used to derive `last_active` date and trade frequency
  - Record count ≈ trade count for min-trades filter

- **Market metadata** — Gamma API `GET /markets?conditionId={conditionId}`
  - Confirms Crypto tag, fetches `endDate`, confirms `active: true`

- **Fill price** — CLOB API `GET /last-trade-price?token_id={token_id}`
  - Paper trade entry price; `token_id` = `asset` field from positions response

- **Current price** — CLOB API `GET /price?token_id={token_id}&side=BUY`
  - Unrealized PnL tracking on open trades

**Key functions:**
- `get_top_traders(category: str, limit: int) -> list[Trader]`
  - Calls Data API leaderboard with automatic pagination (offsets 0/20/40/60/80)
  - Returns traders sorted by monthly PnL; fields captured: `proxy_wallet`, `username`, `pnl`, `vol`

- `get_active_positions(proxy_wallet: str) -> list[Position]`
  - Calls Data API `GET /v1/positions?user={proxyWallet}`
  - Position fields include `token_id` (from `asset`) needed for CLOB pricing

- `get_trader_activity(proxy_wallet: str) -> list[dict]`
  - Calls Data API `GET /v1/activity?user={proxyWallet}&limit=50`
  - Record count used for min-trades filter; latest record timestamp for last-active filter

- `get_market_metadata(condition_id: str) -> Market`
  - Calls Gamma API `GET /markets?conditionId={condition_id}`
  - Confirms Crypto tag, active status, and resolution time; cached 60 seconds

- `get_fill_price(token_id: str) -> float`
  - Calls CLOB API `GET /last-trade-price?token_id={token_id}`; paper trade entry price

- `get_current_price(token_id: str) -> float`
  - Calls CLOB API `GET /price?token_id={token_id}&side=BUY`; unrealized PnL on open trades

**Notes:**
- Use `asyncio.gather` to fetch positions + activity for all traders concurrently
- Implement retry logic with exponential backoff (max 3 retries)
- Cache market metadata for 60 seconds to reduce API calls
- Respect Polymarket rate limits (add configurable delay between batches)

---

### 2. `core/filter.py` — Trader Filter & Scoring Engine

**Responsibility:** Remove noise from the top-50 list to ensure only high-quality, active signal providers are used.

**Filter criteria (all configurable via `settings.py`):**

> ⚠ Win rate is **not returned** by any Polymarket API endpoint — removed as a filter criterion.

| Filter | Data Source | Default Rule | Reason |
|---|---|---|---|
| Minimum PnL | Leaderboard `pnl` field | > $500 | Exclude marginal/noise performers |
| Minimum volume | Leaderboard `vol` field | > $1,000 | Exclude low-activity accounts |
| Activity | Activity endpoint (latest record timestamp) | Last active within 14 days | Remove inactive accounts |
| Minimum trades | Activity endpoint (record count) | ≥ 5 trades | Remove low-sample accounts |
| Open positions | Positions endpoint (record count) | ≥ 1 open position | Only follow traders currently in the market |
| PnL consistency | Derived from activity data | PnL not from a single trade > 80% of total | Detect single-trade flukes |
| Diversity | Activity data (distinct markets) | Trades across ≥ 3 different markets | Remove single-market manipulators |

**Key functions:**
- `filter_traders(traders: list[Trader]) -> list[Trader]`
  - Applies all filters above sequentially
  - Returns cleaned list with a `quality_score` (0–100) per trader

- `score_trader(trader: Trader) -> float`
  - Composite score weighting: PnL (40%), volume (25%), activity (20%), diversity (15%)

---

### 3. `core/consensus.py` — Position Consensus Engine

**Responsibility:** Determine if a meaningful majority of filtered traders hold the same position on a market, and produce a trade signal.

**Key functions:**
- `detect_consensus(positions_by_trader: dict[str, list[Position]], market_metadata=None, trader_pnl=None) -> list[Signal]`
  - Groups positions by `market_id` + `outcome`
  - Counts how many traders hold each position
  - Applies PnL-weighted scoring (primary threshold) and raw count scoring (display)
  - Returns a `Signal` when consensus threshold met and min trader floor satisfied

**Signal data model:**
```python
class Signal(BaseModel):
    market_id: str
    market_title: str
    outcome: str                      # e.g. "YES" / "NO" / "BTC UP"
    trader_count: int                 # how many traders hold this
    total_filtered_traders: int       # denominator
    raw_consensus_pct: float          # trader_count / total * 100 (display only)
    weighted_consensus_pct: float     # PnL-weighted pct (primary signal threshold)
    avg_entry_price: float            # average entry price of signal traders
    market_closes_at: datetime        # market resolution time
    signal_strength: str              # "STRONG" / "MODERATE" / "WEAK"
    generated_at: datetime
```

**Thresholds (configurable, applied to weighted_consensus_pct):**
- `STRONG`: ≥ 70% weighted consensus
- `MODERATE`: 50–69%
- `WEAK`: 35–49%
- Below 35%: no signal generated
- Minimum absolute floor: 3 traders required before any % threshold applied (`min_consensus_traders`)

**Realistic signal pool:** Given 100 top traders spread across diverse Crypto markets, expect 3–8 traders per market/outcome bucket — this is expected behavior. The weighted PnL model compensates for small sample size: the 3–8 traders in a bucket are the highest-conviction, highest-performing ones. Example: "4 of 12 active traders on this market = 33% raw, but those 4 hold 71% of total weighted PnL → STRONG signal"

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
    weighted_consensus_pct: float
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
1. fetch_top_traders()              # Data API leaderboard (paginated)
2. gather activity per trader       # Data API /v1/activity (for last_active + trade count)
3. gather positions per trader      # Data API /v1/positions (for open position count)
4. filter_traders()                 # apply 7 filters; all data now populated
5. detect_consensus()               # group by market+outcome, emit Signals
6. for each new STRONG/MODERATE signal:
   a. get_market_metadata()         # Gamma API — confirm Crypto tag + active
   b. get_fill_price()              # CLOB API — entry price for paper trade
   c. check dedup (market+outcome already open?) → skip if yes
   d. open_trade()
   e. send discord notification (TRADE OPENED)
7. check_and_close_expired_trades()
   a. get_current_price()           # CLOB API — for PnL calculation
   b. for each newly closed trade → send discord notification (TRADE CLOSED)
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
# Polymarket APIs
POLYMARKET_DATA_API=https://data-api.polymarket.com
POLYMARKET_GAMMA_API=https://gamma-api.polymarket.com
POLYMARKET_CLOB_API=https://clob.polymarket.com
TRADER_CATEGORY=CRYPTO
TOP_TRADERS_LIMIT=100
POLLING_INTERVAL_SECONDS=30

# Filtering (win rate removed — not available from any API)
MIN_PNL=500.0
MIN_VOL=1000.0
MIN_TRADES=5
MIN_OPEN_POSITIONS=1
MAX_SINGLE_TRADE_PNL_RATIO=0.80
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

*Spec version: 2.0 — API architecture corrected with verified endpoints (2026-05-14)*
