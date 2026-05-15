from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from data.models import DailyStats, Market, PaperTrade, Signal, Trader

_CREATE_TRADERS = """
CREATE TABLE IF NOT EXISTS traders (
    address TEXT PRIMARY KEY,
    username TEXT,
    total_pnl_30d REAL DEFAULT 0,
    num_trades_30d INTEGER DEFAULT 0,
    last_active_timestamp TEXT,
    win_rate REAL DEFAULT 0,
    avg_position_size REAL DEFAULT 0,
    quality_score REAL DEFAULT 0,
    first_trade_timestamp TEXT,
    num_markets_traded INTEGER DEFAULT 0,
    max_single_trade_pnl REAL DEFAULT 0,
    updated_at TEXT
)
"""

_CREATE_SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL,
    market_title TEXT,
    outcome TEXT,
    trader_count INTEGER,
    total_filtered_traders INTEGER,
    raw_consensus_pct REAL,
    weighted_consensus_pct REAL,
    avg_entry_price REAL,
    market_closes_at TEXT,
    signal_strength TEXT,
    generated_at TEXT
)
"""

_CREATE_PAPER_TRADES = """
CREATE TABLE IF NOT EXISTS paper_trades (
    id TEXT PRIMARY KEY,
    market_id TEXT NOT NULL,
    market_title TEXT,
    outcome TEXT,
    entry_price REAL,
    stake REAL,
    signal_strength TEXT,
    weighted_consensus_pct REAL,
    trader_count INTEGER,
    status TEXT DEFAULT 'OPEN',
    opened_at TEXT,
    closed_at TEXT,
    resolution TEXT,
    pnl REAL,
    exit_price REAL
)
"""

_CREATE_MARKET_CACHE = """
CREATE TABLE IF NOT EXISTS market_cache (
    market_id TEXT PRIMARY KEY,
    title TEXT,
    closes_at TEXT,
    current_price REAL,
    liquidity REAL,
    cached_at TEXT
)
"""

_CREATE_DAILY_STATS = """
CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    trades_opened INTEGER DEFAULT 0,
    trades_closed INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    total_pnl REAL DEFAULT 0,
    win_rate REAL DEFAULT 0,
    strong_win_rate REAL DEFAULT 0,
    moderate_win_rate REAL DEFAULT 0
)
"""


async def init_db(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(_CREATE_TRADERS)
        await db.execute(_CREATE_SIGNALS)
        await db.execute(_CREATE_PAPER_TRADES)
        await db.execute(_CREATE_MARKET_CACHE)
        await db.execute(_CREATE_DAILY_STATS)
        await db.commit()


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s)


# ── Traders ──────────────────────────────────────────────────────────────────

async def upsert_traders(db_path: str | Path, traders: list[Trader]) -> None:
    now = _iso(datetime.now(timezone.utc))
    async with aiosqlite.connect(db_path) as db:
        for t in traders:
            await db.execute(
                """
                INSERT INTO traders VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(address) DO UPDATE SET
                    username=excluded.username,
                    total_pnl_30d=excluded.total_pnl_30d,
                    num_trades_30d=excluded.num_trades_30d,
                    last_active_timestamp=excluded.last_active_timestamp,
                    win_rate=excluded.win_rate,
                    avg_position_size=excluded.avg_position_size,
                    quality_score=excluded.quality_score,
                    first_trade_timestamp=excluded.first_trade_timestamp,
                    num_markets_traded=excluded.num_markets_traded,
                    max_single_trade_pnl=excluded.max_single_trade_pnl,
                    updated_at=excluded.updated_at
                """,
                (
                    t.address, t.username, t.total_pnl_30d, t.num_trades_30d,
                    _iso(t.last_active_timestamp), t.win_rate, t.avg_position_size,
                    t.quality_score, _iso(t.first_trade_timestamp),
                    t.num_markets_traded, t.max_single_trade_pnl, now,
                ),
            )
        await db.commit()


async def get_traders(db_path: str | Path) -> list[Trader]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM traders ORDER BY quality_score DESC") as cur:
            rows = await cur.fetchall()
    return [
        Trader(
            address=r["address"], username=r["username"],
            total_pnl_30d=r["total_pnl_30d"], num_trades_30d=r["num_trades_30d"],
            last_active_timestamp=_parse_dt(r["last_active_timestamp"]) or datetime.now(timezone.utc),
            win_rate=r["win_rate"], avg_position_size=r["avg_position_size"],
            quality_score=r["quality_score"],
            first_trade_timestamp=_parse_dt(r["first_trade_timestamp"]),
            num_markets_traded=r["num_markets_traded"],
            max_single_trade_pnl=r["max_single_trade_pnl"],
        )
        for r in rows
    ]


# ── Signals ───────────────────────────────────────────────────────────────────

async def insert_signal(db_path: str | Path, signal: Signal) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                signal.id, signal.market_id, signal.market_title, signal.outcome,
                signal.trader_count, signal.total_filtered_traders,
                signal.raw_consensus_pct, signal.weighted_consensus_pct,
                signal.avg_entry_price, _iso(signal.market_closes_at),
                signal.signal_strength, _iso(signal.generated_at),
            ),
        )
        await db.commit()


async def get_recent_signals(db_path: str | Path, limit: int = 50) -> list[Signal]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM signals ORDER BY generated_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [
        Signal(
            id=r["id"], market_id=r["market_id"], market_title=r["market_title"],
            outcome=r["outcome"], trader_count=r["trader_count"],
            total_filtered_traders=r["total_filtered_traders"],
            raw_consensus_pct=r["raw_consensus_pct"],
            weighted_consensus_pct=r["weighted_consensus_pct"],
            avg_entry_price=r["avg_entry_price"],
            market_closes_at=_parse_dt(r["market_closes_at"]) or datetime.now(timezone.utc),
            signal_strength=r["signal_strength"],
            generated_at=_parse_dt(r["generated_at"]) or datetime.now(timezone.utc),
        )
        for r in rows
    ]


# ── Paper Trades ──────────────────────────────────────────────────────────────

async def open_trade(db_path: str | Path, trade: PaperTrade) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO paper_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                trade.id, trade.market_id, trade.market_title, trade.outcome,
                trade.entry_price, trade.stake, trade.signal_strength,
                trade.weighted_consensus_pct, trade.trader_count, trade.status,
                _iso(trade.opened_at), _iso(trade.closed_at),
                trade.resolution, trade.pnl, trade.exit_price,
            ),
        )
        await db.commit()


async def close_trade(
    db_path: str | Path,
    trade_id: str,
    resolution: str,
    exit_price: float,
    pnl: float,
) -> None:
    now = _iso(datetime.now(timezone.utc))
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            UPDATE paper_trades
            SET status='CLOSED', closed_at=?, resolution=?, exit_price=?, pnl=?
            WHERE id=?
            """,
            (now, resolution, exit_price, pnl, trade_id),
        )
        await db.commit()


