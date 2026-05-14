# PolyCopy — Development Status

_Last updated: 2026-05-14 — update this file after every significant change._

---

## Overall Progress

**Phase:** Paper Trading (Weeks 1–4)
**Status:** ~55% complete — core data/fetch/filter layer done, consensus/trade/scheduler/dashboard pending.

---

## Module Status

| Module | File | Status | Notes |
|--------|------|--------|-------|
| Config | `config/settings.py` | ✅ Done | pydantic-settings, all .env vars |
| Data Models | `data/models.py` | ✅ Done | Trader, Position, Market, Signal, PaperTrade, DailyStats |
| Database | `data/db.py` | ✅ Done | aiosqlite, all 5 tables, full CRUD |
| Fetcher | `core/fetcher.py` | ✅ Done | async httpx, retry/backoff, 60s cache, concurrent gather |
| Filter | `core/filter.py` | ✅ Done | 7 filters, composite scoring |
| Consensus | `core/consensus.py` | ⏳ Pending | detect_consensus, Signal generation, thresholds |
| Trader | `core/trader.py` | ⏳ Pending | open/close PaperTrade, dedup check, expiry |
| Scheduler | `core/scheduler.py` | ⏳ Pending | APScheduler pipeline loop |
| Discord | `notifications/discord_webhook.py` | ⏳ Pending | embeds for open/close/status/summary |
| Dashboard | `dashboard/app.py` | ⏳ Pending | Streamlit 6-page UI |
| Tests | `tests/` | ⏳ Pending | pytest + pytest-asyncio |

---

## Seeds Issues

| ID | Title | Status |
|----|-------|--------|
| PolyCopy-780d | Build project scaffold and config layer | ✅ Merged |
| PolyCopy-0b41 | Build data models and database layer | ✅ Merged |
| PolyCopy-2be9 | Build core fetcher and filter modules | ✅ Merged |
| PolyCopy-c6f1 | Build consensus engine and trader execution | 🔄 In Progress |
| PolyCopy-d6ac | Build scheduler, Discord notifier, and Streamlit dashboard | 🔄 In Progress |
| PolyCopy-4cde | Build test suite | ⏳ Open |
| PolyCopy-8922 | Create and maintain status.md | 🔄 In Progress |

---

## Git State

- **Branch:** `master`
- **Latest commit:** `fix(data): restore models.py after bad AI merge resolution`
- **Active worktrees (stale, no new commits):**
  - `overstory/builder-consensus/PolyCopy-c6f1`
  - `overstory/builder-scheduler/PolyCopy-d6ac`
  - `overstory/builder-status/PolyCopy-8922`

---

## Overstory / Tooling Notes

- **Path bug fixed:** patched `manager.ts` line 101 — Windows backslash vs forward-slash path comparison
- **Quality gates:** updated `config.yaml` from `bun test` → `pytest tests/ -v --asyncio-mode=auto -x -q`
- **AI merge issue:** overstory AI resolver wrote meta-text into `data/models.py` — fixed manually; avoid `ov merge` with AI resolve on Python files
- **Coordinator tmux:** does not start on this machine — using `ov sling` directly as coordinator instead
- **Headless mode:** `claudeHeadlessByDefault: true` works; builders write code but fail to commit because old overlays hardcode `bun test` quality gates

---

## Next Steps (to resume this session)

1. Implement `core/consensus.py` — detect_consensus, Signal, thresholds STRONG/MODERATE/WEAK
2. Implement `core/trader.py` — open_trade, close_trade, check_and_close_expired_trades
3. Implement `core/scheduler.py` — APScheduler pipeline loop every 30s
4. Implement `notifications/discord_webhook.py` — Discord embeds
5. Implement `dashboard/app.py` — Streamlit 6-page dashboard
6. Write tests in `tests/`
7. Install dependencies: `pip install -r requirements.txt` and verify `python -m core.scheduler` starts

---

## Environment

- **OS:** Windows 11 / Git Bash (MSYS2)
- **Python:** 3.11+
- **Working dir:** `E:\AI\PolyCopy`
- **DB path:** `./data/polymarket_bot.db` (created at runtime)
- **Discord webhook:** set `DISCORD_WEBHOOK_URL` in `.env`
