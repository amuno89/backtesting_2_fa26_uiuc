"""Run the strategy-combination experiment explicitly, without saving any data."""

import argparse

import pandas as pd

from allocation import simulate
from backtest import backtest
from combinations import v2_signals
from data import load_prices
from mean_reversion import mean_reversion
from metrics import summarize
from strategies import golden_cross, momentum


def experiment(data_folder, cost_bps, risk_free):
    """Use 2011–2019 for exposure matching; report the later 2020+ observations."""
    prices = load_prices(data_folder)
    signals = v2_signals(prices)
    names = list(signals)
    signals["Original C4"] = 0.7 * signals["C1"] + 0.3 * signals["C4"]
    signals["Original C5"] = signals["C1"].where(signals["C1"].eq(1), 0.5 * signals["C4"])
    signals["Phase 1 blend"] = (golden_cross(prices) + momentum(prices) + mean_reversion(prices)) / 3
    signals["Equal-weight assets"] = prices.notna().astype(float)
    macd = prices.ewm(span=12, adjust=False).mean() - prices.ewm(span=26, adjust=False).mean()
    signals["MACD only"] = (macd > macd.ewm(span=9, adjust=False).mean()).astype(float)
    positions = {}
    for name, decisions in signals.items():
        decisions.iloc[:252] = float("nan")  # Match the existing Phase 3 evaluation start.
        result = backtest(prices, decisions)
        positions[name] = result["held_positions"]
    asset_returns = result["asset_returns"]
    history = asset_returns.index < "2020-01-01"
    later = ~history
    if history.sum() < 252 or later.sum() < 252:
        raise ValueError("This experiment needs at least a year before and after January 2020.")
    runs = {}
    for name, table in positions.items():
        runs[name] = simulate({name: table}, asset_returns, cost_bps)
    scores = pd.DataFrame({name: runs[name]["returns"] for name in names})
    candidates = {name: positions[name] for name in names}
    runs["Fixed"] = simulate(candidates, asset_returns, cost_bps)
    runs["Dynamic"] = simulate(candidates, asset_returns, cost_bps, scores, dynamic=True)
    # Fit only the exposure control on earlier data, then evaluate all results later.
    fixed_exposure = runs["Fixed"]["exposure"].loc[history].sum(axis=1).mean()
    c1_exposure = runs["C1"]["exposure"].loc[history].sum(axis=1).mean()
    scale = min(1.0, fixed_exposure / c1_exposure)
    runs["Matched C1"] = simulate({"C1": positions["C1"] * scale}, asset_returns, cost_bps)
    for removed in names:
        remaining = {name: table for name, table in candidates.items() if name != removed}
        runs["Without " + removed] = simulate(remaining, asset_returns, cost_bps)
    returns = pd.DataFrame({name: run["returns"] for name, run in runs.items()}).loc[later]
    summary = summarize(returns, risk_free)
    for name, run in runs.items():
        exposure = run["exposure"].loc[later]
        summary.loc[name, "mean_exposure"] = exposure.sum(axis=1).mean()
        summary.loc[name, "mean_active_tickers"] = exposure.gt(0).sum(axis=1).mean()
        invested = exposure.sum(axis=1)
        effective = invested ** 2 / exposure.pow(2).sum(axis=1)
        summary.loc[name, "effective_tickers"] = effective.fillna(0).mean()
        summary.loc[name, "annual_turnover"] = run["turnover"].loc[later].mean() * 252
    bad_days = returns["C1"] <= returns["C1"].quantile(0.1)
    diagnostics = pd.DataFrame(index=names)
    c1_changes = positions["C1"].gt(0).ne(positions["C1"].shift(1).gt(0)).loc[later]
    for name in names:
        changes = positions[name].gt(0).ne(positions[name].shift(1).gt(0)).loc[later]
        overlap = (changes & c1_changes).to_numpy().sum()
        union = (changes | c1_changes).to_numpy().sum()
        diagnostics.loc[name, "entry_exit_overlap_C1"] = overlap / union if union else float("nan")
        diagnostics.loc[name, "mean_on_C1_bad_days"] = returns.loc[bad_days, name].mean()
        diagnostics.loc[name, "loss_share_on_C1_bad_days"] = returns.loc[bad_days, name].lt(0).mean()
    basket_return = asset_returns.loc[later].mean(axis=1)
    stress = pd.DataFrame({"basket_down_over_1pct": returns.loc[basket_return < -0.01].mean(),
                           "basket_up_over_1pct": returns.loc[basket_return > 0.01].mean()})
    return {"summary": summary, "diagnostics": diagnostics, "stress": stress,
            "correlation": returns[names].corr(), "returns": returns, "runs": runs,
            "control_scale": scale, "period": f"{returns.index[0].date()} to {returns.index[-1].date()}"}


def main():
    parser = argparse.ArgumentParser(description="Test five offline strategy combinations.")
    parser.add_argument("data_folder", help="Approved existing dataset folder")
    parser.add_argument("--cost-bps", type=float, required=True, help="Illustrative one-way trading cost")
    parser.add_argument("--risk-free", type=float, required=True, help="Annual decimal risk-free input")
    args = parser.parse_args()
    result = experiment(args.data_folder, args.cost_bps, args.risk_free)
    print(result["period"], "| Matched C1 scale:", round(result["control_scale"], 4))
    for name in ["summary", "diagnostics", "stress", "correlation"]:
        print(name, "\n", result[name].round(4).to_string())


if __name__ == "__main__":
    main()
