from __future__ import annotations

import asyncio
import time

import pandas as pd
import plotly.express as px
import streamlit as st

from config.settings import settings
from data import db

_DB = str(settings.db_path)

st.set_page_config(page_title="PolyCopy Dashboard", page_icon="📈", layout="wide")


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@st.cache_data(ttl=30)
def _trades_df():
    trades = _run(db.get_all_trades(_DB, limit=500))
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([t.model_dump() for t in trades])


@st.cache_data(ttl=30)
def _open_trades_df():
    trades = _run(db.get_open_trades(_DB))
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([t.model_dump() for t in trades])


@st.cache_data(ttl=30)
def _signals_df():
    signals = _run(db.get_recent_signals(_DB, limit=100))
    if not signals:
        return pd.DataFrame()
    return pd.DataFrame([s.model_dump() for s in signals])


@st.cache_data(ttl=30)
def _traders_df():
    traders = _run(db.get_traders(_DB))
    if not traders:
        return pd.DataFrame()
    return pd.DataFrame([t.model_dump() for t in traders])


@st.cache_data(ttl=30)
def _daily_df():
    stats = _run(db.get_daily_stats(_DB, limit=30))
    if not stats:
        return pd.DataFrame()
    return pd.DataFrame([s.model_dump() for s in stats])


# ── Sidebar nav ──────────────────────────────────────────────────────────────
page = st.sidebar.radio(
    "Navigation",
    ["📊 Overview", "🔴 Live Signals", "📂 Open Trades", "✅ Trade History", "👥 Trader Leaderboard", "⚙️ Settings"],
)

# ── Overview ─────────────────────────────────────────────────────────────────
if page == "📊 Overview":
    st.title("📊 Overview")

    trades = _trades_df()
    daily = _daily_df()
    open_df = _open_trades_df()

    closed = trades[trades["status"] == "CLOSED"] if not trades.empty else pd.DataFrame()
    wins = closed[closed["resolution"] == "WIN"] if not closed.empty else pd.DataFrame()

    col1, col2, col3, col4 = st.columns(4)
    total_pnl = closed["pnl"].sum() if not closed.empty else 0.0
    win_rate = len(wins) / len(closed) * 100 if len(closed) > 0 else 0.0
    col1.metric("Total Paper PnL", f"${total_pnl:+.2f}")
    col2.metric("Win Rate", f"{win_rate:.1f}%")
    col3.metric("Total Trades", len(trades) if not trades.empty else 0)
    col4.metric("Open Positions", len(open_df) if not open_df.empty else 0)

    if not closed.empty and "pnl" in closed.columns:
        closed_sorted = closed.sort_values("opened_at")
        closed_sorted["cumulative_pnl"] = closed_sorted["pnl"].cumsum()
        fig = px.line(closed_sorted, x="opened_at", y="cumulative_pnl", title="Cumulative PnL")
        st.plotly_chart(fig, use_container_width=True)

    if not daily.empty:
        fig2 = px.bar(daily.sort_values("date"), x="date", y="total_pnl", title="Daily PnL", color="total_pnl",
                      color_continuous_scale=["red", "green"])
        st.plotly_chart(fig2, use_container_width=True)

# ── Live Signals ──────────────────────────────────────────────────────────────
elif page == "🔴 Live Signals":
    st.title("🔴 Live Signals")
    signals = _signals_df()
    if signals.empty:
        st.info("No signals yet.")
    else:
        def _color_strength(val):
            return {"STRONG": "background-color:#00FF8833", "MODERATE": "background-color:#FFFF0033", "WEAK": "background-color:#2196F333"}.get(val, "")
        cols = ["generated_at", "market_title", "outcome", "signal_strength", "consensus_pct", "trader_count", "avg_entry_price"]
        display = signals[[c for c in cols if c in signals.columns]].head(50)
        st.dataframe(display.style.applymap(_color_strength, subset=["signal_strength"]), use_container_width=True)

# ── Open Trades ───────────────────────────────────────────────────────────────
elif page == "📂 Open Trades":
    st.title("📂 Open Trades")
    open_df = _open_trades_df()
    if open_df.empty:
        st.info("No open trades.")
    else:
        cols = ["market_title", "outcome", "signal_strength", "entry_price", "stake", "consensus_pct", "opened_at"]
        st.dataframe(open_df[[c for c in cols if c in open_df.columns]], use_container_width=True)

# ── Trade History ─────────────────────────────────────────────────────────────
elif page == "✅ Trade History":
    st.title("✅ Trade History")
    trades = _trades_df()
    if trades.empty:
        st.info("No trades yet.")
    else:
        col1, col2 = st.columns(2)
        strength_filter = col1.multiselect("Signal Strength", ["STRONG", "MODERATE", "WEAK"], default=["STRONG", "MODERATE", "WEAK"])
        result_filter = col2.multiselect("Result", ["WIN", "LOSS", "N/A"], default=["WIN", "LOSS", "N/A"])
        filtered = trades[
            trades["signal_strength"].isin(strength_filter) &
            trades["resolution"].isin(result_filter + [None])
        ] if not trades.empty else trades
        cols = ["opened_at", "market_title", "outcome", "signal_strength", "resolution", "entry_price", "exit_price", "pnl"]
        st.dataframe(filtered[[c for c in cols if c in filtered.columns]], use_container_width=True)

# ── Trader Leaderboard ────────────────────────────────────────────────────────
elif page == "👥 Trader Leaderboard":
    st.title("👥 Filtered Trader Leaderboard")
    traders = _traders_df()
    if traders.empty:
        st.info("No trader data yet.")
    else:
        traders["address_short"] = traders["address"].str[:10] + "..."
        cols = ["address_short", "quality_score", "total_pnl_30d", "win_rate", "num_trades_30d", "last_active_timestamp"]
        st.dataframe(traders[[c for c in cols if c in traders.columns]].head(50), use_container_width=True)

# ── Settings ──────────────────────────────────────────────────────────────────
elif page == "⚙️ Settings":
    st.title("⚙️ Active Configuration")
    cfg = {
        "Polling interval": f"{settings.polling_interval_seconds}s",
        "Top traders limit": settings.top_traders_limit,
        "Paper stake per trade": f"${settings.paper_stake_per_trade}",
        "STRONG threshold": f"{settings.consensus_strong_threshold * 100:.0f}%",
        "MODERATE threshold": f"{settings.consensus_moderate_threshold * 100:.0f}%",
        "WEAK threshold": f"{settings.consensus_weak_threshold * 100:.0f}%",
        "Min trades (30d)": settings.min_trades_30d,
        "Min win rate": f"{settings.min_win_rate * 100:.0f}%",
        "Min avg position USD": f"${settings.min_avg_position_usd}",
        "Min account age (days)": settings.min_account_age_days,
        "Last active (days)": settings.last_active_days,
        "Min market diversity": settings.min_market_diversity,
        "Discord notifications": "Enabled" if settings.discord_webhook_url else "Disabled",
    }
    st.table(pd.DataFrame(list(cfg.items()), columns=["Setting", "Value"]))

# ── Auto-refresh ──────────────────────────────────────────────────────────────
st.sidebar.markdown("---")
if st.sidebar.checkbox("Auto-refresh (30s)", value=False):
    time.sleep(30)
    st.cache_data.clear()
    st.rerun()
