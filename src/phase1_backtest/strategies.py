"""Look-ahead-safe strategy signal definitions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pandas_market_calendars as market_calendars


@dataclass(frozen=True)
class StrategySignals:
    """Decision-date targets and the data used to produce them."""

    name: str
    target_weights: pd.DataFrame
    eligibility: pd.DataFrame
    rebalance: pd.Series
    indicators: dict[str, pd.DataFrame]


def validate_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Return numeric prices after enforcing backtest input invariants."""

    if not isinstance(prices, pd.DataFrame) or prices.empty:
        raise ValueError("prices must be a non-empty pandas DataFrame.")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("prices must use a DatetimeIndex.")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("price dates must be unique and increasing.")
    if prices.columns.has_duplicates:
        raise ValueError("price ticker columns must be unique.")
    numeric = prices.apply(pd.to_numeric, errors="coerce").astype(float)
    if numeric.isna().any().any():
        missing = int(numeric.isna().sum().sum())
        raise ValueError(f"prices contain {missing} missing values; prices are never imputed.")
    if numeric.le(0).any().any():
        raise ValueError("prices must be strictly positive.")
    return numeric


def _equal_weight(eligibility: pd.DataFrame) -> pd.DataFrame:
    active = eligibility.fillna(False).astype(bool)
    count = active.sum(axis=1).replace(0, np.nan)
    return active.astype(float).div(count, axis=0).fillna(0.0)


def _target_changes(target: pd.DataFrame) -> pd.Series:
    previous = target.shift(1).fillna(0.0)
    changes = target.ne(previous).any(axis=1)
    changes.name = "rebalance"
    return changes


def _nyse_month_ends(index: pd.DatetimeIndex) -> pd.Series:
    """Flag actual NYSE month-ends, never an arbitrary terminal sample row."""

    calendar = market_calendars.get_calendar("NYSE")
    start = index[0].to_period("M").start_time
    end = index[-1].to_period("M").end_time.normalize()
    sessions = pd.DatetimeIndex(
        calendar.valid_days(start_date=start, end_date=end)
    ).tz_convert(None).normalize()
    session_months = sessions.to_period("M")
    final_sessions = pd.Series(sessions, index=sessions).groupby(session_months).max()
    return pd.Series(index.isin(final_sessions.to_numpy()), index=index, name="rebalance")


def sma_crossover(
    prices: pd.DataFrame,
    *,
    short_window: int = 50,
    long_window: int = 200,
) -> StrategySignals:
    """Go long assets whose short moving average exceeds the long average."""

    prices = validate_prices(prices)
    if short_window <= 0 or long_window <= 0 or short_window >= long_window:
        raise ValueError("windows must be positive and short_window must be less than long_window.")
    short_ma = prices.rolling(short_window, min_periods=short_window).mean()
    long_ma = prices.rolling(long_window, min_periods=long_window).mean()
    eligibility = short_ma.gt(long_ma) & long_ma.notna()
    target = _equal_weight(eligibility)
    return StrategySignals(
        name="sma_crossover",
        target_weights=target,
        eligibility=eligibility,
        rebalance=_target_changes(target),
        indicators={f"sma_{short_window}": short_ma, f"sma_{long_window}": long_ma},
    )


def momentum(
    prices: pd.DataFrame,
    *,
    lookback: int = 252,
    top_n: int = 3,
) -> StrategySignals:
    """Hold the top trailing-return assets, rebalanced at calendar month-end."""

    prices = validate_prices(prices)
    if lookback <= 0:
        raise ValueError("lookback must be positive.")
    if top_n <= 0 or top_n > len(prices.columns):
        raise ValueError("top_n must be between one and the number of tickers.")

    scores = prices.div(prices.shift(lookback)).sub(1.0)
    ranks = scores.rank(axis=1, ascending=False, method="first", na_option="bottom")
    selected_each_day = scores.notna() & ranks.le(top_n)
    candidate_targets = _equal_weight(selected_each_day)

    month_end = _nyse_month_ends(prices.index)
    rebalance = month_end & scores.notna().any(axis=1)

    target = candidate_targets.where(rebalance, np.nan).ffill().fillna(0.0)
    eligibility = target.gt(0.0)
    return StrategySignals(
        name="momentum_12m",
        target_weights=target,
        eligibility=eligibility,
        rebalance=rebalance,
        indicators={f"momentum_{lookback}": scores},
    )


def _wilder_rsi_series(prices: pd.Series, window: int) -> pd.Series:
    delta = prices.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    result = pd.Series(np.nan, index=prices.index, dtype=float)
    if len(prices) <= window:
        return result

    average_gain = float(gains.iloc[1 : window + 1].mean())
    average_loss = float(losses.iloc[1 : window + 1].mean())

    def rsi_value(avg_gain: float, avg_loss: float) -> float:
        if avg_gain == 0.0 and avg_loss == 0.0:
            return 50.0
        if avg_loss == 0.0:
            return 100.0
        if avg_gain == 0.0:
            return 0.0
        relative_strength = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + relative_strength))

    result.iloc[window] = rsi_value(average_gain, average_loss)
    for position in range(window + 1, len(prices)):
        average_gain = ((window - 1) * average_gain + float(gains.iloc[position])) / window
        average_loss = ((window - 1) * average_loss + float(losses.iloc[position])) / window
        result.iloc[position] = rsi_value(average_gain, average_loss)
    return result


def relative_strength_index(prices: pd.DataFrame, *, window: int = 14) -> pd.DataFrame:
    """Calculate Wilder's RSI, with flat price histories defined as RSI 50."""

    prices = validate_prices(prices)
    if window <= 0:
        raise ValueError("window must be positive.")
    return prices.apply(_wilder_rsi_series, window=window)


def rsi_mean_reversion(
    prices: pd.DataFrame,
    *,
    window: int = 14,
    oversold_threshold: float = 30.0,
) -> StrategySignals:
    """Hold assets only while their RSI is below the oversold threshold."""

    if not 0.0 < oversold_threshold < 100.0:
        raise ValueError("oversold_threshold must be between 0 and 100.")
    rsi = relative_strength_index(prices, window=window)
    eligibility = rsi.lt(oversold_threshold) & rsi.notna()
    target = _equal_weight(eligibility)
    return StrategySignals(
        name="rsi_mean_reversion",
        target_weights=target,
        eligibility=eligibility,
        rebalance=_target_changes(target),
        indicators={f"rsi_{window}": rsi},
    )
