"""Use the same daily performance definitions for every return table."""

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def excess_returns(daily_returns, risk_free):
    """Subtract an explicit annual rate or matching daily risk-free returns."""
    if np.isscalar(risk_free):
        if not np.isfinite(risk_free) or risk_free <= -1:
            raise ValueError("The annual risk-free rate must be finite and above -100%.")
        daily_rate = (1 + risk_free) ** (1 / TRADING_DAYS) - 1
        return daily_returns - daily_rate
    if not isinstance(risk_free, pd.Series) or not risk_free.index.equals(daily_returns.index):
        raise ValueError("Daily risk-free returns must match the evaluation dates.")
    if not np.isfinite(risk_free).all() or (risk_free <= -1).any():
        raise ValueError("Daily risk-free returns must be finite and above -100%.")
    return daily_returns.sub(risk_free, axis=0)


def summarize(daily_returns, risk_free=None):
    """risk_free is an annual decimal rate or an aligned series of daily returns."""
    if len(daily_returns) < 2 or daily_returns.shape[1] == 0:
        raise ValueError("Need at least two daily returns and one column.")
    daily_returns = daily_returns.astype(float)
    values = daily_returns.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < -1).any():
        raise ValueError("Returns must be finite and cannot be less than -100%.")
    growth = (1 + daily_returns).cumprod()
    total_return = growth.iloc[-1] - 1
    volatility = daily_returns.std(ddof=1) * np.sqrt(TRADING_DAYS)
    # Include the starting investment when a loss occurs on the first day.
    peak = growth.cummax().clip(lower=1.0)
    drawdown = growth / peak - 1
    sharpe = pd.Series(np.nan, index=daily_returns.columns)
    if risk_free is not None:
        excess = excess_returns(daily_returns, risk_free)
        # Constant columns can have a tiny rounding residual instead of zero deviation.
        deviation = excess.std(ddof=1).mask(excess.max().eq(excess.min()))
        sharpe = excess.mean() / deviation * np.sqrt(TRADING_DAYS)
    return pd.DataFrame({
        "total_return": total_return,
        "annualized_return": (1 + total_return) ** (TRADING_DAYS / len(daily_returns)) - 1,
        "annualized_volatility": volatility,
        "sharpe_ratio": sharpe,
        "maximum_drawdown": drawdown.min(),
        "win_rate": daily_returns.gt(0).mean(),
    })
