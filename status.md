# PolyCopy — Development Status

_Last updated: 2026-05-14 — update this file after every significant change._

---

## Overall Progress

**Phase:** Paper Trading (Weeks 1–4)
**Status:** Code complete (109 tests passing). Leaderboard switched to WEEK, min_pnl lowered to $100, trader_pnl now wired into consensus (2026-05-15).

---

## Completed Task — API Refactor (PolyCopy-43de) ✅

All modules aligned to verified Polymarket API endpoints (spec v2.0). 104 tests passing.

---

## Verified API Architecture (spec v2.0)

| API | Base URL | Purpose |
|-----|----------|---------|
| Data API | `https://data-api.polymarket.com` | Leaderboard, positions, activity |
| Gamma API | `https://gamma-api.polymarket.com` | Market metadata (category, status) |
| CLOB API | `https://clob.polymarket.com` | Fill price + unrealized PnL |

### Leaderboard
```
GET https://data-api.polymarket.com/v1/leaderboard
  ?category=CRYPTO&timePeriod=MONTH&orderBy=PNL&limit=100
```
Returns: `rank`, `proxyWallet`, `userName`, `pnl`, `vol` only.
**No win rate, no trade count, no positions.**
Pagination: caps at ~20/page → paginate with offset=0,20,40,60,80.

### Positions
```
GET https://data-api.polymarket.com/v1/positions?user={proxyWallet}
```
Returns: `conditionId`, `asset` (=token_id), `outcome`, `avgPrice`, `size`, `title`, `slug`, `endDate`

### Activity
```
GET https://data-api.polymarket.com/v1/activity?user={proxyWallet}&limit=50
```
Used for: `last_active` date (latest record), trade count (record count).

### Market Metadata
```
GET https://gamma-api.polymarket.com/markets?conditionId={conditionId}
```
Used to: confirm Crypto tag, get `endDate`, confirm `active: true`.

### Fill Price
```
GET https://clob.polymarket.com/last-trade-price?token_id={token_id}
```
Paper trade entry price. `token_id` = `asset` field from positions response.

### Current Price
```
GET https://clob.polymarket.com/price?token_id={token_id}&side=BUY
```
Unrealized PnL tracking on open trades.

---

## Updated Filter Layer (spec v2.0)

Win rate removed — not available from any API.

| Filter | Source | Rule |
|--------|--------|------|
| Min PnL | Leaderboard `pnl` | > $500 |
| Min volume | Leaderboard `vol` | > $1,000 |
| Activity | Activity (latest timestamp) | Within 14 days |
| Min trades | Activity (record count) | ≥ 5 |
| Open positions | Positions (record count) | ≥ 1 |
| PnL consistency | Activity data | Single trade < 80% of total PnL |
| Diversity | Activity data | ≥ 3 distinct markets |

Scoring: PnL 40%, volume 25%, activity 20%, diversity 15%

---

## Module Status

| Module | File | Status | Notes |
|--------|------|--------|-------|
| Config | `config/settings.py` | ✅ Done | min_pnl/min_vol/min_trades/min_open_positions; three API base URLs |
| Data Models | `data/models.py` | ✅ Done | Trader has vol, num_open_positions; flexible parser |
| Database | `data/db.py` | ✅ Done | aiosqlite, all 5 tables, full CRUD |
| Fetcher | `core/fetcher.py` | ✅ Done | /v1/positions; get_trader_activity, get_fill_price, get_current_price |
| Filter | `core/filter.py` | ✅ Done | 7 filters (no win_rate/pos_size/account_age); PnL 40%/vol 25%/activity 20%/diversity 15% scoring |
| Consensus | `core/consensus.py` | ✅ Done | PnL-weighted scoring, min trader floor (3), STRONG/MODERATE/WEAK, time-window guard |
| Trader | `core/trader.py` | ✅ Done | open/close PaperTrade, dedup check, expiry |
| Scheduler | `core/scheduler.py` | ✅ Done | fetch_all_activities enriches traders before filter |
| Discord | `notifications/discord_webhook.py` | ✅ Done | embeds for open/close/status/daily summary |
| Dashboard | `dashboard/app.py` | ✅ Done | Streamlit 6-page UI with plotly |
| Tests | `tests/` | ✅ Done | 109 tests passing |

