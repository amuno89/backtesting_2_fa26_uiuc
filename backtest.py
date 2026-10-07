"""Apply supplied positions to subsequent daily returns, separately for each ticker."""

import numpy as np

from data import validate_prices


def backtest(prices, signals):
    """Signals are exposures decided at the close; cash earns zero and costs are excluded."""
    validate_prices(prices)
    if not signals.index.equals(prices.index) or not signals.columns.equals(prices.columns):
        raise ValueError("Signals and prices must have identical dates and ticker columns.")
    signals = signals.astype(float)
    held_positions = signals.shift(1)
    ready = held_positions.notna().all(axis=1)
    if not ready.any():
        raise ValueError("No complete positions remain after shifting the signals.")
    start = max(1, int(np.flatnonzero(ready)[0]))
    held_positions = held_positions.iloc[start:]
    if len(held_positions) < 2 or not np.isfinite(held_positions.to_numpy()).all():
        raise ValueError("Need at least two evaluation days, with no position gaps.")
    # Warm-up ends once every ticker has a signal. Both comparisons start together.
    asset_returns = prices.pct_change(fill_method=None).iloc[start:]
    strategy_returns = held_positions * asset_returns
    equity = (1 + strategy_returns).cumprod()
    benchmark_equity = (1 + asset_returns).cumprod()
    # The initial value belongs to the preceding close, not to a fake zero-return day.
    initial_date = prices.index[start - 1]
    equity.loc[initial_date] = 1.0
    benchmark_equity.loc[initial_date] = 1.0
    return {
        "held_positions": held_positions,
        "asset_returns": asset_returns,
        "strategy_returns": strategy_returns,
        "benchmark_returns": asset_returns.copy(),
        "equity": equity.sort_index(),
        "benchmark_equity": benchmark_equity.sort_index(),
    }
