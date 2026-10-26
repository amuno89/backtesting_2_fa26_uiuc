import numpy as np
import pytest

from combinations import v2_signals


@pytest.fixture(scope="module")
def sample(approved_prices):
    prices = approved_prices.iloc[:500].copy()
    return prices, v2_signals(prices)


@pytest.mark.parametrize("name", ["C1", "C3", "C4", "C5", "C6"])
def test_signal_history_and_bounds(sample, name):
    prices, signals = sample
    original = prices.copy()
    prefix = v2_signals(prices.iloc[:120])[name]
    assert prefix.equals(signals[name].iloc[:120])
    assert prices.equals(original)
    assert signals[name].iloc[:33].isna().all(axis=None)
    assert signals[name].iloc[33:].ge(0).all(axis=None)
    assert signals[name].iloc[33:].le(1).all(axis=None)


def test_sizing_and_breakout_states(sample):
    prices, signals = sample
    high = prices.rolling(20).max().shift(1)
    low = prices.rolling(10).min().shift(1)
    decisions = prices * np.nan
    decisions[prices > high] = 1.0
    decisions[prices < low] = 0.0
    # Independent forward-fill reference for the breakout holding state.
    decisions.iloc[:33] = np.nan
    expected = decisions.iloc[33:].ffill().fillna(0)
    assert signals["C4"].iloc[33:].equals(expected)
    assert signals["C3"].iloc[33:].isin([0, 0.5, 1]).all(axis=None)
    assert signals["C3"].gt(0).equals(signals["C1"].gt(0))
    confirmed = signals["C1"].eq(1) & (prices > high)
    assert signals["C3"].where(confirmed, 1).eq(1).all(axis=None)
    holding = signals["C3"].shift(1).eq(1) & signals["C1"].eq(1)
    assert signals["C3"].where(holding, 1).eq(1).all(axis=None)
    volatility = prices.pct_change(fill_method=None).rolling(20).std(ddof=1) * np.sqrt(252)
    expected_scale = signals["C1"] * (0.20 / volatility).clip(upper=1)
    np.testing.assert_allclose(signals["C6"], expected_scale, equal_nan=True)


def test_bollinger_entry_and_exit(sample):
    prices, signals = sample
    positions = signals["C5"]
    middle = prices.rolling(20).mean()
    lower = middle - 2 * prices.rolling(20).std(ddof=0)
    low = prices.rolling(10).min().shift(1)
    entries = positions.diff().eq(1)
    allowed = (prices.shift(1) < lower.shift(1)) & (prices >= lower)
    allowed &= (prices > prices.shift(1)) & (prices < middle) & (prices >= low)
    assert allowed.where(entries, True).all(axis=None)
    exits = positions.diff().eq(-1)
    allowed_exit = (prices >= middle) | (prices < low)
    assert allowed_exit.where(exits, True).all(axis=None)
    # Actual QQQ observations cover entry, continued holding, and downside exit.
    assert positions.loc[["2010-05-10", "2010-05-11", "2010-05-20"], "QQQ"].tolist() == [1, 1, 0]
