"""Combine an existing daily return table; never fetch or save observations."""

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from metrics import TRADING_DAYS, excess_returns, summarize


def analyze_portfolios(daily_returns, risk_free, benchmark="SPY"):
    """Fit long-only, daily-rebalanced portfolios to one shared historical sample."""
    if not np.isscalar(risk_free) or len(daily_returns.columns) < 2:
        raise ValueError("Supply a constant annual risk-free rate and at least two assets.")
    dates = daily_returns.index
    if (not isinstance(dates, pd.DatetimeIndex) or dates.hasnans or dates.has_duplicates
            or not dates.is_monotonic_increasing or daily_returns.columns.has_duplicates):
        raise ValueError("Return dates and asset labels must be unique and ordered.")
    asset_summary = summarize(daily_returns, risk_free)
    mean_return = daily_returns.mean() * TRADING_DAYS  # Arithmetic return, not compound growth.
    excess_mean = excess_returns(daily_returns, risk_free).mean() * TRADING_DAYS
    # Columns are assets; ddof=1 estimates sample covariance, including joint movement.
    covariance = np.cov(daily_returns.to_numpy(), rowvar=False, ddof=1) * TRADING_DAYS
    count = len(mean_return)
    equal_weights = np.full(count, 1 / count)

    def variance(weights):
        return weights @ covariance @ weights  # Combine individual risks and every pair's joint risk.

    def solve(objective, target=None, start=equal_weights):
        constraints = [{"type": "eq", "fun": lambda weights: weights.sum() - 1}]
        if target is not None and mean_return.max() > mean_return.min():
            constraints.append({"type": "eq", "fun": lambda weights: weights @ mean_return - target})
        solution = minimize(objective, start, method="SLSQP", bounds=[(0, 1)] * count,
                            constraints=constraints, options={"ftol": 1e-12, "maxiter": 1000})
        weights = solution.x
        if (not solution.success or not np.isfinite(solution.fun) or not np.isfinite(weights).all()
                or weights.min() < -1e-8 or weights.max() > 1 + 1e-8
                or abs(weights.sum() - 1) > 1e-8
                or (target is not None and abs(weights @ mean_return - target) > 1e-8)):
            raise ValueError(f"Portfolio optimization failed: {solution.message}")
        return weights

    minimum = solve(variance)
    if variance(minimum) <= 1e-14 or excess_mean.max() <= 0:
        raise ValueError("Need positive portfolio risk and at least one positive excess mean.")
    start = np.eye(count)[asset_summary["sharpe_ratio"].argmax()]  # Begin with a positive-Sharpe asset.
    maximum = solve(lambda weights: -(weights @ excess_mean) / np.sqrt(variance(weights)), start=start)
    # Trace only the upper frontier: returns at or above the minimum-risk portfolio.
    targets = np.linspace(minimum @ mean_return, mean_return.max(), 40)
    frontier = [solve(variance, target) for target in targets]
    generator = np.random.default_rng(42)  # Repeatable allocations of existing returns, not new prices.
    random_weights = generator.dirichlet(np.ones(count), size=3000)
    comparison = pd.DataFrame([minimum, maximum, equal_weights,
                               (daily_returns.columns == benchmark).astype(float)],
                              index=["Minimum variance", "Maximum Sharpe", "Equal weight", benchmark],
                              columns=daily_returns.columns)
    if benchmark not in daily_returns.columns:
        raise ValueError("The benchmark must be a column in the same return table.")
    correlation = daily_returns.corr()
    distinct_pairs = np.triu(np.ones((count, count)), k=1).astype(bool)  # Exclude repeats and self-pairs.
    pairs = correlation.where(distinct_pairs).stack()
    pairs = pairs.dropna().sort_values()
    asset_summary["expected_return"] = mean_return
    result = {"asset_summary": asset_summary, "correlation": correlation,
              "correlation_pairs": pairs.iloc[[0, -1]], "risk_free": risk_free,
              "period": f"{dates[0]:%Y-%m-%d} to {dates[-1]:%Y-%m-%d}",
              "covariance": pd.DataFrame(covariance, index=mean_return.index, columns=mean_return.index)}
    for name, weights in [("simulation", random_weights), ("frontier", frontier),
                          ("comparison", comparison)]:
        weights = pd.DataFrame(weights, columns=daily_returns.columns)
        # Sum each weight's contribution to portfolio variance, then take its square root.
        values = weights.to_numpy()
        volatility = np.sqrt((values @ covariance * values).sum(axis=1))
        result[name + "_weights"] = weights
        result[name] = pd.DataFrame({"expected_return": weights @ mean_return,
                                     "annualized_volatility": volatility,
                                     "sharpe_ratio": (weights @ excess_mean) / volatility})
    result["comparison_returns"] = daily_returns @ comparison.T
    result["comparison_summary"] = summarize(result["comparison_returns"], risk_free)
    result["comparison_summary"]["expected_return"] = result["comparison"]["expected_return"]
    return result
