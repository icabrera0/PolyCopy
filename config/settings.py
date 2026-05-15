from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # Polymarket
    polymarket_api_base: str = "https://clob.polymarket.com"
    polymarket_data_api: str = "https://data-api.polymarket.com"
    polymarket_gamma_api: str = "https://gamma-api.polymarket.com"
    trader_category: str = "Crypto"
    top_traders_limit: int = 50
    polling_interval_seconds: int = 30
    leaderboard_time_period: str = "WEEK"

    # Filtering
    min_trades: int = 5
    min_pnl: float = 100.0
    min_vol: float = 1000.0
    min_open_positions: int = 1
    max_single_trade_pnl_ratio: float = 0.80
    min_market_diversity: int = 3
    last_active_days: int = 14

    # Consensus
    consensus_strong_threshold: float = 0.70
    consensus_moderate_threshold: float = 0.50
    consensus_weak_threshold: float = 0.35
    min_consensus_traders: int = 3
    min_market_time_remaining_seconds: int = 120
    max_market_horizon_hours: int = 24

    # Paper Trading
    paper_stake_per_trade: float = 100.0
    paper_currency: str = "USD"

    # Discord
    discord_webhook_url: str = ""
    discord_notify_weak_signals: bool = False

    # Misc
    log_level: str = "INFO"
    db_path: Path = Path("./data/polymarket_bot.db")
    dashboard_port: int = 8501


settings = Settings()
