from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from loguru import logger

from config.settings import settings
from data.models import Market, Position, Trader

_LEADERBOARD_PAGE_SIZE = 20

_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0

_market_cache: dict[str, tuple[Market, float]] = {}
_CACHE_TTL = 60.0


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True)


async def _get_with_retry(client: httpx.AsyncClient, url: str, **kwargs: Any) -> dict | list:
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = await client.get(url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_exc = exc
            wait = _BACKOFF_BASE * (2 ** attempt)
            logger.warning(
                f"Request to {url} failed (attempt {attempt + 1}/{_MAX_RETRIES}): {exc}. Retrying in {wait}s"
            )
            await asyncio.sleep(wait)
    raise RuntimeError(f"All {_MAX_RETRIES} retries failed for {url}") from last_exc


def _parse_trader(raw: dict) -> Trader | None:
    try:
        from datetime import datetime, timezone

        address = raw.get("user") or raw.get("address") or raw.get("proxyWallet", "")
        if not address:
            return None

        last_active_raw = raw.get("lastActive") or raw.get("last_active_timestamp")
        if last_active_raw is None:
            return None
        if isinstance(last_active_raw, (int, float)):
            last_active = datetime.fromtimestamp(last_active_raw, tz=timezone.utc)
        else:
            last_active = datetime.fromisoformat(str(last_active_raw).replace("Z", "+00:00"))

        first_trade_raw = raw.get("firstTradeDate") or raw.get("first_trade_timestamp")
        first_trade: datetime | None = None
        if first_trade_raw is not None:
            if isinstance(first_trade_raw, (int, float)):
                first_trade = datetime.fromtimestamp(first_trade_raw, tz=timezone.utc)
            else:
                first_trade = datetime.fromisoformat(str(first_trade_raw).replace("Z", "+00:00"))

        return Trader(
            address=str(address),
            username=raw.get("name") or raw.get("username"),
            total_pnl_30d=float(raw.get("pnl") or raw.get("profit") or raw.get("total_pnl_30d") or 0.0),
            num_trades_30d=int(raw.get("numTrades") or raw.get("num_trades_30d") or 0),
            last_active_timestamp=last_active,
            win_rate=float(raw.get("winRate") or raw.get("win_rate") or 0.0),
            avg_position_size=float(raw.get("avgPositionSize") or raw.get("avg_position_size") or 0.0),
            first_trade_timestamp=first_trade,
            num_markets_traded=int(raw.get("marketsTraded") or raw.get("num_markets_traded") or 0),
            max_single_trade_pnl=float(raw.get("maxSingleTradePnl") or raw.get("max_single_trade_pnl") or 0.0),
            vol=float(raw.get("volume") or raw.get("vol") or 0.0),
            num_open_positions=int(raw.get("numOpenPositions") or raw.get("num_open_positions") or 0),
        )
    except Exception as exc:
        logger.debug(f"Failed to parse trader record: {exc}")
        return None


def _parse_position(raw: dict, trader_address: str | None = None) -> Position | None:
    try:
        from datetime import datetime, timezone

        market_id = raw.get("conditionId") or raw.get("asset_id") or raw.get("market_id") or raw.get("marketId", "")
        if not market_id:
            return None

        opened_raw = raw.get("createdAt") or raw.get("timestamp_opened") or raw.get("startDate")
        if opened_raw is None:
            opened = datetime.now(tz=timezone.utc)
        elif isinstance(opened_raw, (int, float)):
            opened = datetime.fromtimestamp(opened_raw, tz=timezone.utc)
        else:
            opened = datetime.fromisoformat(str(opened_raw).replace("Z", "+00:00"))

        return Position(
            market_id=str(market_id),
            market_title=str(raw.get("title") or raw.get("market_title") or raw.get("question") or "Unknown"),
            outcome=str(raw.get("outcome") or raw.get("side") or "YES"),
            size=float(raw.get("size") or raw.get("currentValue") or raw.get("sharesOwned") or 0.0),
            entry_price=float(raw.get("avgPrice") or raw.get("entry_price") or raw.get("priceAvg") or 0.0),
            timestamp_opened=opened,
            trader_address=trader_address,
        )
    except Exception as exc:
        logger.debug(f"Failed to parse position record: {exc}")
        return None


def _parse_market(raw: dict, market_id: str) -> Market | None:
    try:
        from datetime import datetime, timezone

        closes_raw = (
            raw.get("endDate")
            or raw.get("closes_at")
            or raw.get("resolutionTime")
            or raw.get("closingTime")
        )
        if closes_raw is None:
            return None
        if isinstance(closes_raw, (int, float)):
            closes_at = datetime.fromtimestamp(closes_raw, tz=timezone.utc)
        else:
            closes_at = datetime.fromisoformat(str(closes_raw).replace("Z", "+00:00"))

        return Market(
            market_id=market_id,
            title=str(raw.get("question") or raw.get("title") or raw.get("description") or "Unknown"),
            closes_at=closes_at,
            current_price=float(raw.get("lastTradePrice") or raw.get("current_price") or raw.get("midpoint") or 0.0),
            liquidity=float(raw.get("liquidity") or raw.get("volume") or 0.0),
        )
    except Exception as exc:
        logger.debug(f"Failed to parse market record for {market_id}: {exc}")
        return None


async def get_top_traders(
    category: str | None = None,
    limit: int | None = None,
) -> list[Trader]:
    category = (category or settings.trader_category).upper()
    limit = limit or settings.top_traders_limit

    url = f"{settings.polymarket_data_api}/v1/leaderboard"
    pages_needed = (limit + _LEADERBOARD_PAGE_SIZE - 1) // _LEADERBOARD_PAGE_SIZE
    base_params = {
        "category": category,
        "timePeriod": "MONTH",
        "orderBy": "PNL",
        "limit": _LEADERBOARD_PAGE_SIZE,
    }

    now = datetime.now(tz=timezone.utc)
    async with _make_client() as client:
        tasks = [
            _get_with_retry(client, url, params={**base_params, "offset": i * _LEADERBOARD_PAGE_SIZE})
            for i in range(pages_needed)
        ]
        try:
            pages = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as exc:
            logger.error(f"get_top_traders failed: {exc}")
            return []

    records: list[dict] = []
    for page in pages:
        if isinstance(page, Exception):
            logger.warning(f"Leaderboard page failed: {page}")
            continue
        page_records = page if isinstance(page, list) else page.get("data", page.get("leaderboard", []))
        records.extend(page_records)

    traders: list[Trader] = []
    for raw in records[:limit]:
        address = raw.get("proxyWallet") or raw.get("user") or raw.get("address", "")
        if not address:
            continue
        traders.append(Trader(
            address=str(address),
            username=raw.get("userName") or raw.get("name") or raw.get("xUsername"),
            total_pnl_30d=float(raw.get("pnl") or 0.0),
            vol=float(raw.get("vol") or raw.get("volume") or 0.0),
            last_active_timestamp=now,  # placeholder; enriched from activity in pipeline
        ))

    logger.info(f"Fetched {len(traders)} traders from leaderboard")
    return traders


async def get_active_positions(trader_address: str) -> list[Position]:
    url = f"{settings.polymarket_data_api}/v1/positions"
    params = {"user": trader_address, "sizeThreshold": "0.01", "sortBy": "CURRENT", "limit": 100}

    async with _make_client() as client:
        try:
            data = await _get_with_retry(client, url, params=params)
        except Exception as exc:
            logger.warning(f"get_active_positions failed for {trader_address[:8]}: {exc}")
            return []

    records: list[dict] = data if isinstance(data, list) else data.get("data", data.get("positions", []))
    positions: list[Position] = []
    for raw in records:
        pos = _parse_position(raw, trader_address=trader_address)
        if pos and pos.size > 0:
            positions.append(pos)

    return positions


async def get_market_metadata(market_id: str) -> Market | None:
    now = time.monotonic()
    cached = _market_cache.get(market_id)
    if cached and now < cached[1]:
        return cached[0]

    url = f"{settings.polymarket_gamma_api}/markets"
    params = {"conditionId": market_id}

    async with _make_client() as client:
        try:
            data = await _get_with_retry(client, url, params=params)
        except Exception as exc:
            logger.warning(f"get_market_metadata failed for {market_id}: {exc}")
            return None

    records: list[dict] = data if isinstance(data, list) else data.get("data", data.get("markets", []))
    raw = records[0] if records else (data if isinstance(data, dict) else None)
    if not raw:
        return None

    market = _parse_market(raw, market_id)
    if market:
        _market_cache[market_id] = (market, now + _CACHE_TTL)

    return market


async def fetch_all_positions(traders: list[Trader]) -> dict[str, list[Position]]:
    """Fetch active positions for all traders concurrently."""
    results = await asyncio.gather(
        *[get_active_positions(t.address) for t in traders],
        return_exceptions=True,
    )
    positions_by_trader: dict[str, list[Position]] = {}
    for trader, result in zip(traders, results):
        if isinstance(result, Exception):
            logger.warning(f"Position fetch error for {trader.address[:8]}: {result}")
            positions_by_trader[trader.address] = []
        else:
            positions_by_trader[trader.address] = result  # type: ignore[assignment]
    return positions_by_trader


async def get_trader_activity(address: str) -> dict:
    """Fetch recent trading activity; returns last_active, num_trades_30d, num_markets_traded."""
    url = f"{settings.polymarket_data_api}/v1/activity"
    params = {"user": address, "limit": 50}

    async with _make_client() as client:
        try:
            data = await _get_with_retry(client, url, params=params)
        except Exception as exc:
            logger.warning(f"get_trader_activity failed for {address[:8]}: {exc}")
            return {}

    records: list[dict] = data if isinstance(data, list) else data.get("data", data.get("activity", []))
    if not records:
        return {}

    now = datetime.now(tz=timezone.utc)
    cutoff_30d = now - timedelta(days=30)

    last_active: datetime | None = None
    num_trades_30d = 0
    market_ids: set[str] = set()

    for r in records:
        ts_raw = r.get("timestamp") or r.get("createdAt") or r.get("time")
        ts: datetime | None = None
        if ts_raw is not None:
            try:
                if isinstance(ts_raw, (int, float)):
                    ts = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
                else:
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            except Exception:
                pass

        if ts:
            if last_active is None or ts > last_active:
                last_active = ts
            if ts >= cutoff_30d:
                num_trades_30d += 1

        mid = str(r.get("conditionId") or r.get("market_id") or r.get("marketId") or "")
        if mid:
            market_ids.add(mid)

    return {
        "last_active_timestamp": last_active or now,
        "num_trades_30d": num_trades_30d,
        "num_markets_traded": len(market_ids),
        "num_open_positions": len(market_ids),  # approximation until positions fetch
    }


async def get_fill_price(token_id: str) -> float | None:
    """Fetch the last fill price for a CLOB token."""
    url = f"{settings.polymarket_api_base}/last-trade-price"
    params = {"token_id": token_id}

    async with _make_client() as client:
        try:
            data = await _get_with_retry(client, url, params=params)
        except Exception as exc:
            logger.warning(f"get_fill_price failed for {token_id}: {exc}")
            return None

    if isinstance(data, dict):
        price = data.get("price") or data.get("lastTradePrice")
        return float(price) if price is not None else None
    return None


async def get_current_price(token_id: str) -> float | None:
    """Fetch the current midpoint price for a CLOB token."""
    url = f"{settings.polymarket_api_base}/midpoint"
    params = {"token_id": token_id}

    async with _make_client() as client:
        try:
            data = await _get_with_retry(client, url, params=params)
        except Exception as exc:
            logger.warning(f"get_current_price failed for {token_id}: {exc}")
            return None

    if isinstance(data, dict):
        price = data.get("mid") or data.get("midpoint")
        return float(price) if price is not None else None
    return None


async def fetch_all_activities(traders: list[Trader]) -> dict[str, dict]:
    """Fetch activity stats for all traders concurrently."""
    results = await asyncio.gather(
        *[get_trader_activity(t.address) for t in traders],
        return_exceptions=True,
    )
    activities: dict[str, dict] = {}
    for trader, result in zip(traders, results):
        if isinstance(result, Exception):
            logger.warning(f"Activity fetch error for {trader.address[:8]}: {result}")
            activities[trader.address] = {}
        else:
            activities[trader.address] = result  # type: ignore[assignment]
    return activities
