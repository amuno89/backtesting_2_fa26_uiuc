import pandas as pd

from backtest import backtest
from metrics import summarize


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
