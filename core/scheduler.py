from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from config.settings import settings
from core.consensus import detect_consensus
from core.fetcher import fetch_all_activities, fetch_all_positions, get_market_metadata, get_top_traders
from core.filter import filter_traders
from core.trader import check_and_close_expired_trades, open_trade
from data import db
from notifications.discord_webhook import send_bot_status, send_trade_closed, send_trade_opened

_DB_PATH = str(settings.db_path)


async def run_pipeline() -> None:
    """Single pipeline tick: fetch → filter → consensus → trade → notify."""
    logger.debug("Pipeline tick start")
    try:
        # 1. Fetch top traders
        traders = await get_top_traders()
        if not traders:
            logger.warning("No traders fetched, skipping tick")
            return

        # 2. Enrich traders with activity data
        activities = await fetch_all_activities(traders)
        traders = [
            t.model_copy(update={k: v for k, v in {
                "last_active_timestamp": activities.get(t.address, {}).get("last_active_timestamp"),
                "num_trades_30d": activities.get(t.address, {}).get("num_trades_30d"),
                "num_markets_traded": activities.get(t.address, {}).get("num_markets_traded"),
                "num_open_positions": activities.get(t.address, {}).get("num_open_positions"),
            }.items() if v is not None})
            for t in traders
        ]

        # 3. Filter
        filtered = filter_traders(traders)
        if not filtered:
            logger.warning("No traders passed filters, skipping tick")
            return

        await db.upsert_traders(_DB_PATH, filtered)

        # 4. Gather positions concurrently
        positions_by_trader = await fetch_all_positions(filtered)

        # 5. Fetch market metadata for all unique market IDs
        market_ids = {
            pos.market_id
            for positions in positions_by_trader.values()
            for pos in positions
        }
        market_metadata = {}
        for mid in market_ids:
            m = await get_market_metadata(mid)
            if m:
                market_metadata[mid] = m

        # 6. Detect consensus
        signals = detect_consensus(positions_by_trader, market_metadata)

        for signal in signals:
            await db.insert_signal(_DB_PATH, signal)

            if signal.signal_strength not in ("STRONG", "MODERATE"):
                if not settings.discord_notify_weak_signals:
                    continue

            # 7. Open trade (dedup check inside)
            trade = await open_trade(signal, _DB_PATH)
            if trade:
                await send_trade_opened(trade)

        # 8. Check and close expired/resolved trades
        closed_trades = await check_and_close_expired_trades(_DB_PATH)
        for trade in closed_trades:
            await send_trade_closed(trade)

    except Exception as exc:
        logger.exception(f"Pipeline error: {exc}")
        await send_bot_status("error", f"Pipeline exception: {exc}")


async def main() -> None:
    logger.add(
        "logs/bot.log",
        rotation="1 day",
        retention="7 days",
        level=settings.log_level,
    )
    logger.info("PolyCopy bot starting up")

    await db.init_db(_DB_PATH)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_pipeline,
        "interval",
        seconds=settings.polling_interval_seconds,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    await send_bot_status("started", "PolyCopy bot is running")
    logger.info(
        f"Scheduler started — polling every {settings.polling_interval_seconds}s"
    )

    # Run first tick immediately
    await run_pipeline()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down")
        scheduler.shutdown()
        await send_bot_status("stopped", "PolyCopy bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
