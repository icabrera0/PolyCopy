from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger

from config.settings import settings
from core.fetcher import get_market_metadata
from data import db
from data.models import PaperTrade, Signal


async def open_trade(signal: Signal, db_path: str) -> PaperTrade | None:
    """Open a paper trade for a signal. Returns None if duplicate exists."""
    if await db.trade_exists(db_path, signal.market_id, signal.outcome):
        logger.debug(f"Duplicate trade skipped: {signal.market_id} {signal.outcome}")
        return None

    trade = PaperTrade(
        market_id=signal.market_id,
        market_title=signal.market_title,
        outcome=signal.outcome,
        entry_price=signal.avg_entry_price,
        stake=settings.paper_stake_per_trade,
        signal_strength=signal.signal_strength,
        weighted_consensus_pct=signal.weighted_consensus_pct,
        trader_count=signal.trader_count,
    )
    await db.open_trade(db_path, trade)
    logger.info(
        f"Trade opened: {trade.market_title[:40]} | {trade.outcome} | "
        f"entry={trade.entry_price:.4f} stake=${trade.stake}"
    )
    return trade


async def close_trade(
    trade: PaperTrade,
    resolution: str,
    exit_price: float,
    db_path: str,
) -> PaperTrade:
    """Close a paper trade and calculate PnL."""
    if resolution == "WIN":
        pnl = trade.stake * (exit_price - trade.entry_price) / trade.entry_price
    elif resolution == "LOSS":
        pnl = -trade.stake
    else:
        pnl = 0.0

    await db.close_trade(db_path, trade.id, resolution, exit_price, round(pnl, 2))
    updated = trade.model_copy(
        update={
            "status": "CLOSED",
            "closed_at": datetime.now(timezone.utc),
            "resolution": resolution,
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
        }
    )
    logger.info(
        f"Trade closed: {trade.market_title[:40]} | {resolution} | "
        f"pnl=${pnl:+.2f}"
    )
    return updated


async def check_and_close_expired_trades(db_path: str) -> list[PaperTrade]:
    """Check open trades; close resolved markets, expire stale ones."""
    open_trades = await db.get_open_trades(db_path)
    closed: list[PaperTrade] = []
    now = datetime.now(timezone.utc)

    for trade in open_trades:
        market = await get_market_metadata(trade.market_id)

        if market is None:
            closes_at = trade.opened_at + timedelta(hours=25)
        else:
            closes_at = market.closes_at
            if closes_at.tzinfo is None:
                closes_at = closes_at.replace(tzinfo=timezone.utc)

        # Expire if 1h past expected resolution with no result
        if now > closes_at + timedelta(hours=1):
            await db.expire_trade(db_path, trade.id)
            expired = trade.model_copy(update={"status": "EXPIRED"})
            closed.append(expired)
            logger.info(f"Trade expired: {trade.market_title[:40]}")
            continue

        # Check if market resolved via current_price reaching 0 or 1
        if market and market.current_price is not None:
            price = market.current_price
            if price >= 0.99:
                resolution = "WIN" if trade.outcome == "YES" else "LOSS"
                updated = await close_trade(trade, resolution, price, db_path)
                closed.append(updated)
            elif price <= 0.01:
                resolution = "LOSS" if trade.outcome == "YES" else "WIN"
                updated = await close_trade(trade, resolution, price, db_path)
                closed.append(updated)

    return closed
