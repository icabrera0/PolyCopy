from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


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
    id: str
    market_id: str
    market_title: str
    outcome: str
    entry_price: float
    stake: float
    signal_strength: str
    consensus_pct: float
    trader_count: int
    status: Literal["OPEN", "CLOSED", "EXPIRED"]
    opened_at: datetime
    closed_at: datetime | None = None
    resolution: str | None = None
    pnl: float | None = None
    exit_price: float | None = None
