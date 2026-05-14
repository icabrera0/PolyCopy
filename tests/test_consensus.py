from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.consensus import _classify, _market_in_window, detect_consensus
from data.models import Market, Position


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_position(
    market_id: str = "mkt-1",
    outcome: str = "YES",
    size: float = 10.0,
    entry_price: float = 0.6,
    trader_address: str = "0xAAA",
) -> Position:
    return Position(
        market_id=market_id,
        market_title=f"Market {market_id}",
        outcome=outcome,
        size=size,
        entry_price=entry_price,
        timestamp_opened=_utc_now(),
        trader_address=trader_address,
    )


def _make_market(market_id: str = "mkt-1", hours_from_now: float = 12.0) -> Market:
    return Market(
        market_id=market_id,
        title=f"Market {market_id}",
        closes_at=_utc_now() + timedelta(hours=hours_from_now),
        current_price=0.5,
        liquidity=10000.0,
    )


def _traders_with_position(
    count: int, total: int, market_id: str = "mkt-1", outcome: str = "YES"
) -> dict[str, list[Position]]:
    """count traders hold the position; rest hold nothing."""
    result: dict[str, list[Position]] = {}
    for i in range(count):
        addr = f"0xPOS{i:010x}"
        result[addr] = [_make_position(market_id=market_id, outcome=outcome, trader_address=addr)]
    for i in range(total - count):
        result[f"0xNONE{i:010x}"] = []
    return result


# --- _classify ---

def test_classify_strong_at_threshold():
    assert _classify(0.70) == "STRONG"


def test_classify_strong_above_threshold():
    assert _classify(1.0) == "STRONG"


def test_classify_moderate_at_threshold():
    assert _classify(0.50) == "MODERATE"


def test_classify_moderate_below_strong():
    assert _classify(0.65) == "MODERATE"


def test_classify_weak_at_threshold():
    assert _classify(0.35) == "WEAK"


def test_classify_weak_below_moderate():
    assert _classify(0.45) == "WEAK"


def test_classify_none_below_weak():
    assert _classify(0.34) is None


def test_classify_none_zero():
    assert _classify(0.0) is None


# --- _market_in_window ---

def test_market_in_window_valid():
    assert _market_in_window(_utc_now() + timedelta(hours=12)) is True


def test_market_in_window_at_min_boundary():
    # Add buffer so timing jitter does not push remaining below the 120s minimum
    assert _market_in_window(_utc_now() + timedelta(seconds=125)) is True


def test_market_in_window_too_soon():
    assert _market_in_window(_utc_now() + timedelta(seconds=60)) is False


def test_market_in_window_at_max_boundary():
    assert _market_in_window(_utc_now() + timedelta(hours=24)) is True


def test_market_in_window_too_far():
    assert _market_in_window(_utc_now() + timedelta(hours=25)) is False


def test_market_in_window_naive_datetime_treated_as_utc():
    naive = datetime.utcnow() + timedelta(hours=6)
    assert _market_in_window(naive) is True


# --- detect_consensus ---

def test_detect_consensus_empty_returns_empty():
    assert detect_consensus({}) == []


def test_detect_consensus_strong_signal():
    result = detect_consensus(_traders_with_position(8, 10))
    assert len(result) == 1
    assert result[0].signal_strength == "STRONG"
    assert result[0].consensus_pct == pytest.approx(80.0)


def test_detect_consensus_moderate_signal():
    result = detect_consensus(_traders_with_position(6, 10))
    assert len(result) == 1
    assert result[0].signal_strength == "MODERATE"


def test_detect_consensus_weak_signal():
    result = detect_consensus(_traders_with_position(4, 10))
    assert len(result) == 1
    assert result[0].signal_strength == "WEAK"


def test_detect_consensus_below_threshold_no_signal():
    result = detect_consensus(_traders_with_position(3, 10))
    assert result == []


def test_detect_consensus_skips_zero_size_positions():
    positions_by_trader = {
        "0xZERO": [_make_position(size=0.0)],
        "0xOTHER": [],
    }
    result = detect_consensus(positions_by_trader)
    assert result == []


def test_detect_consensus_correct_trader_count():
    result = detect_consensus(_traders_with_position(7, 10))
    assert result[0].trader_count == 7
    assert result[0].total_filtered_traders == 10


def test_detect_consensus_avg_entry_price():
    positions_by_trader = {
        "0xA": [_make_position(entry_price=0.6)],
        "0xB": [_make_position(entry_price=0.8)],
    }
    result = detect_consensus(positions_by_trader)
    assert len(result) == 1
    assert result[0].avg_entry_price == pytest.approx(0.7)


def test_detect_consensus_distinguishes_outcomes():
    positions_by_trader: dict[str, list[Position]] = {}
    for i in range(5):
        positions_by_trader[f"0xYES{i}"] = [_make_position("mkt-1", "YES")]
        positions_by_trader[f"0xNO{i}"] = [_make_position("mkt-1", "NO")]

    result = detect_consensus(positions_by_trader)
    outcomes = {sig.outcome for sig in result}
    assert "YES" in outcomes
    assert "NO" in outcomes


def test_detect_consensus_multiple_markets():
    positions_by_trader: dict[str, list[Position]] = {}
    for i in range(4):
        addr = f"0x{i:040x}"
        positions_by_trader[addr] = [
            _make_position("mkt-A", "YES", trader_address=addr),
            _make_position("mkt-B", "NO", trader_address=addr),
        ]

    result = detect_consensus(positions_by_trader)
    market_ids = {sig.market_id for sig in result}
    assert "mkt-A" in market_ids
    assert "mkt-B" in market_ids


# --- time-window guards via market_metadata ---

def test_detect_consensus_time_guard_skips_closing_soon():
    pbt = _traders_with_position(8, 10)
    mkt = _make_market("mkt-1", hours_from_now=0.01)  # ~36s -> below 120s min
    result = detect_consensus(pbt, market_metadata={"mkt-1": mkt})
    assert result == []


def test_detect_consensus_time_guard_skips_too_far():
    pbt = _traders_with_position(8, 10)
    mkt = _make_market("mkt-1", hours_from_now=26.0)
    result = detect_consensus(pbt, market_metadata={"mkt-1": mkt})
    assert result == []


def test_detect_consensus_time_guard_passes_valid_window():
    pbt = _traders_with_position(8, 10)
    mkt = _make_market("mkt-1", hours_from_now=12.0)
    result = detect_consensus(pbt, market_metadata={"mkt-1": mkt})
    assert len(result) == 1


def test_detect_consensus_defaults_to_12h_when_no_metadata():
    pbt = _traders_with_position(8, 10)
    result = detect_consensus(pbt)
    assert len(result) == 1
