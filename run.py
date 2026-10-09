"""One entry point for the approved data and shared calculations."""

import argparse

import pandas as pd

from backtest import backtest
from data import load_prices
from metrics import summarize


def analyze(data_folder, strategy=None, risk_free=None):
    """A supplied strategy function takes prices and returns matching signals."""
    prices = load_prices(data_folder)
    if strategy is None:
        signals = prices.notna().astype(float)  # Buy-and-hold baseline only.
    else:
        signals = strategy(prices)
    result = backtest(prices, signals)
    if isinstance(risk_free, pd.Series):
        risk_free = risk_free.loc[result["asset_returns"].index]
    result["prices"] = prices
    result["benchmark_only"] = strategy is None
    result["summary"] = summarize(result["strategy_returns"], risk_free)
    result["benchmark_summary"] = summarize(result["benchmark_returns"], risk_free)
    return result


def main():
    parser = argparse.ArgumentParser(description="Run the offline buy-and-hold baseline.")
    parser.add_argument("data_folder", help="Path to the approved existing dataset")
    parser.add_argument("--risk-free", type=float, help="Explicit annual decimal rate")
    args = parser.parse_args()
    try:
        result = analyze(args.data_folder, risk_free=args.risk_free)
    except (ValueError, FileNotFoundError, KeyError) as error:
        parser.error(str(error))
    print("Buy-and-hold baseline (no trading strategy selected)")
    if args.risk_free is None:
        print("Sharpe is unavailable until a risk-free input is supplied.")
    print(result["benchmark_summary"].to_string())


if __name__ == "__main__":
    main()
