# PolyCopy — Development Status

_Last updated: 2026-05-14 — update this file after every significant change._

---

## Overall Progress

**Phase:** Paper Trading (Weeks 1–4)
**Status:** ~90% complete — all core modules built, only tests remain.

---

## Module Status

| Module | File | Status | Notes |
|--------|------|--------|-------|
| Config | `config/settings.py` | ✅ Done | pydantic-settings, all .env vars |
| Data Models | `data/models.py` | ✅ Done | Trader, Position, Market, Signal, PaperTrade, DailyStats |
| Database | `data/db.py` | ✅ Done | aiosqlite, all 5 tables, full CRUD |
| Fetcher | `core/fetcher.py` | ✅ Done | async httpx, retry/backoff, 60s cache, concurrent gather |
| Filter | `core/filter.py` | ✅ Done | 7 filters, composite scoring |
| Consensus | `core/consensus.py` | ✅ Done | detect_consensus, STRONG/MODERATE/WEAK, time-window guard |
| Trader | `core/trader.py` | ✅ Done | open/close PaperTrade, dedup check, expiry |
| Scheduler | `core/scheduler.py` | ✅ Done | APScheduler pipeline loop every 30s |
| Discord | `notifications/discord_webhook.py` | ✅ Done | embeds for open/close/status/daily summary |
| Dashboard | `dashboard/app.py` | ✅ Done | Streamlit 6-page UI with plotly |
| Tests | `tests/` | ⏳ Pending | pytest + pytest-asyncio (PolyCopy-4cde) |

---

## Seeds Issues

| ID | Title | Status |
|----|-------|--------|
| PolyCopy-780d | Build project scaffold and config layer | ✅ Closed |
| PolyCopy-0b41 | Build data models and database layer | ✅ Closed |
| PolyCopy-2be9 | Build core fetcher and filter modules | ✅ Closed |
| PolyCopy-c6f1 | Build consensus engine and trader execution | ✅ Closed |
| PolyCopy-d6ac | Build scheduler, Discord notifier, and Streamlit dashboard | ✅ Closed |
| PolyCopy-4cde | Build test suite | ⏳ Open — next task |
| PolyCopy-8922 | Create and maintain status.md | ✅ Closed |

---

## Git State

- **Branch:** `master`
- **Latest commit:** `feat: implement consensus, trader, scheduler, discord, dashboard, status.md`
- **Stale worktrees (nothing useful, safe to clean):**
  - `overstory/builder-consensus/PolyCopy-c6f1`
  - `overstory/builder-scheduler/PolyCopy-d6ac`
  - `overstory/builder-status/PolyCopy-8922`

---

## To Run

```bash
# Install deps
pip install -r requirements.txt

# Set env
cp .env.example .env
# Edit .env — set DISCORD_WEBHOOK_URL if desired

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

## Next Steps

1. **Write tests** — `ov sling PolyCopy-4cde --capability builder --name builder-tests --depth 1`
   - Tests for: filter.py (all 7 filters), consensus.py (thresholds, time guards), trader.py (open/close/dedup), db.py (CRUD)
2. **Verify imports** — run `python -c "from core.scheduler import main"` to catch any import errors
3. **Clean stale worktrees** — `ov worktree clean --completed`
4. **Set .env** — fill in `DISCORD_WEBHOOK_URL` and test notifications
5. **Paper trading run** — start bot and monitor for 24h

---

## Environment

- **OS:** Windows 11 / Git Bash (MSYS2)
- **Python:** 3.11+
- **Working dir:** `E:\AI\PolyCopy`
- **DB path:** `./data/polymarket_bot.db` (created at runtime by `db.init_db()`)
- **Discord webhook:** set `DISCORD_WEBHOOK_URL` in `.env`
