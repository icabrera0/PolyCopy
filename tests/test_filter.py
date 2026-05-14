from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.filter import (
    _passes_account_age,
    _passes_activity,
    _passes_diversity,
    _passes_min_trades,
    _passes_pnl_consistency,
    _passes_position_size,
    _passes_win_rate,
    filter_traders,
    score_trader,
)
from data.models import Trader


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_trader(**overrides) -> Trader:
    """Factory producing a Trader that passes all 7 filters by default."""
    base = dict(
        address="0xABC123",
        last_active_timestamp=_utc_now() - timedelta(days=5),
        first_trade_timestamp=_utc_now() - timedelta(days=90),
        total_pnl_30d=1000.0,
        num_trades_30d=20,
        win_rate=0.55,
        avg_position_size=150.0,
        max_single_trade_pnl=600.0,
        num_markets_traded=5,
    )
    base.update(overrides)
    return Trader(**base)


# --- _passes_activity ---

def test_activity_passes_when_recent():
    t = _make_trader(last_active_timestamp=_utc_now() - timedelta(days=1))
    assert _passes_activity(t) is True


def test_activity_fails_when_stale():
    t = _make_trader(last_active_timestamp=_utc_now() - timedelta(days=30))
    assert _passes_activity(t) is False


def test_activity_passes_at_boundary():
    t = _make_trader(last_active_timestamp=_utc_now() - timedelta(days=14, seconds=-10))
    assert _passes_activity(t) is True


# --- _passes_min_trades ---

def test_min_trades_passes_at_threshold():
    t = _make_trader(num_trades_30d=10)
    assert _passes_min_trades(t) is True


def test_min_trades_fails_below_threshold():
    t = _make_trader(num_trades_30d=9)
    assert _passes_min_trades(t) is False


def test_min_trades_passes_well_above():
    t = _make_trader(num_trades_30d=100)
    assert _passes_min_trades(t) is True


# --- _passes_position_size ---

def test_position_size_passes_at_threshold():
    t = _make_trader(avg_position_size=50.0)
    assert _passes_position_size(t) is True


def test_position_size_fails_below_threshold():
    t = _make_trader(avg_position_size=49.99)
    assert _passes_position_size(t) is False


def test_position_size_passes_well_above():
    t = _make_trader(avg_position_size=500.0)
    assert _passes_position_size(t) is True


# --- _passes_win_rate ---

def test_win_rate_passes_at_threshold():
    t = _make_trader(win_rate=0.40)
    assert _passes_win_rate(t) is True


def test_win_rate_fails_below_threshold():
    t = _make_trader(win_rate=0.39)
    assert _passes_win_rate(t) is False


def test_win_rate_passes_at_one():
    t = _make_trader(win_rate=1.0)
    assert _passes_win_rate(t) is True


# --- _passes_pnl_consistency ---

def test_pnl_consistency_passes_when_no_dominant_trade():
    # max/total = 500/1000 = 0.5, below 0.80 limit
    t = _make_trader(total_pnl_30d=1000.0, max_single_trade_pnl=500.0)
    assert _passes_pnl_consistency(t) is True


def test_pnl_consistency_fails_when_single_trade_dominates():
    # max/total = 900/1000 = 0.9, above 0.80 limit
    t = _make_trader(total_pnl_30d=1000.0, max_single_trade_pnl=900.0)
    assert _passes_pnl_consistency(t) is False


def test_pnl_consistency_always_passes_when_pnl_nonpositive():
    t = _make_trader(total_pnl_30d=0.0, max_single_trade_pnl=9999.0)
    assert _passes_pnl_consistency(t) is True


def test_pnl_consistency_passes_at_exact_limit():
    # 800/1000 = 0.80, exactly at limit -> passes (<=)
    t = _make_trader(total_pnl_30d=1000.0, max_single_trade_pnl=800.0)
    assert _passes_pnl_consistency(t) is True


