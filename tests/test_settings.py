import os
import pytest
from config.settings import Settings


def test_settings_defaults(monkeypatch):
    # Clear all env vars that pydantic-settings would pick up
    for var in [
        "POLYMARKET_API_BASE", "POLYMARKET_GAMMA_API", "POLYMARKET_DATA_API",
        "TRADER_CATEGORY", "TOP_TRADERS_LIMIT", "POLLING_INTERVAL_SECONDS",
        "LEADERBOARD_TIME_PERIOD",
        "MIN_TRADES", "MIN_PNL", "MIN_VOL", "MIN_OPEN_POSITIONS",
        "MAX_SINGLE_TRADE_PNL_RATIO", "MIN_MARKET_DIVERSITY", "LAST_ACTIVE_DAYS",
        "CONSENSUS_STRONG_THRESHOLD", "CONSENSUS_MODERATE_THRESHOLD",
        "CONSENSUS_WEAK_THRESHOLD", "MIN_CONSENSUS_TRADERS",
        "MIN_MARKET_TIME_REMAINING_SECONDS",
        "MAX_MARKET_HORIZON_HOURS", "PAPER_STAKE_PER_TRADE", "PAPER_CURRENCY",
        "DISCORD_WEBHOOK_URL", "DISCORD_NOTIFY_WEAK_SIGNALS",
        "LOG_LEVEL", "DB_PATH", "DASHBOARD_PORT",
    ]:
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.polymarket_api_base == "https://clob.polymarket.com"
    assert s.polymarket_gamma_api == "https://gamma-api.polymarket.com"
    assert s.polymarket_data_api == "https://data-api.polymarket.com"
    assert s.trader_category == "Crypto"
    assert s.top_traders_limit == 50
    assert s.polling_interval_seconds == 30
    assert s.leaderboard_time_period == "WEEK"
    assert s.min_trades == 5
    assert s.min_pnl == pytest.approx(100.0)
    assert s.min_vol == pytest.approx(1000.0)
    assert s.min_open_positions == 1
    assert s.max_single_trade_pnl_ratio == pytest.approx(0.80)
    assert s.min_market_diversity == 3
    assert s.last_active_days == 14
    assert s.consensus_strong_threshold == pytest.approx(0.70)
    assert s.consensus_moderate_threshold == pytest.approx(0.50)
    assert s.consensus_weak_threshold == pytest.approx(0.35)
    assert s.min_consensus_traders == 3
    assert s.min_market_time_remaining_seconds == 120
    assert s.max_market_horizon_hours == 24
    assert s.paper_stake_per_trade == pytest.approx(100.0)
    assert s.paper_currency == "USD"
    assert s.discord_webhook_url == ""
    assert s.discord_notify_weak_signals is False
    assert s.log_level == "INFO"
    assert s.dashboard_port == 8501


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("TOP_TRADERS_LIMIT", "25")
    monkeypatch.setenv("POLLING_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.top_traders_limit == 25
    assert s.polling_interval_seconds == 60
    assert s.log_level == "DEBUG"
