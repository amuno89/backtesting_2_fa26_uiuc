import os

import numpy as np
import pytest

from backtest import backtest
from data import load_prices, validate_prices
from mean_reversion import mean_reversion
from metrics import summarize
from run import analyze
import pandas as pd
from strategies import golden_cross

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


def test_mean_reversion_signals(prices):
    history = load_prices(os.environ["BACKTEST_DATA"]).iloc[:260]
    original = history.copy()
    signals = mean_reversion(history)
    assert signals.index.equals(history.index) and signals.columns.equals(history.columns)
    assert signals.iloc[:14].isna().all(axis=None)
    assert signals.iloc[14:].isin([0.0, 1.0]).all(axis=None)
    assert mean_reversion(history.iloc[:40]).equals(signals.iloc[:40])
    assert history.equals(original)
    # Independently seed pandas' exponential average to check Wilder's RSI.
    changes = history.diff()
    gains = changes.clip(lower=0)
    losses = -changes.clip(upper=0)
    gains.iloc[14] = gains.iloc[1:15].mean()
    losses.iloc[14] = losses.iloc[1:15].mean()
    average_gain = gains.iloc[14:].ewm(alpha=1 / 14, adjust=False).mean()
    average_loss = losses.iloc[14:].ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + average_gain / average_loss)
    decisions = signals.iloc[14:]
    expected = decisions.shift(1).fillna(0)
    expected[rsi < 30] = 1.0
    expected[rsi >= 50] = 0.0
    assert decisions.equals(expected)
    # Approved QQQ observations: cash, oversold entry, continued hold, then exit.
    dates = ["2010-01-25", "2010-01-29", "2010-02-01", "2010-02-17"]
    assert signals.loc[dates, "QQQ"].tolist() == [0.0, 1.0, 1.0, 0.0]


def test_mean_reversion_integration(prices):
    result = analyze(os.environ["BACKTEST_DATA"], strategy=mean_reversion)
    history = result["prices"]
    signals = mean_reversion(history)
    expected_positions = signals.shift(1).iloc[15:]
    assert result["benchmark_only"] is False
    assert result["held_positions"].equals(expected_positions)
    assert result["equity"].index[0] == history.index[14]
    expected = expected_positions * history.pct_change(fill_method=None).iloc[15:]
    assert result["strategy_returns"].equals(expected)
    assert result["benchmark_returns"].index.equals(expected.index)
    assert result["summary"].equals(summarize(expected))


def test_mean_reversion_zero_gain_loss(prices):
    # Actual second-day moves: SPY up, IWM down, QQQ unchanged (neutral RSI 50).
    signals = mean_reversion(prices, period=1)
    assert signals.iloc[1][["SPY", "IWM", "QQQ"]].tolist() == [0.0, 1.0, 0.0]
    neutral_signals = mean_reversion(prices, period=1, entry=51, exit=75)
    assert neutral_signals.iloc[1]["QQQ"] == 1.0
    boundary_signals = mean_reversion(prices, period=1, entry=0)
    assert boundary_signals.iloc[1]["IWM"] == 0.0


@pytest.mark.parametrize("options", [{"period": 0}, {"period": 1.5}, {"period": True},
                                     {"entry": 50}, {"exit": 101}, {"entry": np.nan}])
def test_mean_reversion_invalid_parameters(prices, options):
    with pytest.raises(ValueError):
        mean_reversion(prices, **options)

def test_golden_cross_warmup_and_uptrend():
    dates = pd.bdate_range("2020-01-01", periods=250)
    prices = pd.DataFrame({"A": range(1, 251)}, index=dates, dtype=float)
    signals = golden_cross(prices)
    assert signals.iloc[:199].isna().all().all()
    assert (signals.iloc[199:] == 1).all().all()