---

## Seeds Issues

| ID | Title | Status |
|----|-------|--------|
| PolyCopy-780d | Build project scaffold and config layer | ✅ Closed |
| PolyCopy-0b41 | Build data models and database layer | ✅ Closed |
| PolyCopy-2be9 | Build core fetcher and filter modules | ✅ Closed |
| PolyCopy-c6f1 | Build consensus engine and trader execution | ✅ Closed |
| PolyCopy-d6ac | Build scheduler, Discord notifier, and Streamlit dashboard | ✅ Closed |
| PolyCopy-4cde | Build test suite | ✅ Closed |
| PolyCopy-8922 | Create and maintain status.md | ✅ Closed |
| PolyCopy-43de | Refactor API layer to verified Polymarket endpoints (v2 spec) | ✅ Closed |
| PolyCopy-6795 | Weighted PnL consensus scoring | ✅ Closed |
| PolyCopy-53af | Minimum absolute trader count floor for consensus | ✅ Closed |

---

## Consensus Improvements (PolyCopy-6795 + PolyCopy-53af) ✅ 2026-05-15

Merged via `overstory/consensus-weighted-scoring/PolyCopy-6795`. 109 tests passing.

### What changed
- `Signal` model: `consensus_pct` → `raw_consensus_pct` + `weighted_consensus_pct`
- `PaperTrade` model: `consensus_pct` → `weighted_consensus_pct`
- `detect_consensus(...)` accepts optional `trader_pnl: dict[str, float]`; thresholds use weighted pct
- `min_consensus_traders = 3` added to settings; blocks signals with < 3 traders regardless of %
- Negative PnL traders clamped to weight 1.0 (never drag weighted score negative)
- `spec.md` updated with realistic 3–8 trader pool explanation

## After PolyCopy-43de Completes (DONE ✅)

---

## Git State

- **Branch:** `master`
- **Latest commit:** `feat: implement consensus, trader, scheduler, discord, dashboard, status.md`

---

## To Run (post-refactor)

```bash
# Install deps
pip install -r requirements.txt

# Set env
cp .env.example .env
# Required .env vars (v2.0):
#   POLYMARKET_DATA_API=https://data-api.polymarket.com
#   POLYMARKET_GAMMA_API=https://gamma-api.polymarket.com
#   POLYMARKET_CLOB_API=https://clob.polymarket.com
#   DISCORD_WEBHOOK_URL=<your webhook>

# Run bot
python -m core.scheduler

# Run dashboard (separate terminal)
streamlit run dashboard/app.py --server.port 8501

# Run tests
pytest tests/ -v --asyncio-mode=auto
```

---

## Overstory / Tooling Notes

- **Path bug fixed:** patched `manager.ts` line 101 — Windows backslash vs forward-slash path comparison
- **Quality gates:** updated `config.yaml` from `bun test` → `pytest tests/ -v --asyncio-mode=auto -x -q`
- **AI merge issue:** overstory AI resolver wrote meta-text into `data/models.py` — fixed manually; be careful with `ov merge` AI resolve on Python files
- **Coordinator tmux:** does not start on this machine — using `ov sling` directly as coordinator instead
- **Headless mode:** `claudeHeadlessByDefault: true` works; builders write code but old overlays hardcode `bun test` quality gates so they fail to commit — workaround: commit manually after sling

---

## Environment

- **OS:** Windows 11 / Git Bash (MSYS2)
- **Python:** 3.11+
- **Working dir:** `E:\AI\PolyCopy`
- **DB path:** `./data/polymarket_bot.db` (created at runtime by `db.init_db()`)
- **Discord webhook:** set `DISCORD_WEBHOOK_URL` in `.env`
