def plot_equity(result, ticker):
    ax = result["equity"][ticker].plot(label="Strategy", logy=True)
    result["benchmark_equity"][ticker].plot(ax=ax, label="Buy and hold")
    ax.set_title(ticker)
    ax.legend()
    return ax
