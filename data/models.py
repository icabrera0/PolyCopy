from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from pydantic import BaseModel, Field


def _new_id() -> str:
    return str(uuid.uuid4())


class Trader(BaseModel):
    address: str
    username: str | None = None
    total_pnl_30d: float = 0.0
    num_trades_30d: int = 0
    last_active_timestamp: datetime
    win_rate: float = 0.0
    avg_position_size: float = 0.0
    quality_score: float = 0.0
    first_trade_timestamp: datetime | None = None
    num_markets_traded: int = 0
    max_single_trade_pnl: float = 0.0
    vol: float = 0.0
    num_open_positions: int = 0


class Position(BaseModel):
    market_id: str
    market_title: str
    outcome: str
    size: float
    entry_price: float
    timestamp_opened: datetime
    trader_address: str | None = None


class Market(BaseModel):
    market_id: str
    title: str
    closes_at: datetime
    current_price: float = 0.0
    liquidity: float = 0.0


class Signal(BaseModel):
    id: str = Field(default_factory=_new_id)
    market_id: str
    market_title: str
    outcome: str
    trader_count: int
    total_filtered_traders: int
    consensus_pct: float
    avg_entry_price: float
    market_closes_at: datetime
    signal_strength: Literal["STRONG", "MODERATE", "WEAK"]
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class PaperTrade(BaseModel):
    id: str = Field(default_factory=_new_id)
    market_id: str
    market_title: str
    outcome: str
    entry_price: float
    stake: float
    signal_strength: str
    consensus_pct: float
    trader_count: int
    status: Literal["OPEN", "CLOSED", "EXPIRED"] = "OPEN"
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: datetime | None = None
    resolution: str | None = None  # "WIN" / "LOSS" / "N/A"
    pnl: float | None = None
    exit_price: float | None = None


class DailyStats(BaseModel):
    date: str  # YYYY-MM-DD
    trades_opened: int = 0
    trades_closed: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    win_rate: float = 0.0
    strong_win_rate: float = 0.0
    moderate_win_rate: float = 0.0
