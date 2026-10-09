import numpy as np
import pandas as pd


def golden_cross(prices, short=50, long=200):
    """1 when the short moving average is above the long one, else 0."""
    short_ma = prices.rolling(short).mean()
    long_ma = prices.rolling(long).mean()
    signals = (short_ma > long_ma).astype(float)
    signals[long_ma.isna()] = np.nan
    return signals