from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.fetcher import (
    _CACHE_TTL,
    _get_with_retry,
    _market_cache,
    _parse_market,
    _parse_position,
    _parse_trader,
    fetch_all_positions,
    get_active_positions,
    get_market_metadata,
    get_top_traders,
)
from data.models import Market, Position, Trader


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _trader_raw(**overrides) -> dict:
    base = {
        "user": "0xABCDEF1234567890",
        "lastActive": _utc_now().timestamp(),
        "pnl": 5000.0,
        "numTrades": 25,
        "winRate": 0.6,
        "avgPositionSize": 200.0,
        "firstTradeDate": (_utc_now() - timedelta(days=60)).timestamp(),
        "marketsTraded": 5,
        "maxSingleTradePnl": 1000.0,
    }
    base.update(overrides)
    return base


def _position_raw(**overrides) -> dict:
    base = {
        "conditionId": "market-abc",
        "title": "Will BTC hit 100k?",
        "outcome": "YES",
        "size": 50.0,
        "avgPrice": 0.65,
        "createdAt": _utc_now().timestamp(),
    }
    base.update(overrides)
    return base


def _market_raw(**overrides) -> dict:
    base = {
        "question": "Will ETH flip BTC?",
        "endDate": (_utc_now() + timedelta(hours=12)).timestamp(),
        "lastTradePrice": 0.45,
        "liquidity": 50000.0,
    }
    base.update(overrides)
    return base


# --- _parse_trader ---

def test_parse_trader_valid():
    t = _parse_trader(_trader_raw())
    assert t is not None
    assert t.address == "0xABCDEF1234567890"
    assert t.total_pnl_30d == 5000.0
    assert t.num_trades_30d == 25
    assert t.win_rate == pytest.approx(0.6)
    assert t.num_markets_traded == 5


def test_parse_trader_missing_address():
    raw = _trader_raw()
    del raw["user"]
    assert _parse_trader(raw) is None


def test_parse_trader_missing_last_active():
    raw = _trader_raw()
    del raw["lastActive"]
    assert _parse_trader(raw) is None


def test_parse_trader_iso_timestamp():
    ts = _utc_now().isoformat()
    t = _parse_trader(_trader_raw(lastActive=ts))
    assert t is not None
    assert t.last_active_timestamp.tzinfo is not None


def test_parse_trader_alt_fields():
    raw = {
        "address": "0xDEAD",
        "last_active_timestamp": _utc_now().isoformat(),
        "total_pnl_30d": 100.0,
        "num_trades_30d": 10,
        "win_rate": 0.5,
        "avg_position_size": 75.0,
        "num_markets_traded": 3,
        "max_single_trade_pnl": 20.0,
    }
    t = _parse_trader(raw)
    assert t is not None
    assert t.address == "0xDEAD"


# --- _parse_position ---

def test_parse_position_valid():
    p = _parse_position(_position_raw())
    assert p is not None
    assert p.market_id == "market-abc"
    assert p.outcome == "YES"
    assert p.size == 50.0
    assert p.entry_price == pytest.approx(0.65)


def test_parse_position_missing_market_id():
    raw = _position_raw()
    del raw["conditionId"]
    assert _parse_position(raw) is None


def test_parse_position_no_timestamp_defaults_now():
    raw = _position_raw()
    del raw["createdAt"]
    p = _parse_position(raw)
    assert p is not None
    assert (_utc_now() - p.timestamp_opened).total_seconds() < 5


def test_parse_position_sets_trader_address():
    p = _parse_position(_position_raw(), trader_address="0xFOO")
    assert p is not None
    assert p.trader_address == "0xFOO"


# --- _parse_market ---

def test_parse_market_valid():
    m = _parse_market(_market_raw(), "mkt-1")
    assert m is not None
    assert m.market_id == "mkt-1"
    assert m.title == "Will ETH flip BTC?"
    assert m.current_price == pytest.approx(0.45)
    assert m.liquidity == pytest.approx(50000.0)


def test_parse_market_missing_enddate():
    raw = _market_raw()
    del raw["endDate"]
    assert _parse_market(raw, "mkt-1") is None


def test_parse_market_iso_closes_at():
    ts = (_utc_now() + timedelta(hours=6)).isoformat()
    m = _parse_market(_market_raw(endDate=ts), "mkt-2")
    assert m is not None
    assert m.closes_at.tzinfo is not None


