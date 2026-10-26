"""Rebalance virtual strategy accounts using existing, already delayed positions."""

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from data import TICKERS


def rebalance(capital, holdings, targets, fee):
    """Pay for actual purchases and sales, including changes caused by price drift."""
    def balance(remaining):
        trading_cost = fee * np.abs(remaining * targets - holdings).sum()
        return remaining + trading_cost - capital

    # Find the capital left after fees; target purchases must be affordable.
    remaining = brentq(balance, 0, capital, xtol=1e-14)
    return remaining, remaining * targets


def simulate(positions, asset_returns, cost_bps, scores=None, dynamic=False):
    """Monthly allocation; daily ticker targets; cash earns zero. No files are saved."""
    names = list(positions)
    dates = asset_returns.index
    if not names or list(asset_returns.columns) != TICKERS or len(dates) < 2:
        raise ValueError("Supply candidate positions and the ten approved asset returns.")
    if (not isinstance(dates, pd.DatetimeIndex) or dates.hasnans
            or dates.has_duplicates or not dates.is_monotonic_increasing):
        raise ValueError("Return dates must be present, unique, and increasing.")
    if not np.isfinite(cost_bps) or not 0 <= cost_bps < 10000:
        raise ValueError("One-way cost must be finite and between 0 and 10,000 basis points.")
    values = asset_returns.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= -1).any():
        raise ValueError("Asset returns must be finite and greater than -100%.")
    for table in positions.values():
        if not table.index.equals(dates) or not table.columns.equals(asset_returns.columns):
            raise ValueError("Positions must match the asset return dates and tickers.")
        if (not np.isfinite(table.to_numpy()).all()
                or not table.ge(0).all(axis=None) or not table.le(1).all(axis=None)):
            raise ValueError("Ticker exposures must be finite fractions between zero and one.")
    if dynamic and (len(names) != 5 or scores is None
                    or list(scores.columns) != names or not scores.index.equals(dates)):
        raise ValueError("Dynamic allocation needs five matching standalone return series.")
    if dynamic and (not np.isfinite(scores.to_numpy()).all() or scores.le(-1).any(axis=None)):
        raise ValueError("Ranking returns must be finite and greater than -100%.")
    targets = np.stack([positions[name].to_numpy() / 10 for name in names], axis=1)
    count = len(names)
    capital = np.full(count, 1 / count)
    holdings = np.zeros((count, 10))
    records, weights, exposures = [], [], []
    fee = cost_bps / 10000
    months = dates.to_period("M")
    for day, month in enumerate(months):
        before = capital.sum()
        old_holdings = holdings.copy()
        if day == 0 or month != months[day - 1]:
            allocation = np.full(count, 1 / count)
            if dynamic and day >= 63:
                # Use only the previous 63 days; tied ranks receive equal weights.
                trailing = (1 + scores.iloc[day - 63:day]).prod() - 1
                ranks = trailing.rank(ascending=False, method="average")
                allocation = (0.35 - 0.05 * ranks).to_numpy()
            joint_targets = targets[day] * allocation[:, None]
            remaining, holdings = rebalance(before, holdings, joint_targets, fee)
            capital = remaining * allocation
        else:
            for candidate in range(count):
                capital[candidate], holdings[candidate] = rebalance(
                    capital[candidate], holdings[candidate], targets[day, candidate], fee)
        after_fees = capital.sum()
        turnover = np.abs(holdings - old_holdings).sum() / before
        weights.append(capital / after_fees)
        exposures.append(holdings.sum(axis=0) / after_fees)
        # Fees are charged once on these trades, not again through ranking returns.
        capital += (holdings * values[day]).sum(axis=1)
        holdings *= 1 + values[day]
        records.append((capital.sum() / before - 1, turnover, (before - after_fees) / before))
    result = pd.DataFrame(records, index=dates, columns=["returns", "turnover", "cost"])
    return {"returns": result["returns"], "turnover": result["turnover"], "cost": result["cost"],
            "weights": pd.DataFrame(weights, index=dates, columns=names),
            "exposure": pd.DataFrame(exposures, index=dates, columns=TICKERS)}
