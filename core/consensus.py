from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from config.settings import settings
from data.models import Position, Signal


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _classify(pct: float) -> str | None:
    if pct >= settings.consensus_strong_threshold:
        return "STRONG"
    if pct >= settings.consensus_moderate_threshold:
        return "MODERATE"
    if pct >= settings.consensus_weak_threshold:
        return "WEAK"
    return None


def _market_in_window(closes_at: datetime) -> bool:
    now = _now_utc()
    if closes_at.tzinfo is None:
        closes_at = closes_at.replace(tzinfo=timezone.utc)
    remaining = (closes_at - now).total_seconds()
    return (
        remaining >= settings.min_market_time_remaining_seconds
        and remaining <= settings.max_market_horizon_hours * 3600
    )


def detect_consensus(
    positions_by_trader: dict[str, list[Position]],
    market_metadata: dict[str, object] | None = None,
    trader_pnl: dict[str, float] | None = None,
) -> list[Signal]:
    """Group positions by market+outcome, emit Signal when consensus threshold met."""
    total = len(positions_by_trader)
    if total == 0:
        return []

    # Aggregate: (market_id, outcome) -> list of (entry_price, trader_address)
    buckets: dict[tuple[str, str], list[tuple[float, str]]] = {}
    titles: dict[str, str] = {}

    for trader_addr, positions in positions_by_trader.items():
        for pos in positions:
            if pos.size <= 0:
                continue
            key = (pos.market_id, pos.outcome)
            buckets.setdefault(key, []).append((pos.entry_price, trader_addr))
            titles[pos.market_id] = pos.market_title

    # Precompute total PnL weight across all traders in pool (negative PnL clamped to 1.0)
    all_weights = sum(
        max((trader_pnl or {}).get(addr, 1.0), 1.0)
        for addr in positions_by_trader.keys()
    )

    signals: list[Signal] = []
    for (market_id, outcome), entries in buckets.items():
        count = len(entries)

        # Absolute floor: must have min_consensus_traders before any % threshold applied
        if count < settings.min_consensus_traders:
            continue

        # Raw count-based pct (kept for display)
        raw_pct = count / total * 100

        # PnL-weighted pct (primary signal threshold)
        weighted_score = sum(
            max((trader_pnl or {}).get(addr, 1.0), 1.0)
            for _, addr in entries
        )
        weighted_pct = (weighted_score / all_weights * 100) if all_weights > 0 else 0.0

        # Threshold check uses weighted_pct converted to 0-1 fraction
        strength = _classify(weighted_pct / 100)
        if strength is None:
            continue

        # Time-window guard using market metadata if available
        closes_at: datetime | None = None
        if market_metadata and market_id in market_metadata:
            m = market_metadata[market_id]
            closes_at = getattr(m, "closes_at", None)
        if closes_at is None:
            from datetime import timedelta
            closes_at = _now_utc() + timedelta(hours=12)

        if not _market_in_window(closes_at):
            logger.debug(f"Market {market_id} outside time window, skipping")
            continue

        prices = [ep for ep, _ in entries]
        avg_price = sum(prices) / len(prices)

        sig = Signal(
            market_id=market_id,
            market_title=titles.get(market_id, "Unknown"),
            outcome=outcome,
            trader_count=count,
            total_filtered_traders=total,
            raw_consensus_pct=round(raw_pct, 2),
            weighted_consensus_pct=round(weighted_pct, 2),
            avg_entry_price=round(avg_price, 6),
            market_closes_at=closes_at,
            signal_strength=strength,
        )
        signals.append(sig)
        logger.info(
            f"Signal {strength}: {sig.market_title[:40]} | {outcome} | "
            f"{count}/{total} traders ({sig.weighted_consensus_pct:.1f}% weighted)"
        )

    return signals
