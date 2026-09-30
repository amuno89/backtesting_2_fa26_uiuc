"""Run the Phase 1 strategies and persist inspectable results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from phase1_backtest.engine import (
    BacktestResult,
    buy_and_hold,
    performance_metrics,
    run_strategy,
)
from phase1_backtest.strategies import (
    StrategySignals,
    momentum,
    rsi_mean_reversion,
    sma_crossover,
    validate_prices,
)


@dataclass(frozen=True)
class BacktestArtifacts:
    """Top-level result files created by :func:`run_phase1_backtests`."""

    performance_summary: Path
    equity_curves: Path
    daily_returns: Path
    strategy_directory: Path


def _write_indexed_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=True, index_label="date", float_format="%.10g")
    temporary.replace(path)


def _slice_signals(signals: StrategySignals, start: pd.Timestamp) -> StrategySignals:
    target = signals.target_weights.loc[start:].copy()
    eligibility = signals.eligibility.loc[start:].copy()
    rebalance = signals.rebalance.loc[start:].copy()
    if target.empty:
        raise ValueError("backtest_start is after the available data.")
    rebalance.iloc[0] = bool(target.iloc[0].ne(0.0).any())
    indicators = {name: values.loc[start:].copy() for name, values in signals.indicators.items()}
    return StrategySignals(
        name=signals.name,
        target_weights=target,
        eligibility=eligibility,
        rebalance=rebalance,
        indicators=indicators,
    )


def _write_strategy_details(
    result: BacktestResult,
    root: Path,
    signals: StrategySignals | None = None,
) -> None:
    strategy_dir = root / result.name
    _write_indexed_csv(result.daily, strategy_dir / "daily_performance.csv")
    _write_indexed_csv(result.target_weights, strategy_dir / "target_weights.csv")
    _write_indexed_csv(result.held_weights, strategy_dir / "held_weights.csv")
    _write_indexed_csv(result.end_of_day_weights, strategy_dir / "end_of_day_weights.csv")
    if signals is not None:
        _write_indexed_csv(signals.eligibility.astype(int), strategy_dir / "eligibility.csv")
        schedule = signals.rebalance.rename("rebalance").astype(int).to_frame()
        _write_indexed_csv(schedule, strategy_dir / "rebalance_schedule.csv")
        for indicator_name, indicator in signals.indicators.items():
            _write_indexed_csv(indicator, strategy_dir / f"{indicator_name}.csv")


def run_phase1_backtests(
    prices: pd.DataFrame,
    *,
    output_dir: str | Path = "results",
    transaction_cost_bps: float = 0.0,
    backtest_start: str | None = None,
) -> BacktestArtifacts:
    """Run buy-and-hold plus SMA, momentum, and RSI strategies."""

    prices = validate_prices(prices)
    definitions = [
        sma_crossover(prices),
        momentum(prices),
        rsi_mean_reversion(prices),
    ]

    if backtest_start is not None:
        requested_start = pd.Timestamp(backtest_start).normalize()
        available = prices.index[prices.index >= requested_start]
        if available.empty:
            raise ValueError("backtest_start is after the available data.")
        effective_start = available[0]
        backtest_prices = prices.loc[effective_start:]
        definitions = [_slice_signals(signals, effective_start) for signals in definitions]
    else:
        backtest_prices = prices

    benchmark = buy_and_hold(
        backtest_prices,
        transaction_cost_bps=transaction_cost_bps,
    )
    strategy_results = [
        run_strategy(
            backtest_prices,
            signals,
            transaction_cost_bps=transaction_cost_bps,
        )
        for signals in definitions
    ]
    all_results = [benchmark, *strategy_results]

    root = Path(output_dir)
    details = root / "strategies"
    _write_strategy_details(benchmark, details)
    for result, signals in zip(strategy_results, definitions, strict=True):
        _write_strategy_details(result, details, signals)

    summary = pd.DataFrame(performance_metrics(result) for result in all_results)
    summary_path = root / "performance_summary.csv"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_path, index=False, float_format="%.10g")

    equity_curves = pd.concat(
        {result.name: result.daily["equity"] for result in all_results}, axis=1
    )
    return_series = pd.concat(
        {result.name: result.daily["net_return"] for result in all_results}, axis=1
    )
    equity_path = root / "equity_curves.csv"
    returns_path = root / "daily_returns.csv"
    _write_indexed_csv(equity_curves, equity_path)
    _write_indexed_csv(return_series, returns_path)

    return BacktestArtifacts(
        performance_summary=summary_path,
        equity_curves=equity_path,
        daily_returns=returns_path,
        strategy_directory=details,
    )
