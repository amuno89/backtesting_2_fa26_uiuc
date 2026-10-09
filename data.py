"""Read the approved local dataset without changing it or contacting a provider."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as calendars

TICKERS = ["SPY", "QQQ", "IWM", "AAPL", "JPM", "XOM", "JNJ", "PG", "WMT", "CAT"]


def validate_prices(prices):
    """Reject unusable observations rather than silently filling or dropping them."""
    dates = prices.index
    if len(prices) < 3 or list(prices.columns) != TICKERS:
        raise ValueError("Expected at least three dates and the ten approved ticker columns.")
    if not isinstance(dates, pd.DatetimeIndex) or dates.tz is not None:
        raise ValueError("Dates must be a timezone-free DatetimeIndex.")
    if dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError("Dates must be present, unique, and increasing.")
    if not all(pd.api.types.is_numeric_dtype(dtype) for dtype in prices.dtypes):
        raise ValueError("Price columns must contain numbers, not text.")
    values = prices.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Adjusted prices must be finite, positive, and complete.")
    exchange = calendars.get_calendar("NYSE")
    sessions = exchange.valid_days(dates[0], dates[-1]).tz_localize(None)
    if not dates.equals(sessions):
        raise ValueError("Dates contain missing NYSE sessions or unexpected timestamps.")


def load_prices(data_folder):
    """Read adjusted prices and verify them against the existing download record."""
    folder = Path(data_folder)
    raw_path = folder / "raw" / "daily_ohlcv.csv"
    report_path = folder / "quality" / "quality_report.json"
    report = json.loads(report_path.read_text())
    checksum = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    if checksum != report["source_sha256"]:
        raise ValueError("The raw data no longer matches its recorded checksum.")
    prices = pd.read_csv(folder / "cleaned" / "adjusted_close.csv", index_col="date",
                         parse_dates=["date"])
    validate_prices(prices)
    raw = pd.read_csv(raw_path, parse_dates=["date"])
    recorded_prices = raw.pivot(index="date", columns="ticker", values="adj_close")
    if set(recorded_prices.columns) != set(TICKERS):
        raise ValueError("The raw file does not contain exactly the approved tickers.")
    recorded_prices = recorded_prices.loc[:, TICKERS]
    if not prices.equals(recorded_prices):
        raise ValueError("Cleaned prices differ from the raw adjusted-close observations.")
    # Historical prices already include adjustments: never apply split factors again.
    return prices
