from __future__ import annotations

from datetime import datetime, timezone

import httpx
from loguru import logger

from config.settings import settings
from data.models import DailyStats, PaperTrade

_COLOR_GREEN = 0x00FF88
_COLOR_RED = 0xFF4444
_COLOR_GREY = 0x9E9E9E
_COLOR_BLUE = 0x2196F3


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _post(payload: dict) -> None:
    url = settings.discord_webhook_url
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
    except Exception as exc:
        logger.warning(f"Discord webhook failed: {exc}")


def _embed(title: str, color: int, fields: list[dict], description: str = "") -> dict:
    embed: dict = {"title": title, "color": color, "fields": fields, "timestamp": _now_utc().isoformat()}
    if description:
        embed["description"] = description
    return {"embeds": [embed]}


def _field(name: str, value: str, inline: bool = True) -> dict:
    return {"name": name, "value": value, "inline": inline}


async def send_trade_opened(trade: PaperTrade) -> None:
    strength_emoji = {"STRONG": "🟢", "MODERATE": "🟡", "WEAK": "🔵"}.get(trade.signal_strength, "⚪")
    fields = [
        _field("Market", trade.market_title[:50], inline=False),
        _field("Outcome", trade.outcome),
        _field("Signal", f"{strength_emoji} {trade.signal_strength}"),
        _field("Consensus", f"{trade.weighted_consensus_pct:.1f}% ({trade.trader_count} traders)"),
        _field("Entry Price", f"${trade.entry_price:.4f}"),
        _field("Stake", f"${trade.stake:.2f}"),
    ]
    await _post(_embed(f"📈 Trade Opened", _COLOR_GREEN, fields))


async def send_trade_closed(trade: PaperTrade) -> None:
    if trade.status == "EXPIRED":
        color = _COLOR_GREY
        title = "⏰ Trade Expired"
    elif trade.resolution == "WIN":
        color = _COLOR_GREEN
        title = "✅ Trade Won"
    else:
        color = _COLOR_RED
        title = "❌ Trade Lost"

    pnl_str = f"${trade.pnl:+.2f}" if trade.pnl is not None else "N/A"
    duration = ""
    if trade.closed_at and trade.opened_at:
        delta = trade.closed_at - trade.opened_at
        h, rem = divmod(int(delta.total_seconds()), 3600)
        m = rem // 60
        duration = f"{h}h {m}m"

    fields = [
        _field("Market", trade.market_title[:50], inline=False),
        _field("Outcome", trade.outcome),
        _field("Result", trade.resolution or "EXPIRED"),
        _field("Entry", f"${trade.entry_price:.4f}"),
        _field("Exit", f"${trade.exit_price:.4f}" if trade.exit_price else "N/A"),
        _field("PnL", pnl_str),
    ]
    if duration:
        fields.append(_field("Duration", duration))

    await _post(_embed(title, color, fields))


async def send_bot_status(status: str, message: str) -> None:
    color = _COLOR_GREEN if status == "started" else (_COLOR_RED if status in ("error", "stopped") else _COLOR_BLUE)
    title = {"started": "🤖 Bot Started", "stopped": "🛑 Bot Stopped", "error": "⚠️ Bot Error"}.get(status, "ℹ️ Bot Status")
    await _post(_embed(title, color, [_field("Message", message, inline=False)]))


async def send_daily_summary(stats: DailyStats) -> None:
    pnl_color = _COLOR_GREEN if stats.total_pnl >= 0 else _COLOR_RED
    fields = [
        _field("Date", stats.date),
        _field("Trades", f"{stats.trades_opened} opened / {stats.trades_closed} closed"),
        _field("Win Rate", f"{stats.win_rate * 100:.1f}%"),
        _field("Total PnL", f"${stats.total_pnl:+.2f}"),
        _field("STRONG win rate", f"{stats.strong_win_rate * 100:.1f}%"),
        _field("MODERATE win rate", f"{stats.moderate_win_rate * 100:.1f}%"),
    ]
    await _post(_embed("📊 Daily Summary", pnl_color, fields))
