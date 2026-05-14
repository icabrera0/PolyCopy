import os
import pytest
from config.settings import Settings


def test_settings_defaults():
    s = Settings()
    assert s.polymarket_api_base == "https://clob.polymarket.com"
    assert s.polymarket_gamma_api == "https://gamma-api.polymarket.com"
    assert s.trader_category == "Crypto"
    assert s.top_traders_limit == 50
    assert s.polling_interval_seconds == 30
    assert s.min_trades_30d == 10
    assert s.min_avg_position_usd == 50.0
    assert s.min_win_rate == pytest.approx(0.40)
    assert s.max_single_trade_pnl_ratio == pytest.approx(0.80)
    assert s.min_account_age_days == 30
    assert s.min_market_diversity == 3
    assert s.last_active_days == 14
    assert s.consensus_strong_threshold == pytest.approx(0.70)
    assert s.consensus_moderate_threshold == pytest.approx(0.50)
    assert s.consensus_weak_threshold == pytest.approx(0.35)
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
