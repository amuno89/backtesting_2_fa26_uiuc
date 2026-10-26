import os
import numpy as np
import pytest
from allocation import simulate
from data import load_prices


@pytest.fixture(scope="module")
def sample():
    folder = os.environ.get("BACKTEST_DATA")
    if not folder:
        pytest.skip("Set BACKTEST_DATA to the approved existing dataset folder.")
    returns = load_prices(folder).pct_change(fill_method=None).iloc[1:150]
    positions = {str(number): returns * 0 + number / 4 for number in range(5)}
    return returns, positions


def test_zero_cost_accounting_and_limits(sample):
    returns, positions = sample
    result = simulate(positions, returns, 0)
    expected = (result["exposure"] * returns).sum(axis=1)
    np.testing.assert_allclose(result["returns"], expected, atol=1e-12)
    np.testing.assert_allclose(result["weights"].sum(axis=1), 1)
    assert result["exposure"].ge(0).all(axis=None)
    assert result["exposure"].le(0.1 + 1e-12).all(axis=None)
    assert result["exposure"].sum(axis=1).le(1 + 1e-12).all()


def test_entry_cost_drift_turnover_and_cash(sample):
    returns, positions = sample
    full = {name: returns.notna().astype(float) for name in positions}
    result = simulate(full, returns, 100)
    assert result["cost"].iloc[0] == pytest.approx(0.01 / 1.01)
    assert result["returns"].iloc[0] == pytest.approx((1 + returns.iloc[0].mean()) / 1.01 - 1)
    assert result["turnover"].iloc[1] > 0  # Price drift requires trades even without new signals.
    np.testing.assert_allclose(result["cost"], result["turnover"] * 0.01, atol=1e-12)
    cash = simulate({name: table * 0 for name, table in positions.items()}, returns, 100)
    assert cash["returns"].eq(0).all() and cash["cost"].eq(0).all()
    assert cash["turnover"].eq(0).all()


def test_monthly_ranking_ties_drift_and_prefix(sample):
    returns, positions = sample
    scores = returns.iloc[:, :5].copy()
    scores.columns = list(positions)
    result = simulate(positions, returns, 0, scores=scores, dynamic=True)
    # First eligible month: prior 63-day returns rank AAPL, IWM, QQQ, SPY, JPM.
    np.testing.assert_allclose(result["weights"].loc["2010-05-03"], [0.15, 0.2, 0.25, 0.3, 0.1])
    short = simulate({name: table.iloc[:100] for name, table in positions.items()},
                     returns.iloc[:100], 0, scores=scores.iloc[:100], dynamic=True)
    assert short["returns"].equals(result["returns"].iloc[:100])
    for name in scores:
        scores[name] = returns["SPY"]
    tied = simulate(positions, returns, 0, scores=scores, dynamic=True)
    np.testing.assert_allclose(tied["weights"].loc["2010-05-03"], 0.2)
    assert not np.allclose(tied["weights"].loc["2010-05-04"], 0.2)