# --- _passes_account_age ---

def test_account_age_passes_when_old_enough():
    t = _make_trader(first_trade_timestamp=_utc_now() - timedelta(days=60))
    assert _passes_account_age(t) is True


def test_account_age_fails_when_too_new():
    t = _make_trader(first_trade_timestamp=_utc_now() - timedelta(days=10))
    assert _passes_account_age(t) is False


def test_account_age_fails_when_none():
    t = _make_trader(first_trade_timestamp=None)
    assert _passes_account_age(t) is False


def test_account_age_passes_at_boundary():
    t = _make_trader(first_trade_timestamp=_utc_now() - timedelta(days=30, seconds=10))
    assert _passes_account_age(t) is True


# --- _passes_diversity ---

def test_diversity_passes_at_threshold():
    t = _make_trader(num_markets_traded=3)
    assert _passes_diversity(t) is True


def test_diversity_fails_below_threshold():
    t = _make_trader(num_markets_traded=2)
    assert _passes_diversity(t) is False


def test_diversity_passes_well_above():
    t = _make_trader(num_markets_traded=20)
    assert _passes_diversity(t) is True


# --- score_trader ---

def test_score_trader_maximum_possible():
    t = _make_trader(
        total_pnl_30d=10_000.0,
        win_rate=1.0,
        last_active_timestamp=_utc_now(),
        num_markets_traded=10,
    )
    score = score_trader(t)
    assert score == pytest.approx(100.0, abs=0.5)


def test_score_trader_zero_pnl_and_no_activity():
    t = _make_trader(
        total_pnl_30d=0.0,
        win_rate=0.0,
        last_active_timestamp=_utc_now() - timedelta(days=14),
        num_markets_traded=0,
    )
    score = score_trader(t)
    assert score == pytest.approx(0.0, abs=0.5)


def test_score_trader_bounds():
    t = _make_trader(
        total_pnl_30d=5000.0,
        win_rate=0.5,
        last_active_timestamp=_utc_now() - timedelta(days=7),
        num_markets_traded=5,
    )
    score = score_trader(t)
    assert 0.0 <= score <= 100.0


def test_score_trader_pnl_capped_at_reference():
    # PnL >> 10k should still cap at 40 points
    t = _make_trader(
        total_pnl_30d=1_000_000.0,
        win_rate=0.0,
        last_active_timestamp=_utc_now() - timedelta(days=14),
        num_markets_traded=0,
    )
    score = score_trader(t)
    assert score == pytest.approx(40.0, abs=0.5)


def test_score_trader_negative_pnl_gives_zero_pnl_component():
    t = _make_trader(
        total_pnl_30d=-500.0,
        win_rate=0.0,
        last_active_timestamp=_utc_now() - timedelta(days=14),
        num_markets_traded=0,
    )
    score = score_trader(t)
    assert score == pytest.approx(0.0, abs=0.5)


# --- filter_traders integration ---

def test_filter_traders_passes_all_valid():
    t = _make_trader()
    result = filter_traders([t])
    assert len(result) == 1
    assert result[0].quality_score > 0


def test_filter_traders_removes_stale_trader():
    t = _make_trader(last_active_timestamp=_utc_now() - timedelta(days=30))
    assert filter_traders([t]) == []


def test_filter_traders_removes_low_win_rate():
    t = _make_trader(win_rate=0.1)
    assert filter_traders([t]) == []


def test_filter_traders_multiple_mixed():
    good = _make_trader(address="0xGOOD")
    bad = _make_trader(address="0xBAD", win_rate=0.1)
    result = filter_traders([good, bad])
    assert len(result) == 1
    assert result[0].address == "0xGOOD"


def test_filter_traders_empty_input():
    assert filter_traders([]) == []


def test_filter_traders_assigns_quality_score():
    t = _make_trader()
    result = filter_traders([t])
    assert result[0].quality_score >= 0.0
