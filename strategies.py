import numpy as np


def golden_cross(prices, short=50, long=200):
    """1 when the short moving average is above the long one, else 0."""
    short_ma = prices.rolling(short).mean()
    long_ma = prices.rolling(long).mean()
    signals = (short_ma > long_ma).astype(float)
    signals[long_ma.isna()] = np.nan
    return signals


def momentum(prices, lookback=252, skip=21):
    """1 if the return from 12 months ago to 1 month ago is positive, else 0."""
    past_return = prices.shift(skip) / prices.shift(lookback) - 1
    signals = (past_return > 0).astype(float)
    signals[past_return.isna()] = np.nan
    return signals
