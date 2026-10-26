"""One entry point for the approved data and shared calculations."""

import argparse

import pandas as pd

from backtest import backtest
from data import load_prices
from performance import analyze_portfolios, summarize


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


def compare(prices, strategies, metric="annualized_return", warmup=252):
    """One metric for every strategy and buy-and-hold, over the same dates."""
    table = {}
    for name, strategy in strategies.items():
        signals = strategy(prices)
        signals.iloc[:warmup] = float("nan")
        result = backtest(prices, signals)
        table[name] = summarize(result["strategy_returns"])[metric]
    table["Buy and hold"] = summarize(result["benchmark_returns"])[metric]
    return pd.DataFrame(table)


def main():
    parser = argparse.ArgumentParser(description="Run offline backtesting or raw-asset portfolios.")
    parser.add_argument("data_folder", help="Path to the approved existing dataset")
    parser.add_argument("--risk-free", type=float, help="Explicit annual decimal rate")
    parser.add_argument("--phase2", action="store_true", help="Analyze raw-asset portfolios and show charts")
    args = parser.parse_args()
    if args.phase2 and args.risk_free is None:
        parser.error("Phase 2 requires an explicit --risk-free annual rate.")
    try:
        result = analyze(args.data_folder, risk_free=args.risk_free)
        if args.phase2:
            from plots import plot_portfolios
            import matplotlib.pyplot as plt
            portfolios = analyze_portfolios(result["asset_returns"], args.risk_free)
            for name in ["asset_summary", "correlation_pairs", "comparison_summary", "comparison_weights"]:
                print(name, "\n", portfolios[name].to_string())
            plot_portfolios(portfolios)
            plt.show()
            return
    except (ValueError, FileNotFoundError, KeyError) as error:
        parser.error(str(error))
    print("Buy-and-hold baseline (no trading strategy selected)")
    if args.risk_free is None:
        print("Sharpe is unavailable until a risk-free input is supplied.")
    print(result["benchmark_summary"].to_string())


if __name__ == "__main__":
    main()
