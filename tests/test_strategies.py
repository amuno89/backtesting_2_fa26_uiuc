"""Behavioral tests for the Phase 1 strategy definitions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase1_backtest.strategies import (
    momentum,
    relative_strength_index,
    rsi_mean_reversion,
    sma_crossover,
)


def test_sma_crossover_waits_for_the_full_200_session_warmup() -> None:
    dates = pd.bdate_range("2023-01-02", periods=201)
    prices = pd.DataFrame({"AAA": np.arange(1.0, 202.0)}, index=dates)

    signals = sma_crossover(prices)

    assert signals.indicators["sma_50"].first_valid_index() == dates[49]
    assert signals.indicators["sma_200"].first_valid_index() == dates[199]
    assert signals.target_weights.iloc[:199].eq(0.0).all().all()
    assert not signals.eligibility.iloc[:199].any().any()
    assert signals.eligibility.loc[dates[199], "AAA"]
    assert signals.target_weights.loc[dates[199], "AAA"] == 1.0
    assert signals.rebalance.sum() == 1
    assert signals.rebalance.loc[dates[199]]


def test_momentum_selects_top_three_only_at_observed_month_ends() -> None:
    dates = pd.to_datetime(
        [
            "2024-01-29",
            "2024-01-30",
            "2024-01-31",
            "2024-02-01",
            "2024-02-02",
            "2024-02-28",
            "2024-02-29",
        ]
    )
    prices = pd.DataFrame(
        {
            "A": [100.0, 100.0, 140.0, 70.0, 70.0, 70.0, 35.0],
            "B": [100.0, 100.0, 130.0, 130.0, 130.0, 130.0, 260.0],
            "C": [100.0, 100.0, 120.0, 120.0, 120.0, 120.0, 180.0],
            "D": [100.0, 100.0, 90.0, 180.0, 180.0, 180.0, 360.0],
        },
        index=dates,
    )

    signals = momentum(prices, lookback=1, top_n=3)

    assert signals.rebalance.tolist() == [False, False, True, False, False, False, True]
    np.testing.assert_allclose(signals.target_weights.iloc[:2].to_numpy(), 0.0)

    january_selection = pd.Series(
        {"A": 1.0 / 3.0, "B": 1.0 / 3.0, "C": 1.0 / 3.0, "D": 0.0}
    )
    for date in dates[2:6]:
        pd.testing.assert_series_equal(
            signals.target_weights.loc[date], january_selection, check_names=False
        )

    # D is the strongest name on February 1, but the January allocation is
    # deliberately held until the next month-end rebalance.
    assert signals.indicators["momentum_1"].loc[dates[3], "D"] == 1.0
    assert signals.target_weights.loc[dates[3], "D"] == 0.0

    february_selection = pd.Series(
        {"A": 0.0, "B": 1.0 / 3.0, "C": 1.0 / 3.0, "D": 1.0 / 3.0}
    )
    pd.testing.assert_series_equal(
        signals.target_weights.loc[dates[-1]], february_selection, check_names=False
    )


def test_momentum_does_not_treat_an_incomplete_terminal_month_as_month_end() -> None:
    dates = pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-15"])
    prices = pd.DataFrame(
        {
            "A": [100.0, 101.0, 102.0, 103.0],
            "B": [100.0, 102.0, 103.0, 104.0],
            "C": [100.0, 103.0, 104.0, 105.0],
        },
        index=dates,
    )

    signals = momentum(prices, lookback=1, top_n=1)

    assert signals.rebalance.tolist() == [False, True, False, False]
    assert signals.target_weights.loc[dates[-1], "C"] == 1.0


def test_wilder_rsi_uses_recursive_smoothed_gains_and_losses() -> None:
    dates = pd.date_range("2024-01-01", periods=7, freq="D")
    prices = pd.DataFrame({"AAA": [10.0, 11.0, 13.0, 12.0, 12.0, 15.0, 14.0]}, index=dates)

    rsi = relative_strength_index(prices, window=3)["AAA"]

    assert rsi.iloc[:3].isna().all()
    expected = np.array([75.0, 75.0, 3900.0 / 43.0, 7800.0 / 113.0])
    np.testing.assert_allclose(rsi.iloc[3:].to_numpy(), expected, rtol=0.0, atol=1e-12)


def test_wilder_rsi_defines_monotonic_and_flat_edge_cases_exactly() -> None:
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    prices = pd.DataFrame(
        {
            "UP": [1.0, 2.0, 3.0, 4.0, 5.0],
            "DOWN": [5.0, 4.0, 3.0, 2.0, 1.0],
            "FLAT": [2.0, 2.0, 2.0, 2.0, 2.0],
        },
        index=dates,
    )

    rsi = relative_strength_index(prices, window=2)

    assert rsi.iloc[:2].isna().all().all()
    np.testing.assert_array_equal(rsi.loc[dates[2]:, "UP"].to_numpy(), 100.0)
    np.testing.assert_array_equal(rsi.loc[dates[2]:, "DOWN"].to_numpy(), 0.0)
    np.testing.assert_array_equal(rsi.loc[dates[2]:, "FLAT"].to_numpy(), 50.0)

    signals = rsi_mean_reversion(prices, window=2, oversold_threshold=30.0)
    assert signals.target_weights.iloc[:2].eq(0.0).all().all()
    expected_target = pd.Series({"UP": 0.0, "DOWN": 1.0, "FLAT": 0.0})
    for date in dates[2:]:
        pd.testing.assert_series_equal(
            signals.target_weights.loc[date], expected_target, check_names=False
        )
