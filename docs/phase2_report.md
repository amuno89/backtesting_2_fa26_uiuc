# Phase 2: diversification helps, but 1.07 is an in-sample estimate

## Summary

- The maximum estimated Sharpe is **1.073**, compared with **0.898** for equal
  weights and **0.747** for SPY. These are historical estimates, not forecasts.
- Only **2 of 45** asset pairs have correlation above 0.80. All pairs are positive,
  but diversification still helps: negative correlation is not required.
- The optimized portfolio already holds almost no index ETFs. Their inclusion
  alone does not explain the 1.07 result.

Scope: the ten approved raw assets, 4,207 daily returns from January 5, 2010 to
September 25, 2026, and the explicitly selected **2% illustrative annual risk-free
rate**. No new observations or strategies were added. Updated October 24, 2026.

## 1. Read the frontier as a risk–return trade-off

![In-sample efficient frontier, with simulated portfolios colored by Sharpe ratio](sharpe_ratio.png)

Each dot is one of 3,000 allocations. Color measures Sharpe; the axes measure
annualized standard deviation and arithmetic expected return. Black marker
shapes distinguish the comparison portfolios. The green line is the optimized
upper frontier, not a line joining the best random dots.

| Portfolio | Arithmetic return/year | Volatility/year | Sharpe |
|---|---:|---:|---:|
| Minimum variance | 12.84% | 13.57% | 0.801 |
| Maximum Sharpe | 20.36% | 17.13% | 1.073 |
| Equal weight | 16.55% | 16.22% | 0.898 |
| SPY | 14.72% | 17.05% | 0.747 |

Within this mean–variance model, a risk-averse investor prefers the efficient
frontier: least variance for a target return, or highest return for a given risk.
The chosen point depends on risk tolerance. The maximum-Sharpe point is not the
minimum-risk point. [CFA Institute: Portfolio Risk and Return](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/portfolio-risk-return-part-1)

## 2. Correlation limits diversification; it does not eliminate it

![Daily raw-asset return correlations for the approved historical sample](asset_correlation.png)

| Correlation check | Result |
|---|---:|
| Highest pair: SPY / QQQ | 0.930 |
| Second-highest pair: SPY / IWM | 0.882 |
| Lowest pair: XOM / WMT | 0.213 |
| Median of the 45 distinct pairs | 0.390 |
| Pairs above 0.80 | 2 / 45 |
| Negative pairs | 0 / 45 |

The 0.80 level is a descriptive flag, not an exclusion rule. Shared equity
exposure may explain the strongly correlated ETF pairs; this table does not
establish causality. Lower correlations help all else equal, but returns,
individual volatilities, and portfolio weights also matter.

For the maximum-Sharpe weights, the weighted average individual volatility is
23.89%, while portfolio volatility is 17.13%. The ratio is **1.395**. The former
is also the hypothetical portfolio volatility if every pair had correlation +1,
with weights and individual volatilities unchanged. This is a mathematical
comparison, not another observed portfolio or a forecast.

Perfectly **positively** correlated assets offer no correlation-based
diversification benefit. That does not mean they can never be held together:
identical return streams can share a weight without changing portfolio results.

## 3. The optimizer already avoids most ETF overlap

| Asset | Maximum-Sharpe weight |
|---|---:|
| AAPL | 36.29% |
| JNJ | 23.36% |
| WMT | 23.32% |
| CAT | 15.81% |
| JPM | 1.06% |
| QQQ | 0.17% |
| SPY | 0.00% |
| IWM | 0.00% |
| XOM | 0.00% |
| PG | 0.00% |

Weights are rounded; tiny numerical residuals appear as zero. The top three
allocations total **82.96%**, so the portfolio remains concentrated.

Because zero weights are allowed, removing an asset cannot increase the
theoretical best in-sample Sharpe: it only narrows the available choices. The
observed maximum depends on the whole set of estimated returns and covariances,
the sample, the risk-free input, and the long-only constraints. Calling 1.07
"good but not great" without a matched comparison is not a reliable conclusion.

## What was corrected—and what was not

The chart now directly encodes Sharpe and labels the fit as in-sample. The report
adds measured correlations, allocations, and the qualifications above. The
optimizer, tickers, prices, and strategies are unchanged; **1.073 remains the
estimated maximum**, not a promised improvement or a universal ceiling.

All estimates use the same dates, 252-day annualization, and sample covariance.
The annual risk-free input is converted to its compounded daily equivalent for
Sharpe. Arithmetic return is not CAGR. Weights are long-only, sum to one, and are
rebalanced daily. Costs are excluded. Fitting and evaluation use the same history;
there is no independent future-performance test in this Phase 2 report.

Evidence comes from the approved local data through the existing
[runner](../run.py), [portfolio calculations](../portfolio.py), and
[shared metrics](../metrics.py). The inputs retain the provider-adjustment and
repaired-observation caveats in [Existing data](../README.md#existing-data).
Use the existing [Phase 2 command](../README.md#run-the-analysis) to calculate
the charts in memory. These two PNGs were saved explicitly for this report;
ordinary analysis still does not download or save data.
