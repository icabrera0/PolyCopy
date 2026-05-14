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
    """At least min_trades_30d trades in last 30 days."""
    return trader.num_trades_30d >= settings.min_trades_30d


def _passes_position_size(trader: Trader) -> bool:
    """Average position size above min_avg_position_usd."""
    return trader.avg_position_size >= settings.min_avg_position_usd


def _passes_win_rate(trader: Trader) -> bool:
    """Win rate at or above min_win_rate floor."""
    return trader.win_rate >= settings.min_win_rate


def _passes_pnl_consistency(trader: Trader) -> bool:
    """No single trade dominates total PnL (avoids single-win flukes)."""
    if trader.total_pnl_30d <= 0:
        return True
    ratio = trader.max_single_trade_pnl / trader.total_pnl_30d
    return ratio <= settings.max_single_trade_pnl_ratio


def _passes_account_age(trader: Trader) -> bool:
    """Wallet first trade must be at least min_account_age_days ago."""
    if trader.first_trade_timestamp is None:
        return False
    return _days_since(trader.first_trade_timestamp) >= settings.min_account_age_days


def _passes_diversity(trader: Trader) -> bool:
    """Traded across at least min_market_diversity different markets."""
    return trader.num_markets_traded >= settings.min_market_diversity


_FILTERS = [
    ("activity", _passes_activity),
    ("min_trades", _passes_min_trades),
    ("position_size", _passes_position_size),
    ("win_rate", _passes_win_rate),
    ("pnl_consistency", _passes_pnl_consistency),
    ("account_age", _passes_account_age),
    ("diversity", _passes_diversity),
]


def filter_traders(traders: list[Trader]) -> list[Trader]:
    """Apply all 7 filters and return traders that pass, each with a quality_score."""
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
    """Composite quality score 0-100: PnL 40%, win rate 25%, activity 20%, diversity 15%."""
    # PnL component: normalize relative to a reference of $10k 30d PnL
    pnl_ref = 10_000.0
    pnl_score = min(trader.total_pnl_30d / pnl_ref, 1.0) * 40.0 if trader.total_pnl_30d > 0 else 0.0

    # Win rate component: scale 0-1 win rate to 0-25
    win_rate_score = min(trader.win_rate, 1.0) * 25.0

    # Activity component: reward recency; 0 days ago = full score, last_active_days = 0
    days_inactive = _days_since(trader.last_active_timestamp)
    activity_score = max(0.0, 1.0 - days_inactive / settings.last_active_days) * 20.0

    # Diversity component: scale markets traded; cap at 10
    diversity_score = min(trader.num_markets_traded / 10.0, 1.0) * 15.0

    total = pnl_score + win_rate_score + activity_score + diversity_score
    return round(min(max(total, _MIN_SCORE), _MAX_SCORE), 2)
