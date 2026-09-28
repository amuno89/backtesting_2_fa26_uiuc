from __future__ import annotations

import numpy as np
import pandas as pd

from phase1_backtest.reporting import run_phase1_backtests


def test_phase1_reporting_runs_all_four_strategies(tmp_path) -> None:
    dates = pd.bdate_range("2023-01-02", periods=280)
    base = np.arange(len(dates), dtype=float)
    prices = pd.DataFrame(
        {
            f"TICKER_{number}": 100.0
            + base * (0.02 + number * 0.001)
            + np.sin(base / (4.0 + number)) * (number + 1)
            for number in range(10)
        },
        index=dates,
    )

    artifacts = run_phase1_backtests(
        prices,
        output_dir=tmp_path,
        backtest_start=dates[252].date().isoformat(),
    )

    summary = pd.read_csv(artifacts.performance_summary)
    assert summary["strategy"].tolist() == [
        "buy_and_hold",
        "sma_crossover",
        "momentum_12m",
        "rsi_mean_reversion",
    ]
    assert summary["start"].eq(dates[252].date().isoformat()).all()
    assert artifacts.equity_curves.exists()
    assert artifacts.daily_returns.exists()
    assert (artifacts.strategy_directory / "momentum_12m" / "momentum_252.csv").exists()
