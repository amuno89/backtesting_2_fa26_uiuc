"""RSI mean reversion, independent of the Golden Cross strategy."""

import numpy as np
import pandas as pd


def mean_reversion(prices, period=14, entry=30, exit=50):
    """Return same-day decisions; the shared backtest applies them one day later."""
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("RSI period must be a positive integer.")
    if not 0 <= entry < exit <= 100:
        raise ValueError("RSI thresholds must satisfy 0 <= entry < exit <= 100.")
    changes = prices.diff()
    gains = changes.clip(lower=0)
    losses = -changes.clip(upper=0)
    # Wilder starts with the average of the first period price changes.
    average_gain = gains.iloc[1:period + 1].mean()
    average_loss = losses.iloc[1:period + 1].mean()
    signals = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    position = pd.Series(0.0, index=prices.columns)
    for day in range(period, len(prices)):
        if day > period:
            average_gain = (average_gain * (period - 1) + gains.iloc[day]) / period
            average_loss = (average_loss * (period - 1) + losses.iloc[day]) / period
        movement = average_gain + average_loss
        # RSI measures smoothed gains as a percentage of total price movement.
        rsi = 100 * average_gain / movement
        rsi = rsi.mask(movement.eq(0), 50.0)  # No price movement means neutral RSI.
        position[rsi < entry] = 1.0
        position[rsi >= exit] = 0.0
        # Between the thresholds, keep yesterday's position. Warm-up stays missing.
        signals.iloc[day] = position
    return signals
