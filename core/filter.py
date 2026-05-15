from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from config.settings import settings
from data.models import Trader

_MIN_SCORE = 0.0
_MAX_SCORE = 100.0


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _days_since(dt: datetime) -> float:
    now = _now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 86400.0


def _passes_activity(trader: Trader) -> bool:
    """Last trade within last_active_days days."""
    return _days_since(trader.last_active_timestamp) <= settings.last_active_days


def _passes_min_trades(trader: Trader) -> bool:
    return trader.num_trades_30d >= settings.min_trades


def _passes_min_pnl(trader: Trader) -> bool:
    return trader.total_pnl_30d >= settings.min_pnl


def _passes_min_vol(trader: Trader) -> bool:
    return trader.vol >= settings.min_vol


def _passes_min_open_positions(trader: Trader) -> bool:
    return trader.num_open_positions >= settings.min_open_positions


def _passes_pnl_consistency(trader: Trader) -> bool:
    """No single trade dominates total PnL (avoids single-win flukes)."""
    if trader.total_pnl_30d <= 0:
        return True
    ratio = trader.max_single_trade_pnl / trader.total_pnl_30d
    return ratio <= settings.max_single_trade_pnl_ratio


def _passes_diversity(trader: Trader) -> bool:
    """Traded across at least min_market_diversity different markets."""
    return trader.num_markets_traded >= settings.min_market_diversity


_FILTERS = [
    ("activity", _passes_activity),
    ("min_trades", _passes_min_trades),
    ("min_pnl", _passes_min_pnl),
    ("min_vol", _passes_min_vol),
    ("min_open_positions", _passes_min_open_positions),
    ("pnl_consistency", _passes_pnl_consistency),
    ("diversity", _passes_diversity),
]


def filter_traders(traders: list[Trader]) -> list[Trader]:
    """Apply all filters and return traders that pass, each with a quality_score."""
    passed: list[Trader] = []
    for trader in traders:
        failed: list[str] = []
        for name, fn in _FILTERS:
            if not fn(trader):
                failed.append(name)
        if failed:
            logger.debug(f"Trader {trader.address[:8]} filtered out: {', '.join(failed)}")
            continue
        scored = trader.model_copy(update={"quality_score": score_trader(trader)})
        passed.append(scored)

    logger.info(f"filter_traders: {len(traders)} in -> {len(passed)} passed")
    return passed


def score_trader(trader: Trader) -> float:
    """Composite quality score 0–100: PnL 40%, vol 25%, activity 20%, diversity 15%."""
    pnl_ref = 10_000.0
    vol_ref = 10_000.0
    pnl_score = min(trader.total_pnl_30d / pnl_ref, 1.0) * 40.0 if trader.total_pnl_30d > 0 else 0.0
    vol_score = min(trader.vol / vol_ref, 1.0) * 25.0

    days_inactive = _days_since(trader.last_active_timestamp)
    activity_score = max(0.0, 1.0 - days_inactive / settings.last_active_days) * 20.0

    diversity_score = min(trader.num_markets_traded / 10.0, 1.0) * 15.0

    total = pnl_score + vol_score + activity_score + diversity_score
    return round(min(max(total, _MIN_SCORE), _MAX_SCORE), 2)
