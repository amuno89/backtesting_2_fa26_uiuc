"""Five daily signal variants using the same approved adjusted-price table."""

import numpy as np
import pandas as pd

from data import validate_prices


def v2_signals(prices):
    """Return ticker exposures from zero to one; the backtest delays them once."""
    validate_prices(prices)
    fast_average = prices.ewm(span=12, adjust=False, min_periods=12).mean()
    slow_average = prices.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = fast_average - slow_average
    signal_line = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    # Yesterday's rolling channel excludes today's close from the threshold.
    high = prices.rolling(20).max().shift(1)
    low = prices.rolling(10).min().shift(1)
    middle = prices.rolling(20).mean()
    lower_band = middle - 2 * prices.rolling(20).std(ddof=0)
    volatility = prices.pct_change(fill_method=None).rolling(20).std(ddof=1) * np.sqrt(252)
    active = (macd > signal_line) & (prices >= low)
    reentry = (prices.shift(1) < lower_band.shift(1)) & (prices >= lower_band)
    reentry &= (prices > prices.shift(1)) & (prices < middle) & (prices >= low)
    signals = {"C1": active.astype(float).mask(signal_line.isna())}
    for name in ["C3", "C4", "C5"]:
        signals[name] = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    # Zero volatility gives full sizing; higher volatility can only reduce it.
    scale = (0.20 / volatility).clip(upper=1.0)
    signals["C6"] = signals["C1"] * scale
    partial = pd.Series(0.0, index=prices.columns)  # C3 starts at half size before confirmation.
    breakout = partial.copy()  # C4 holds until the lower channel is crossed.
    rebound = partial.copy()  # C5 holds a rebound until recovery or a downside exit.
    # The 26-day MACD plus its 9-day signal first becomes available on day 34.
    for day in range(33, len(prices)):
        close = prices.iloc[day]
        bullish = active.iloc[day]
        above_high = close > high.iloc[day]
        below_low = close < low.iloc[day]
        partial[bullish & partial.eq(0)] = 0.5
        partial[bullish & above_high] = 1.0
        partial[~bullish] = 0.0
        breakout[above_high] = 1.0
        breakout[below_low] = 0.0
        rebound[reentry.iloc[day]] = 1.0
        rebound[(close >= middle.iloc[day]) | below_low] = 0.0
        signals["C3"].iloc[day] = partial
        signals["C4"].iloc[day] = breakout
        signals["C5"].iloc[day] = rebound
    return signals
