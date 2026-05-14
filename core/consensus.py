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
) -> list[Signal]:
    """Group positions by market+outcome, emit Signal when consensus threshold met."""
    total = len(positions_by_trader)
    if total == 0:
        return []

    # Aggregate: (market_id, outcome) -> list of entry prices
    buckets: dict[tuple[str, str], list[float]] = {}
    titles: dict[str, str] = {}

    for positions in positions_by_trader.values():
        for pos in positions:
            if pos.size <= 0:
                continue
            key = (pos.market_id, pos.outcome)
            buckets.setdefault(key, []).append(pos.entry_price)
            titles[pos.market_id] = pos.market_title

    signals: list[Signal] = []
    for (market_id, outcome), prices in buckets.items():
        count = len(prices)
        pct = count / total
        strength = _classify(pct)
        if strength is None:
            continue

        # Time-window guard using market metadata if available
        closes_at: datetime | None = None
        if market_metadata and market_id in market_metadata:
            m = market_metadata[market_id]
            closes_at = getattr(m, "closes_at", None)
        if closes_at is None:
            # Default: assume 12h from now if we have no metadata
            from datetime import timedelta
            closes_at = _now_utc() + timedelta(hours=12)

        if not _market_in_window(closes_at):
            logger.debug(f"Market {market_id} outside time window, skipping")
            continue

        avg_price = sum(prices) / len(prices)
        sig = Signal(
            market_id=market_id,
            market_title=titles.get(market_id, "Unknown"),
            outcome=outcome,
            trader_count=count,
            total_filtered_traders=total,
            consensus_pct=round(pct * 100, 2),
            avg_entry_price=round(avg_price, 6),
            market_closes_at=closes_at,
            signal_strength=strength,
        )
        signals.append(sig)
        logger.info(
            f"Signal {strength}: {sig.market_title[:40]} | {outcome} | "
            f"{count}/{total} traders ({sig.consensus_pct:.1f}%)"
        )

    return signals
