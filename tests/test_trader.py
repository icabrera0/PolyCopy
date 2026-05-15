from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from core.trader import check_and_close_expired_trades, close_trade, open_trade
from data.models import Market, PaperTrade, Signal


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_signal(**overrides) -> Signal:
    base = dict(
        market_id="mkt-test",
        market_title="Will BTC hit 100k?",
        outcome="YES",
        trader_count=7,
        total_filtered_traders=10,
        raw_consensus_pct=70.0,
        weighted_consensus_pct=70.0,
        avg_entry_price=0.65,
        market_closes_at=_utc_now() + timedelta(hours=12),
        signal_strength="STRONG",
    )
    base.update(overrides)
    return Signal(**base)


def _make_trade(**overrides) -> PaperTrade:
    base = dict(
        market_id="mkt-test",
        market_title="Will BTC hit 100k?",
        outcome="YES",
        entry_price=0.65,
        stake=100.0,
        signal_strength="STRONG",
        weighted_consensus_pct=70.0,
        trader_count=7,
        status="OPEN",
        opened_at=_utc_now() - timedelta(hours=1),
    )
    base.update(overrides)
    return PaperTrade(**base)


def _make_market(hours_from_now: float = 12.0, current_price: float = 0.5) -> Market:
    return Market(
        market_id="mkt-test",
        title="Will BTC hit 100k?",
        closes_at=_utc_now() + timedelta(hours=hours_from_now),
        current_price=current_price,
        liquidity=5000.0,
    )


# --- open_trade ---

async def test_open_trade_creates_new_trade():
    sig = _make_signal()
    with patch("core.trader.db.trade_exists", new=AsyncMock(return_value=False)), \
         patch("core.trader.db.open_trade", new=AsyncMock()) as mock_open:
        trade = await open_trade(sig, ":memory:")

    assert trade is not None
    assert trade.market_id == "mkt-test"
    assert trade.outcome == "YES"
    assert trade.entry_price == pytest.approx(0.65)
    assert trade.status == "OPEN"
    mock_open.assert_awaited_once()


async def test_open_trade_returns_none_on_duplicate():
    sig = _make_signal()
    with patch("core.trader.db.trade_exists", new=AsyncMock(return_value=True)):
        trade = await open_trade(sig, ":memory:")

    assert trade is None


async def test_open_trade_uses_default_stake():
    sig = _make_signal()
    with patch("core.trader.db.trade_exists", new=AsyncMock(return_value=False)), \
         patch("core.trader.db.open_trade", new=AsyncMock()):
        trade = await open_trade(sig, ":memory:")

    assert trade is not None
    assert trade.stake == pytest.approx(100.0)


async def test_open_trade_propagates_signal_fields():
    sig = _make_signal(signal_strength="MODERATE", weighted_consensus_pct=55.0, trader_count=5)
    with patch("core.trader.db.trade_exists", new=AsyncMock(return_value=False)), \
         patch("core.trader.db.open_trade", new=AsyncMock()):
        trade = await open_trade(sig, ":memory:")

    assert trade is not None
    assert trade.signal_strength == "MODERATE"
    assert trade.weighted_consensus_pct == pytest.approx(55.0)
    assert trade.trader_count == 5


# --- close_trade ---

async def test_close_trade_win_pnl():
    trade = _make_trade(entry_price=0.5, stake=100.0)
    with patch("core.trader.db.close_trade", new=AsyncMock()):
        updated = await close_trade(trade, "WIN", exit_price=0.75, db_path=":memory:")

    assert updated.resolution == "WIN"
    assert updated.pnl == pytest.approx(50.0)
    assert updated.status == "CLOSED"
    assert updated.exit_price == pytest.approx(0.75)
    assert updated.closed_at is not None


async def test_close_trade_loss_pnl():
    trade = _make_trade(entry_price=0.5, stake=100.0)
    with patch("core.trader.db.close_trade", new=AsyncMock()):
        updated = await close_trade(trade, "LOSS", exit_price=0.01, db_path=":memory:")

    assert updated.resolution == "LOSS"
    assert updated.pnl == pytest.approx(-100.0)
    assert updated.status == "CLOSED"