# --- get_top_traders (mocked HTTP) ---

@pytest.mark.asyncio
async def test_get_top_traders_success():
    raw_list = [_trader_raw(user=f"0x{i:040x}") for i in range(3)]
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=raw_list)

    with patch("core.fetcher._make_client") as mock_make_client:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_make_client.return_value = mock_client

        traders = await get_top_traders(category="Crypto", limit=50)

    assert len(traders) == 3
    assert all(isinstance(t, Trader) for t in traders)


@pytest.mark.asyncio
async def test_get_top_traders_api_error_returns_empty():
    with patch("core.fetcher._make_client") as mock_make_client:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_make_client.return_value = mock_client

        traders = await get_top_traders()

    assert traders == []


# --- get_active_positions (mocked HTTP) ---

@pytest.mark.asyncio
async def test_get_active_positions_success():
    raw_list = [_position_raw(size=10.0), _position_raw(conditionId="mkt-2", size=20.0)]
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=raw_list)

    with patch("core.fetcher._make_client") as mock_make_client:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_make_client.return_value = mock_client

        positions = await get_active_positions("0xABC")

    assert len(positions) == 2
    assert all(isinstance(p, Position) for p in positions)


@pytest.mark.asyncio
async def test_get_active_positions_filters_zero_size():
    raw_list = [_position_raw(size=0.0), _position_raw(size=10.0)]
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=raw_list)

    with patch("core.fetcher._make_client") as mock_make_client:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_make_client.return_value = mock_client

        positions = await get_active_positions("0xABC")

    assert len(positions) == 1


# --- get_market_metadata (mocked HTTP + cache) ---

@pytest.mark.asyncio
async def test_get_market_metadata_caches_result():
    _market_cache.clear()
    raw = _market_raw()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=[raw])

    with patch("core.fetcher._make_client") as mock_make_client:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_make_client.return_value = mock_client

        m1 = await get_market_metadata("mkt-cache-test")
        m2 = await get_market_metadata("mkt-cache-test")

    # Second call should hit cache; get was called only once
    assert mock_client.get.call_count == 1
    assert m1 is m2


@pytest.mark.asyncio
async def test_get_market_metadata_api_error_returns_none():
    _market_cache.clear()

    with patch("core.fetcher._make_client") as mock_make_client:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_make_client.return_value = mock_client

        result = await get_market_metadata("mkt-err")

    assert result is None


# --- _get_with_retry ---

@pytest.mark.asyncio
async def test_get_with_retry_retries_on_failure():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"ok": True})

    call_count = 0

    async def flaky_get(url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.TimeoutException("timeout")
        return mock_resp

    with patch("asyncio.sleep", new_callable=AsyncMock):
        import httpx as _httpx
        mock_client = MagicMock()
        mock_client.get = flaky_get
        result = await _get_with_retry(mock_client, "http://example.com")

    assert result == {"ok": True}
    assert call_count == 3


@pytest.mark.asyncio
async def test_get_with_retry_raises_after_max_retries():
    async def always_fail(url, **kwargs):
        raise httpx.ConnectError("refused")

    with patch("asyncio.sleep", new_callable=AsyncMock):
        mock_client = MagicMock()
        mock_client.get = always_fail
        with pytest.raises(RuntimeError, match="retries failed"):
            await _get_with_retry(mock_client, "http://example.com")


# --- fetch_all_positions ---

@pytest.mark.asyncio
async def test_fetch_all_positions_concurrent():
    t1 = Trader(
        address="0xAAA", last_active_timestamp=_utc_now(), total_pnl_30d=100.0,
        num_trades_30d=10, win_rate=0.5, avg_position_size=50.0,
    )
    t2 = Trader(
        address="0xBBB", last_active_timestamp=_utc_now(), total_pnl_30d=200.0,
        num_trades_30d=20, win_rate=0.6, avg_position_size=75.0,
    )

    async def mock_positions(addr):
        return [_parse_position(_position_raw(conditionId=addr))]

    with patch("core.fetcher.get_active_positions", side_effect=mock_positions):
        result = await fetch_all_positions([t1, t2])

    assert set(result.keys()) == {"0xAAA", "0xBBB"}
    assert len(result["0xAAA"]) == 1