async def expire_trade(db_path: str | Path, trade_id: str) -> None:
    now = _iso(datetime.now(timezone.utc))
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "UPDATE paper_trades SET status='EXPIRED', closed_at=?, resolution='N/A' WHERE id=?",
            (now, trade_id),
        )
        await db.commit()


async def get_open_trades(db_path: str | Path) -> list[PaperTrade]:
    return await _get_trades(db_path, "WHERE status='OPEN'")


async def get_all_trades(db_path: str | Path, limit: int = 200) -> list[PaperTrade]:
    return await _get_trades(db_path, f"ORDER BY opened_at DESC LIMIT {limit}")


async def trade_exists(db_path: str | Path, market_id: str, outcome: str) -> bool:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT 1 FROM paper_trades WHERE market_id=? AND outcome=? AND status='OPEN'",
            (market_id, outcome),
        ) as cur:
            return await cur.fetchone() is not None


async def _get_trades(db_path: str | Path, clause: str) -> list[PaperTrade]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(f"SELECT * FROM paper_trades {clause}") as cur:
            rows = await cur.fetchall()
    return [_row_to_trade(r) for r in rows]


def _row_to_trade(r: Any) -> PaperTrade:
    return PaperTrade(
        id=r["id"], market_id=r["market_id"], market_title=r["market_title"],
        outcome=r["outcome"], entry_price=r["entry_price"], stake=r["stake"],
        signal_strength=r["signal_strength"], weighted_consensus_pct=r["weighted_consensus_pct"],
        trader_count=r["trader_count"], status=r["status"],
        opened_at=_parse_dt(r["opened_at"]) or datetime.now(timezone.utc),
        closed_at=_parse_dt(r["closed_at"]),
        resolution=r["resolution"], pnl=r["pnl"], exit_price=r["exit_price"],
    )


# ── Market Cache ──────────────────────────────────────────────────────────────

async def cache_market(db_path: str | Path, market: Market) -> None:
    now = _iso(datetime.now(timezone.utc))
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO market_cache VALUES (?,?,?,?,?,?)
            ON CONFLICT(market_id) DO UPDATE SET
                title=excluded.title, closes_at=excluded.closes_at,
                current_price=excluded.current_price, liquidity=excluded.liquidity,
                cached_at=excluded.cached_at
            """,
            (market.market_id, market.title, _iso(market.closes_at),
             market.current_price, market.liquidity, now),
        )
        await db.commit()


# ── Daily Stats ───────────────────────────────────────────────────────────────

async def upsert_daily_stats(db_path: str | Path, stats: DailyStats) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO daily_stats VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(date) DO UPDATE SET
                trades_opened=excluded.trades_opened,
                trades_closed=excluded.trades_closed,
                wins=excluded.wins, losses=excluded.losses,
                total_pnl=excluded.total_pnl, win_rate=excluded.win_rate,
                strong_win_rate=excluded.strong_win_rate,
                moderate_win_rate=excluded.moderate_win_rate
            """,
            (
                stats.date, stats.trades_opened, stats.trades_closed,
                stats.wins, stats.losses, stats.total_pnl,
                stats.win_rate, stats.strong_win_rate, stats.moderate_win_rate,
            ),
        )
        await db.commit()


async def get_daily_stats(db_path: str | Path, limit: int = 30) -> list[DailyStats]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM daily_stats ORDER BY date DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [
        DailyStats(
            date=r["date"], trades_opened=r["trades_opened"],
            trades_closed=r["trades_closed"], wins=r["wins"], losses=r["losses"],
            total_pnl=r["total_pnl"], win_rate=r["win_rate"],
            strong_win_rate=r["strong_win_rate"], moderate_win_rate=r["moderate_win_rate"],
        )
        for r in rows
    ]
