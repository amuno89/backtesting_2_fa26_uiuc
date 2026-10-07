"""Apply supplied positions to subsequent daily returns, separately for each ticker."""

import numpy as np

from data import validate_prices


def equity_curve(daily_returns, initial_date):
    """Start at one on the preceding close, without adding a fake return day."""
    equity = (1 + daily_returns).cumprod()
    equity.loc[initial_date] = 1.0
    return equity.sort_index()


def backtest(prices, signals):
    """Signals are exposures decided at the close; cash earns zero and costs are excluded."""
    validate_prices(prices)
    if not signals.index.equals(prices.index) or not signals.columns.equals(prices.columns):
        raise ValueError("Signals and prices must have identical dates and ticker columns.")
    signals = signals.astype(float)
    held_positions = signals.shift(1)
    ready_dates = held_positions.dropna().index
    if ready_dates.empty:
        raise ValueError("No complete positions remain after shifting the signals.")
    start = prices.index.get_loc(ready_dates[0])
    held_positions = held_positions.iloc[start:]
    if len(held_positions) < 2 or not np.isfinite(held_positions.to_numpy()).all():
        raise ValueError("Need at least two evaluation days, with no position gaps.")
    # Warm-up ends once every ticker has a signal. Both comparisons start together.
    asset_returns = prices.pct_change(fill_method=None).iloc[start:]
    strategy_returns = held_positions * asset_returns
    initial_date = prices.index[start - 1]
    return {
        "held_positions": held_positions,
        "asset_returns": asset_returns,
        "strategy_returns": strategy_returns,
        "benchmark_returns": asset_returns.copy(),
        "equity": equity_curve(strategy_returns, initial_date),
        "benchmark_equity": equity_curve(asset_returns, initial_date),
    }
