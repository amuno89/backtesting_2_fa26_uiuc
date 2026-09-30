"""Behavioral tests for close-to-close portfolio simulation."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from phase1_backtest.engine import buy_and_hold, performance_metrics, run_strategy
from phase1_backtest.strategies import StrategySignals


def _signals(targets: pd.DataFrame, rebalance: Sequence[bool]) -> StrategySignals:
    return StrategySignals(
        name="test_strategy",
        target_weights=targets,
        eligibility=targets.gt(0.0),
        rebalance=pd.Series(rebalance, index=targets.index, name="rebalance", dtype=bool),
        indicators={},
    )


def test_strategy_decision_at_close_is_first_held_next_session() -> None:
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    prices = pd.DataFrame({"AAA": [100.0, 200.0, 100.0, 50.0]}, index=dates)
    targets = pd.DataFrame({"AAA": [0.0, 1.0, 0.0, 0.0]}, index=dates)

    result = run_strategy(prices, _signals(targets, [False, True, True, False]))

    # The buy decision at the second close misses the preceding +100% move,
    # participates in the following -50% move, and is sold only after it.
    np.testing.assert_allclose(result.held_weights["AAA"], [0.0, 0.0, 1.0, 0.0])
    np.testing.assert_allclose(result.end_of_day_weights["AAA"], [0.0, 1.0, 0.0, 0.0])
    np.testing.assert_allclose(result.daily["gross_return"], [0.0, 0.0, -0.5, 0.0])
    np.testing.assert_allclose(result.daily["net_return"], [0.0, 0.0, -0.5, 0.0])
    np.testing.assert_allclose(result.daily["equity"], [1.0, 1.0, 0.5, 0.5])


def test_buy_and_hold_keeps_fixed_shares_instead_of_rebalancing_weights() -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    prices = pd.DataFrame(
        {"A": [100.0, 110.0, 121.0], "B": [50.0, 50.0, 40.0]}, index=dates
    )
    allocation = pd.Series({"A": 0.6, "B": 0.4})

    result = buy_and_hold(prices, initial_weights=allocation)

    expected_equity = np.array([1.0, 1.06, 1.046])
    np.testing.assert_allclose(result.daily["equity"], expected_equity)
    np.testing.assert_allclose(
        result.daily["net_return"], [0.0, 0.06, (1.046 / 1.06) - 1.0]
    )
    np.testing.assert_allclose(
        result.end_of_day_weights.to_numpy(),
        [[0.6, 0.4], [33.0 / 53.0, 20.0 / 53.0], [363.0 / 523.0, 160.0 / 523.0]],
    )
    np.testing.assert_allclose(
        result.held_weights.to_numpy(),
        [[0.6, 0.4], [0.6, 0.4], [33.0 / 53.0, 20.0 / 53.0]],
    )

    position_values = result.end_of_day_weights.mul(result.daily["equity"], axis=0)
    implied_shares = position_values.div(prices)
    np.testing.assert_allclose(implied_shares.to_numpy(), [[0.006, 0.008]] * len(dates))
    np.testing.assert_allclose(result.daily["turnover"], [1.0, 0.0, 0.0])
    assert result.daily["rebalance"].tolist() == [True, False, False]


def test_buy_and_hold_charges_entry_cost_and_counts_it_in_drawdown() -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    prices = pd.DataFrame({"A": 100.0, "B": 100.0}, index=dates)

    result = buy_and_hold(prices, transaction_cost_bps=100.0)

    np.testing.assert_allclose(result.daily["gross_return"], 0.0)
    np.testing.assert_allclose(result.daily["net_return"], [-0.01, 0.0, 0.0])
    np.testing.assert_allclose(result.daily["equity"], 0.99)
    np.testing.assert_allclose(result.daily["transaction_cost"], [0.01, 0.0, 0.0])
    assert np.isclose(performance_metrics(result)["max_drawdown"], -0.01)


def test_transaction_costs_charge_full_traded_notional_turnover() -> None:
    dates = pd.date_range("2024-01-01", periods=3, freq="D")
    prices = pd.DataFrame({"A": 100.0, "B": 100.0}, index=dates)
    targets = pd.DataFrame(
        {"A": [1.0, 0.0, 0.0], "B": [0.0, 1.0, 1.0]}, index=dates
    )
    signals = _signals(targets, [True, True, False])

    result = run_strategy(prices, signals, transaction_cost_bps=100.0)

    # Buying from cash trades 100% of NAV. A full A-to-B rotation sells 100%
    # and buys 100%, so the one-way traded-notional convention records 200%.
    np.testing.assert_allclose(result.daily["turnover"], [1.0, 2.0, 0.0])
    np.testing.assert_allclose(result.daily["transaction_cost"], [0.01, 0.0198, 0.0])
    np.testing.assert_allclose(result.daily["transaction_cost_return"], [0.01, 0.02, 0.0])
    np.testing.assert_allclose(result.daily["net_return"], [-0.01, -0.02, 0.0])
    np.testing.assert_allclose(result.daily["equity"], [0.99, 0.9702, 0.9702])

    waived = run_strategy(
        prices,
        signals,
        transaction_cost_bps=100.0,
        charge_initial_trade=False,
    )
    np.testing.assert_allclose(waived.daily["turnover"], [1.0, 2.0, 0.0])
    np.testing.assert_allclose(waived.daily["transaction_cost"], [0.0, 0.02, 0.0])
    np.testing.assert_allclose(waived.daily["equity"], [1.0, 0.98, 0.98])


def test_rebalance_turnover_is_measured_against_drifted_pretrade_weights() -> None:
    dates = pd.date_range("2024-01-01", periods=2, freq="D")
    prices = pd.DataFrame({"A": [100.0, 200.0], "B": [100.0, 100.0]}, index=dates)
    targets = pd.DataFrame({"A": [0.5, 0.5], "B": [0.5, 0.5]}, index=dates)

    result = run_strategy(
        prices,
        _signals(targets, [True, True]),
        transaction_cost_bps=100.0,
        charge_initial_trade=False,
    )

    np.testing.assert_allclose(result.daily["gross_return"], [0.0, 0.5])
    np.testing.assert_allclose(result.daily["turnover"], [1.0, 1.0 / 3.0])
    np.testing.assert_allclose(result.daily["transaction_cost"], [0.0, 0.005])
    np.testing.assert_allclose(result.daily["transaction_cost_return"], [0.0, 0.005])
    np.testing.assert_allclose(result.daily["net_return"], [0.0, 0.495])
    np.testing.assert_allclose(result.daily["equity"], [1.0, 1.495])
    np.testing.assert_allclose(result.end_of_day_weights.iloc[-1], [0.5, 0.5])
