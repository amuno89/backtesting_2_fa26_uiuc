"""Portfolio simulation and performance measurement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from phase1_backtest.config import TRADING_DAYS_PER_YEAR
from phase1_backtest.strategies import StrategySignals, validate_prices


@dataclass(frozen=True)
class BacktestResult:
    """Complete time-series output for one strategy."""

    name: str
    daily: pd.DataFrame
    target_weights: pd.DataFrame
    held_weights: pd.DataFrame
    end_of_day_weights: pd.DataFrame


def _validate_targets(prices: pd.DataFrame, signals: StrategySignals) -> None:
    target = signals.target_weights
    if not target.index.equals(prices.index) or not target.columns.equals(prices.columns):
        raise ValueError("target weights must have the same index and columns as prices.")
    if target.isna().any().any() or not np.isfinite(target.to_numpy()).all():
        raise ValueError("target weights must be finite and non-null.")
    if target.lt(-1e-12).any().any():
        raise ValueError("target weights cannot be negative.")
    if target.sum(axis=1).gt(1.0 + 1e-10).any():
        raise ValueError("target weights cannot exceed 100% gross exposure.")
    if not signals.rebalance.index.equals(prices.index):
        raise ValueError("rebalance flags must use the price index.")

    changes = target.ne(target.shift(1).fillna(0.0)).any(axis=1)
    missing_rebalance = changes & ~signals.rebalance.astype(bool)
    if missing_rebalance.any():
        first = missing_rebalance.index[missing_rebalance][0]
        raise ValueError(f"target changes without a rebalance flag on {first.date()}.")


def run_strategy(
    prices: pd.DataFrame,
    signals: StrategySignals,
    *,
    transaction_cost_bps: float = 0.0,
    charge_initial_trade: bool = True,
) -> BacktestResult:
    """Simulate close-to-close holdings with decisions made after each close.

    A target observed at close ``t`` is held over ``t`` to ``t+1``. Between
    rebalance events weights drift with asset returns, so an unchanged target
    does not imply daily rebalancing.
    """

    prices = validate_prices(prices)
    if transaction_cost_bps < 0:
        raise ValueError("transaction_cost_bps cannot be negative.")
    _validate_targets(prices, signals)

    target = signals.target_weights.astype(float)
    rebalance_schedule = signals.rebalance.astype(bool)
    index, columns = prices.index, prices.columns
    held = pd.DataFrame(0.0, index=index, columns=columns)
    ending = pd.DataFrame(0.0, index=index, columns=columns)
    daily = pd.DataFrame(
        0.0,
        index=index,
        columns=[
            "gross_return",
            "transaction_cost",
            "transaction_cost_return",
            "net_return",
            "equity",
            "turnover",
            "gross_exposure",
        ],
    )
    daily["rebalance"] = False

    weights = np.zeros(len(columns), dtype=float)
    equity = 1.0
    has_traded = False
    cost_rate = transaction_cost_bps / 10_000.0

    for position, timestamp in enumerate(index):
        held.iloc[position] = weights
        equity_before = equity

        if position == 0:
            relatives = np.ones(len(columns), dtype=float)
        else:
            relatives = prices.iloc[position].to_numpy() / prices.iloc[position - 1].to_numpy()
        if not np.isfinite(relatives[weights > 1e-12]).all():
            raise ValueError(f"A held asset has a missing return on {timestamp.date()}.")

        cash_weight = 1.0 - float(weights.sum())
        portfolio_relative = cash_weight + float(np.dot(weights, relatives))
        if not np.isfinite(portfolio_relative) or portfolio_relative <= 0:
            raise ValueError(f"Portfolio value is invalid on {timestamp.date()}.")
        gross_return = portfolio_relative - 1.0
        pretrade_equity = equity_before * portfolio_relative
        pretrade_weights = weights * relatives / portfolio_relative

        turnover = 0.0
        cost = 0.0
        did_rebalance = bool(rebalance_schedule.iloc[position])
        if did_rebalance:
            new_target = target.iloc[position].to_numpy(dtype=float)
            turnover = float(np.abs(new_target - pretrade_weights).sum())
            should_charge = charge_initial_trade or has_traded
            if should_charge:
                cost = pretrade_equity * cost_rate * turnover
            weights = new_target
            has_traded = has_traded or turnover > 1e-12
        else:
            weights = pretrade_weights

        equity = pretrade_equity - cost
        if equity <= 0:
            raise ValueError(f"Transaction costs exhausted the portfolio on {timestamp.date()}.")
        net_return = equity / equity_before - 1.0

        ending.iloc[position] = weights
        daily.loc[timestamp, "gross_return"] = gross_return
        daily.loc[timestamp, "transaction_cost"] = cost
        daily.loc[timestamp, "transaction_cost_return"] = cost / equity_before
        daily.loc[timestamp, "net_return"] = net_return
        daily.loc[timestamp, "equity"] = equity
        daily.loc[timestamp, "turnover"] = turnover
        daily.loc[timestamp, "gross_exposure"] = float(weights.sum())
        daily.loc[timestamp, "rebalance"] = did_rebalance

    return BacktestResult(
        name=signals.name,
        daily=daily,
        target_weights=target,
        held_weights=held,
        end_of_day_weights=ending,
    )


def buy_and_hold(
    prices: pd.DataFrame,
    *,
    initial_weights: pd.Series | None = None,
    transaction_cost_bps: float = 0.0,
    charge_initial_trade: bool = True,
) -> BacktestResult:
    """Buy once at the first close and keep a fixed number of shares."""

    prices = validate_prices(prices)
    if transaction_cost_bps < 0:
        raise ValueError("transaction_cost_bps cannot be negative.")
    if initial_weights is None:
        allocation = pd.Series(1.0 / len(prices.columns), index=prices.columns)
    else:
        allocation = initial_weights.reindex(prices.columns).astype(float)
        if allocation.isna().any():
            raise ValueError("initial_weights must cover every ticker.")
        if allocation.lt(0).any() or not np.isclose(allocation.sum(), 1.0):
            raise ValueError("initial_weights must be non-negative and sum to one.")

    entry_turnover = 1.0
    entry_cost = transaction_cost_bps / 10_000.0 if charge_initial_trade else 0.0
    normalized_prices = prices.div(prices.iloc[0])
    gross_equity = normalized_prices.mul(allocation, axis=1).sum(axis=1)
    position_values = normalized_prices.mul(allocation * (1.0 - entry_cost), axis=1)
    equity = position_values.sum(axis=1)
    end_weights = position_values.div(equity, axis=0)
    held_weights = end_weights.shift(1)
    held_weights.iloc[0] = allocation
    gross_return = gross_equity.pct_change(fill_method=None).fillna(0.0)
    net_return = equity.pct_change(fill_method=None)
    net_return.iloc[0] = equity.iloc[0] - 1.0

    daily = pd.DataFrame(index=prices.index)
    daily["gross_return"] = gross_return
    daily["transaction_cost"] = 0.0
    daily["transaction_cost_return"] = 0.0
    daily.iloc[0, daily.columns.get_loc("transaction_cost")] = entry_cost
    daily.iloc[0, daily.columns.get_loc("transaction_cost_return")] = entry_cost
    daily["net_return"] = net_return
    daily["equity"] = equity
    daily["turnover"] = 0.0
    daily.iloc[0, daily.columns.get_loc("turnover")] = entry_turnover
    daily["gross_exposure"] = 1.0
    daily["rebalance"] = False
    daily.iloc[0, daily.columns.get_loc("rebalance")] = True

    target = pd.DataFrame(
        np.tile(allocation.to_numpy(), (len(prices), 1)),
        index=prices.index,
        columns=prices.columns,
    )
    return BacktestResult(
        name="buy_and_hold",
        daily=daily,
        target_weights=target,
        held_weights=held_weights,
        end_of_day_weights=end_weights,
    )


def performance_metrics(result: BacktestResult) -> dict[str, Any]:
    """Summarize a backtest using the normalized net equity curve."""

    daily = result.daily
    returns = daily["net_return"]
    equity = daily["equity"]
    elapsed_days = int((daily.index[-1] - daily.index[0]).days)
    years = elapsed_days / 365.25
    final_equity = float(equity.iloc[-1])
    cagr = final_equity ** (1.0 / years) - 1.0 if years > 0 and final_equity > 0 else np.nan
    volatility = float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    return_std = float(returns.std(ddof=1))
    sharpe = (
        float(returns.mean() / return_std * np.sqrt(TRADING_DAYS_PER_YEAR))
        if return_std > 0
        else np.nan
    )
    running_peak = equity.cummax().clip(lower=1.0)
    drawdown = equity.div(running_peak).sub(1.0)
    return {
        "strategy": result.name,
        "start": daily.index[0].date().isoformat(),
        "end": daily.index[-1].date().isoformat(),
        "observations": int(len(daily)),
        "total_return": final_equity - 1.0,
        "cagr": float(cagr),
        "annualized_volatility": volatility,
        "sharpe_ratio_rf0": float(sharpe),
        "max_drawdown": float(drawdown.min()),
        "rebalance_count": int(daily["rebalance"].sum()),
        "total_turnover": float(daily["turnover"].sum()),
        "total_transaction_cost": float(daily["transaction_cost"].sum()),
        "average_gross_exposure": float(daily["gross_exposure"].mean()),
    }
