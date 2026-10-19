import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


def plot_equity(result, ticker):
    ax = result["equity"][ticker].plot(label="Strategy", logy=True)
    result["benchmark_equity"][ticker].plot(ax=ax, label="Buy and hold")
    ax.set_title(ticker)
    ax.legend()
    return ax


def plot_portfolios(result):
    """Return two figures without showing or saving them automatically."""
    heatmap, ax = plt.subplots(figsize=(8, 7), layout="constrained")
    correlation = result["correlation"]
    cells = ax.imshow(correlation, vmin=-1, vmax=1, cmap="coolwarm")
    ax.set_xticks(range(len(correlation)), correlation.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(correlation)), correlation.index)
    ax.set_title("Raw-asset return correlation\n" + result["period"])
    heatmap.colorbar(cells, ax=ax, label="Correlation")
    frontier, ax = plt.subplots(figsize=(10, 7), layout="constrained")
    cloud = result["simulation"]
    curve = result["frontier"]
    ax.scatter(cloud["annualized_volatility"], cloud["expected_return"],
               color="firebrick", s=9, alpha=0.25, label="3,000 simulated portfolios")
    ax.plot(curve["annualized_volatility"], curve["expected_return"],
            color="forestgreen", label="Optimized efficient frontier")
    for (name, row), marker in zip(result["comparison"].iterrows(), ["s", "*", "D", "^"]):
        ax.scatter(row["annualized_volatility"], row["expected_return"], marker=marker,
                   s=110, color="black", label=f"{name}: Sharpe {row['sharpe_ratio']:.2f}")
    ax.set(xlabel="Annualized standard deviation", ylabel="Annualized arithmetic return",
           title=f"Efficient frontier | {result['period']}\nAnnual risk-free input: {result['risk_free']:.2%}")
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.legend(loc="upper left", fontsize=9)
    frontier.supxlabel("In-sample estimates; long-only; daily rebalancing; no costs.", fontsize=10)
    return heatmap, frontier
