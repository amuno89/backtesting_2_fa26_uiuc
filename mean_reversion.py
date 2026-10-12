"""RSI mean reversion, independent of the Golden Cross strategy."""

import numpy as np
import pandas as pd


def mean_reversion(prices, period=14, entry=30, exit=50):
    """Return daily decisions: 1 invested, 0 cash, and NaN during warm-up."""
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("RSI period must be a positive integer.")
    if not 0 <= entry < exit <= 100:
        raise ValueError("RSI thresholds must satisfy 0 <= entry < exit <= 100.")
    changes = prices.diff()
    gains = changes.clip(lower=0)
    losses = -changes.clip(upper=0)
    # Seed Wilder's smoothing with the first period daily gains and losses.
    average_gain = gains.iloc[1:period + 1].mean()
    average_loss = losses.iloc[1:period + 1].mean()
    signals = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    positions = pd.Series(0.0, index=prices.columns)
    for day in range(period, len(prices)):
        if day > period:
            average_gain = (average_gain * (period - 1) + gains.iloc[day]) / period
            average_loss = (average_loss * (period - 1) + losses.iloc[day]) / period
        total_movement = average_gain + average_loss
        # RSI measures smoothed gains as a percentage of total price movement.
        rsi = 100 * average_gain / total_movement
        rsi = rsi.mask(total_movement.eq(0), 50.0)  # Both averages zero: neutral RSI.
        positions[rsi < entry] = 1.0
        positions[rsi >= exit] = 0.0
        # Keep positions between the thresholds; only the backtest delays execution.
        signals.iloc[day] = positions
    return signals
