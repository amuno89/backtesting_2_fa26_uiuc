import os

import numpy as np
import pytest

from backtest import backtest
from data import load_prices, validate_prices
from metrics import summarize
from run import analyze


@pytest.fixture(scope="module")
def prices():
    folder = os.environ.get("BACKTEST_DATA")
    if not folder:
        pytest.skip("Set BACKTEST_DATA to the approved existing dataset folder.")
    return load_prices(folder).iloc[:20]


@pytest.mark.parametrize("column_names", [None, [f"portfolio_{i}" for i in range(10)]])
def test_buy_and_hold(prices, column_names):
    result = backtest(prices, prices.notna().astype(float))
    expected = prices.iloc[-1] / prices.iloc[0]
    np.testing.assert_allclose(result["equity"].iloc[-1], expected)
    np.testing.assert_allclose(result["benchmark_equity"].iloc[-1], expected)
    returns = result["strategy_returns"].copy()
    if column_names is not None:
        returns.columns = column_names
    summary = summarize(returns)
    np.testing.assert_allclose(summary["total_return"], expected - 1)
    assert summary["sharpe_ratio"].isna().all()


def test_position_timing_and_warmup(prices):
    signals = prices.notna().astype(float)
    signals.iloc[:3] = np.nan  # Unavailable decisions during an indicator's warm-up.
    signals.iloc[5] = 0  # A test decision to exit affects only the following return.
    result = backtest(prices, signals)
    assert result["equity"].index[0] == prices.index[3]
    assert result["strategy_returns"].index[0] == prices.index[4]
    assert result["strategy_returns"].loc[prices.index[6]].eq(0).all()
    prefix = backtest(prices.iloc[:10], signals.iloc[:10])
    assert prefix["strategy_returns"].equals(result["strategy_returns"].iloc[:6])


@pytest.mark.parametrize("problem", ["order", "gap", "tickers", "text"])
def test_invalid_prices(prices, problem):
    invalid = {"order": prices.iloc[::-1], "gap": prices.drop(prices.index[2]),
               "tickers": prices.iloc[:, :-1], "text": prices.astype(str)}
    with pytest.raises(ValueError):
        validate_prices(invalid[problem])


def test_signal_gap_is_not_silently_dropped(prices):
    signals = prices.notna().astype(float)
    signals.iloc[5] = np.nan
    with pytest.raises(ValueError, match="position gaps"):
        backtest(prices, signals)


def test_drawdown_includes_the_starting_investment(prices):
    returns = prices.pct_change(fill_method=None).iloc[1:]
    first_loss = returns.index[returns["SPY"] < 0][0]
    sample = returns.loc[first_loss:]
    assert summarize(sample).loc["SPY", "maximum_drawdown"] <= sample["SPY"].iloc[0]


def test_constant_excess_returns_have_undefined_sharpe(prices):
    cash_returns = prices.pct_change(fill_method=None).iloc[1:] * 0
    # This rate tests the formula only; it is not a chosen assumption for analysis.
    assert summarize(cash_returns, risk_free=0.05)["sharpe_ratio"].isna().all()


@pytest.mark.parametrize("benchmark_only", [True, False])
def test_shared_analysis(prices, benchmark_only):
    def test_signals(history):
        decisions = history.notna().astype(float)
        decisions.iloc[:3] = np.nan
        return decisions

    strategy = None if benchmark_only else test_signals
    result = analyze(os.environ["BACKTEST_DATA"], strategy=strategy)
    assert result["benchmark_only"] is benchmark_only
    assert result["prices"].iloc[:len(prices)].equals(prices)
    expected_start = prices.index[1 if benchmark_only else 4]
    assert result["asset_returns"].index[0] == expected_start
    assert result["asset_returns"].equals(result["strategy_returns"])
    assert result["summary"].equals(result["benchmark_summary"])
