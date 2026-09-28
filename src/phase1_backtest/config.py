"""Shared defaults for the Phase 1 analysis."""

from __future__ import annotations

PHASE1_TICKERS: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "AAPL",
    "JPM",
    "XOM",
    "JNJ",
    "PG",
    "WMT",
    "CAT",
)

DEFAULT_START_DATE = "2010-01-01"
TRADING_DAYS_PER_YEAR = 252