async def test_close_trade_na_pnl_zero():
    trade = _make_trade(entry_price=0.5, stake=100.0)
    with patch("core.trader.db.close_trade", new=AsyncMock()):
        updated = await close_trade(trade, "N/A", exit_price=0.5, db_path=":memory:")

    assert updated.pnl == pytest.approx(0.0)
    assert updated.status == "CLOSED"


async def test_close_trade_calls_db():
    trade = _make_trade()
    with patch("core.trader.db.close_trade", new=AsyncMock()) as mock_close:
        await close_trade(trade, "WIN", exit_price=0.99, db_path=":memory:")

    mock_close.assert_awaited_once()
    call_args = mock_close.call_args
    assert call_args.args[1] == trade.id
    assert call_args.args[2] == "WIN"


# --- check_and_close_expired_trades ---

async def test_check_and_close_expired_no_metadata():
    trade = _make_trade(opened_at=_utc_now() - timedelta(hours=27))

    with patch("core.trader.db.get_open_trades", new=AsyncMock(return_value=[trade])), \
         patch("core.trader.get_market_metadata", new=AsyncMock(return_value=None)), \
         patch("core.trader.db.expire_trade", new=AsyncMock()) as mock_expire:
        closed = await check_and_close_expired_trades(":memory:")

    assert len(closed) == 1
    assert closed[0].status == "EXPIRED"
    mock_expire.assert_awaited_once()


async def test_check_and_close_expired_with_market_metadata():
    trade = _make_trade()
    market = _make_market(hours_from_now=-2.0)

    with patch("core.trader.db.get_open_trades", new=AsyncMock(return_value=[trade])), \
         patch("core.trader.get_market_metadata", new=AsyncMock(return_value=market)), \
         patch("core.trader.db.expire_trade", new=AsyncMock()) as mock_expire:
        closed = await check_and_close_expired_trades(":memory:")

    assert len(closed) == 1
    assert closed[0].status == "EXPIRED"
    mock_expire.assert_awaited_once()


async def test_check_and_close_resolved_win_yes_outcome():
    trade = _make_trade(outcome="YES")
    market = _make_market(current_price=0.99)

    with patch("core.trader.db.get_open_trades", new=AsyncMock(return_value=[trade])), \
         patch("core.trader.get_market_metadata", new=AsyncMock(return_value=market)), \
         patch("core.trader.db.close_trade", new=AsyncMock()):
        closed = await check_and_close_expired_trades(":memory:")

    assert len(closed) == 1
    assert closed[0].resolution == "WIN"


async def test_check_and_close_resolved_loss_yes_outcome():
    trade = _make_trade(outcome="YES")
    market = _make_market(current_price=0.01)

    with patch("core.trader.db.get_open_trades", new=AsyncMock(return_value=[trade])), \
         patch("core.trader.get_market_metadata", new=AsyncMock(return_value=market)), \
         patch("core.trader.db.close_trade", new=AsyncMock()):
        closed = await check_and_close_expired_trades(":memory:")

    assert len(closed) == 1
    assert closed[0].resolution == "LOSS"


async def test_check_and_close_resolved_win_no_outcome():
    trade = _make_trade(outcome="NO")
    market = _make_market(current_price=0.01)

    with patch("core.trader.db.get_open_trades", new=AsyncMock(return_value=[trade])), \
         patch("core.trader.get_market_metadata", new=AsyncMock(return_value=market)), \
         patch("core.trader.db.close_trade", new=AsyncMock()):
        closed = await check_and_close_expired_trades(":memory:")

    assert len(closed) == 1
    assert closed[0].resolution == "WIN"


async def test_check_and_close_no_action_when_market_open():
    trade = _make_trade()
    market = _make_market(current_price=0.5)

    with patch("core.trader.db.get_open_trades", new=AsyncMock(return_value=[trade])), \
         patch("core.trader.get_market_metadata", new=AsyncMock(return_value=market)), \
         patch("core.trader.db.close_trade", new=AsyncMock()):
        closed = await check_and_close_expired_trades(":memory:")

    assert closed == []


async def test_check_and_close_empty_open_trades():
    with patch("core.trader.db.get_open_trades", new=AsyncMock(return_value=[])):
        closed = await check_and_close_expired_trades(":memory:")

    assert closed == []