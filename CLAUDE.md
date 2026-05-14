# PolyCopy — Polymarket Copy-Trading Bot

## Project Overview

Python-based paper trading bot that monitors the top 50 most profitable Polymarket traders in the Crypto category, filters smurf/inactive accounts, detects consensus positions, and automatically copies trades. Includes Discord webhook notifications and a Streamlit dashboard.

## Architecture

```
core/           # Fetch → Filter → Consensus → Trade pipeline
notifications/  # Discord webhook dispatcher
dashboard/      # Streamlit UI (reads SQLite)
data/           # SQLite via aiosqlite, Pydantic models
config/         # .env-driven settings
tests/          # pytest + pytest-asyncio
```

## Stack

- **Runtime:** Python 3.11+
- **HTTP:** `httpx` (async)
- **Scheduling:** `APScheduler`
- **Concurrency:** `asyncio` + `asyncio.gather`
- **DB:** SQLite via `aiosqlite`
- **Models:** `pydantic` v2
- **Dashboard:** `Streamlit` + `plotly`
- **Config:** `python-dotenv`
- **Logging:** `loguru`
- **Testing:** `pytest` + `pytest-asyncio`

## Pipeline (runs every 30s)

1. `fetcher.py` — fetch top 50 traders + active positions (async parallel)
2. `filter.py` — activity / smurf / quality filters → `quality_score`
3. `consensus.py` — group by market+outcome, emit `Signal` when threshold met
4. `trader.py` — open/close `PaperTrade` records in SQLite
5. `discord_webhook.py` — notify on open/close
6. `dashboard/app.py` — Streamlit reads SQLite, live-refreshes every 30s

## Key Rules

- Never open two trades on the same `market_id + outcome` simultaneously (dedup check before `open_trade`)
- Skip markets resolving in < 2 min or > 24h
- All HTTP must be async (`httpx`); no `requests` or threading for I/O
- Retry with exponential backoff (max 3) on API failures; log and continue, never crash the loop
- Signal thresholds: STRONG ≥ 70%, MODERATE 50–69%, WEAK 35–49%; only STRONG/MODERATE trigger trades by default

## Configuration

All config lives in `.env` (see `.env.example`). Settings are loaded via `config/settings.py` using `python-dotenv`. Never hardcode API URLs, thresholds, or secrets.

## Testing

```bash
pytest tests/ -v
pytest tests/ -v --asyncio-mode=auto   # for async tests
```

## Running

```bash
# Bot
python -m core.scheduler

# Dashboard
streamlit run dashboard/app.py --server.port 8501
```

## Current Phase

**Paper trading (Weeks 1–4).** No real money. Success criteria: ≥ 55% win rate on STRONG signals, positive cumulative paper PnL, ≥ 30 closed trades.

## Spec

Full specification in `spec.md`.
