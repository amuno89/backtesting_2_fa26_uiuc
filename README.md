# backtesting_2_fa26_uiuc
Repository for Backtesting group 2 for Fall 2026 semester's Financial Engineering club projects.

The tickers being used for phase 1 are: SPY, QQQ, IWM, AAPL, JPM, XOM, JNJ, PG, WMT, CAT

To make changes, create a new branch for your changes, commit the changes to that branch, and then create a pull request to merge the branch with `main`.

## Current work

This is a small, offline backtesting foundation with one entry point: `run.py`.
The command-line runner uses buy-and-hold, or raw-asset portfolios with `--phase2`.
RSI mean reversion and Huixin's strategies use the same Python workflow.
A risk-free rate must be supplied explicitly; no rate is downloaded or assumed.
Completed coding work goes to `Kevin-Mean-revision`
and then through a pull request into `main`.

- `run.py` loads the data once, calls the calculations, and returns their results.
- `data.py` reads the approved dataset, verifies its raw-file checksum, compares
  adjusted prices with the raw observations, and checks the NYSE trading calendar.
- `backtest.py` applies supplied positions to the following day's returns and
  compares each ticker with buy-and-hold over the same dates.
- `metrics.py` calculates performance statistics from a daily return table.
- `mean_reversion.py` returns RSI-based signals independently of Golden Cross.
- `strategies.py` contains Huixin's Golden Cross and momentum rules.
- `compare.py` compares strategy metrics over a shared evaluation period.
- `portfolio.py` combines daily returns into portfolios and finds the frontier.
- `plots.py` draws equity curves, the correlation heatmap, and the frontier.
- `tests/test_core.py` checks these functions against existing local observations.

Each file keeps its role across phases. All source, tests, comments, and blank
lines combined must stay at or below 600 lines, with at most 300 added for Phase 2.
The earlier mean-reversion addition retains its separate 100-added-line limit.

## Run the current baseline

From the repository folder, use a Python environment with the libraries in
`requirements.txt` installed. For the existing local environment and dataset:

```sh
.venv/bin/python -B run.py data
```

The data-folder argument is required; replace `data` with the path to your approved
dataset when needed. The command prints a table of buy-and-hold results. It does
not create result files. Use `--help` for the options. An explicit annual decimal
rate can be supplied with `--risk-free`; otherwise Sharpe remains unavailable.

## Run RSI mean reversion

From the repository folder, explicitly select this strategy using the same local data:

```sh
.venv/bin/python -B - <<'PY'
from mean_reversion import mean_reversion
from run import analyze
result = analyze("data", strategy=mean_reversion)
print(result["summary"].to_string())
print(result["benchmark_summary"].to_string())
PY
```

### How to read the strategy

`mean_reversion` keeps three steps together: check the settings, prepare daily
gains and losses, then update RSI and each ticker's position one day at a time.
It takes a price table, with dates in rows and tickers in columns, and returns
a decision table with the same layout. `1.0` means invested, `0.0` means cash,
and `NaN` means there is not enough history to make a decision yet.

RSI (Relative Strength Index) compares recent gains with losses. The default
uses 14 daily price changes, so the first value needs 15 price observations.
Wilder's smoothing starts with the average of those gains and losses; afterward,
each average becomes (13 times its previous value + today's gain or loss) / 14.
Losses are measured as positive amounts. RSI is 100 times the average gain divided
by the sum of the average gain and average loss. All gains gives RSI 100 and all
losses gives 0. When both smoothed averages are zero, this implementation uses
neutral RSI 50; a single flat day does not reset an existing RSI to 50.

| RSI after warm-up | Decision for each ticker |
|---|---|
| Below 30 | Buy if currently in cash; otherwise remain invested |
| From 30 up to, but not including, 50 | Keep the current position: invested or cash |
| 50 or higher | Sell if invested; otherwise remain in cash |

The mean-reversion idea is to test whether a rebound follows recent weakness.
This is a hypothesis, not a guarantee that a low-RSI asset will recover. Holdings
are tracked separately for each ticker; these are not weights in a combined portfolio.

Decisions are made at the close. The shared backtest applies each decision to the
following close-to-close return, so today's price is not used to choose today's
position. With the default period, the first 14 decision rows stay missing;
the first decision is at observation 15 and evaluation starts at observation 16.
The benchmark uses those same evaluation dates. At least 17 price observations
are needed for the backtest's minimum of two evaluation returns.

The function only calculates signals from its input; it does not download, change,
or save data. It does not depend on Huixin's strategy file. Both strategies can
use the shared backtest and metrics independently. Costs and cash interest remain
zero. Without an explicit risk-free input, Sharpe stays unavailable.

## How the phases connect

`analyze(data_folder, strategy=None, risk_free=None)` in `run.py` is the shared
workflow. It returns an ordinary dictionary of tables, so later phases can reuse
the same objects without saving or reloading intermediate files.

| Result | What it contains |
|---|---|
| `prices` | Complete validated history, including dates needed for warm-up |
| `held_positions` | Prior-day decisions applied to the evaluation dates |
| `asset_returns` | Raw buy-and-hold asset returns over the evaluation dates |
| `strategy_returns` | Returns earned by the supplied signals, on matching dates |
| `benchmark_returns` | A separate copy of the matching buy-and-hold returns |
| `equity`, `benchmark_equity` | Growth from one, including the initial close |
| `summary`, `benchmark_summary` | Matching performance-statistic tables |
| `benchmark_only` | True when no strategy function was supplied |

Each strategy function takes `prices` and returns a signal
table with the same dates and columns. Passing that function to `analyze` uses the
existing backtest and metrics. Without it, both return tables contain the baseline;
`benchmark_only=True` means no selected strategy has been evaluated.

Phase 2 passes the baseline's `asset_returns` to `analyze_portfolios` in
`portfolio.py`. Do not pass a strategy backtest's shortened warm-up window when
you intend to use the full raw-asset history. Phase 3 can later pass approved,
aligned strategy-return tables to the same portfolio function.
Both phases can use `summarize` with portfolio names as columns and `equity_curve`
for growth calculations. The matched evaluation dates make comparisons fair;
`prices` retains the full history when an explicitly different period is required.

Phase 3 is not implemented. It must not mistake a benchmark-only result for a selected strategy or
claim diversification across different strategies when only one is supplied.

## Run Phase 2

### Sharpe ratio graph

![Efficient frontier with Sharpe ratios for minimum variance, maximum Sharpe, equal weight, and SPY portfolios](docs/sharpe_ratio.png)

Updated on October 24, 2026 using the approved January 5, 2010–September 25, 2026
return sample and an illustrative 2% annual risk-free rate. Point colors show
simulated portfolio Sharpe ratios; black markers identify the four comparisons.
The axes show risk and return, not Sharpe. This is a saved snapshot, updated only
on request, not a live chart.

Read the [Phase 2 visual report](docs/phase2_report.md) for the correlation
heatmap, allocation weights, and interpretation. The maximum remains about 1.07
for this sample and model; the graph correction does not improve investment returns.

### Run the analysis

Use the same environment and approved data folder. This command explicitly asks
for calculations and two chart windows; it does not save them:

```sh
.venv/bin/python -B run.py data --phase2 --risk-free 0.02
```

Here, `0.02` is the user-approved 2% illustration, not an observed Treasury or SOFR
rate. Replace it only when a different rate is selected. A historical-period average Treasury
yield can be used as a constant proxy, but must be obtained and selected explicitly.
Phase 2 rejects a missing rate. It supports a constant rate so the optimizer's
Sharpe definition matches Phase 1; it does not accept a time-varying rate series.

The runner first calls the existing baseline, then passes its raw-asset returns
to `analyze_portfolios`. There are no strategy signals or warm-up losses in this
Phase 2 sample. Every asset and comparison uses exactly the same dates.

| Returned table | Rows and columns |
|---|---|
| `asset_summary` | Ten assets × existing metrics plus `expected_return` |
| `correlation`, `covariance` | Ten assets × ten assets, in the original ticker order |
| `correlation_pairs` | Least and most correlated distinct pairs, in that order |
| `simulation_weights`, `simulation` | 3,000 portfolios × asset weights or three statistics |
| `frontier_weights`, `frontier` | 40 optimized points × weights or statistics |
| `comparison_weights`, `comparison` | Four named portfolios × weights or statistics |
| `comparison_returns` | Original return dates × four named portfolios |
| `comparison_summary` | Four portfolios × existing metrics plus `expected_return` |

The three statistics are arithmetic expected return, annualized volatility, and
Sharpe. `period` and `risk_free` keep the dates and rate input with the result.
Weights are nonnegative and sum to one. The random seed is 42, so rerunning the
same inputs produces the same 3,000 simulated allocations. These are alternative
weights applied to existing returns, not generated market observations.

### How to read the charts

The heatmap compares daily raw-asset returns. Correlation near 1 means the assets
often move together; a smaller value suggests more diversification potential.
The printed pairs exclude self-pairs and count each pair once. "Least" means the
smallest signed correlation, not the correlation nearest zero. Sector differences
and overlapping ETF holdings can help explain patterns, but correlation alone
does not establish their cause.

For the approved January 5, 2010–September 25, 2026 return sample, SPY/QQQ
is the most correlated pair (0.930), and XOM/WMT is the least (0.213). Shared
U.S. equity exposure is a plausible explanation for the first pair; different
business drivers may help explain the second. These are interpretations, not
causal findings, and the correlations can change with the evaluation period.

Each colored dot on the frontier chart is one simulated portfolio; its color shows
Sharpe. Horizontal position is annualized standard deviation; vertical position is
arithmetic expected return.
The green line comes from constrained optimization, not from joining random dots.
Its targets begin at the minimum-variance portfolio, keeping only the upper branch.
The four black marker shapes and their legend entries identify:

- Minimum variance: the lowest modeled volatility under the weight constraints.
- Maximum Sharpe: the highest modeled excess return per unit of volatility.
- Equal weight: 10% in each asset, without fitted allocation weights.
- SPY: the single-index comparison, using the same dates and rate input.

The legend includes each portfolio's Sharpe ratio; Sharpe is not a chart axis.
Lower modeled volatility does not guarantee smaller drawdowns or better future
returns. Low correlation can help diversification, but the covariance and weights
determine the combined portfolio's risk.

### Calculations and limits

Expected return is the daily arithmetic mean multiplied by 252. The existing
`annualized_return` remains CAGR (compounded annual growth); it is reported in
the summary but is not used as the frontier's vertical coordinate.
`numpy.cov(..., rowvar=False, ddof=1) * 252` estimates annual sample covariance:
columns represent assets and off-diagonal entries describe their joint movement.
Portfolio variance is `weights @ covariance @ weights`; its square root is volatility.
See [NumPy's covariance documentation](https://numpy.org/doc/stable/reference/generated/numpy.cov.html).

The same Phase 1 risk-free conversion is used throughout: a constant annual rate
becomes `(1 + rate) ** (1 / 252) - 1` per trading day. Sharpe is the annualized daily
excess mean divided by annualized volatility. With a constant rate, excess-return
volatility equals raw-return volatility. No cash interest is added to strategies.
The optimizer requires positive portfolio risk and at least one positive expected
excess return; otherwise it stops rather than presenting an undefined tangency.
Solver failures and constraint violations also stop the analysis. The solver uses
[SciPy SLSQP](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html).

Fixed portfolio weights imply daily rebalancing, unlike letting initial asset
weights drift. Costs are excluded. Weights are fitted and evaluated on the same
history, so these are in-sample estimates, not an out-of-sample trading result.
`plot_portfolios` returns two figures in memory; only the explicitly invoked CLI
shows them. Nothing exports files or refreshes data automatically.

## Existing data

Pass the existing dataset folder explicitly to `load_prices`. It must contain
`raw/daily_ohlcv.csv`, `cleaned/adjusted_close.csv`, and
`quality/quality_report.json`. The adjusted-price table uses a `date` column and
the ten ticker columns listed above, in that order.

The previously downloaded dataset contains 4,208 NYSE sessions from January 4,
2010 through September 25, 2026. Its raw checksum, cleaned adjusted prices, and
665 corporate-action records were checked for consistency. The original provider
marked 115 QQQ observations, January 4 through June 17, 2010, as repaired. This
checks internal consistency, not independent verification of Yahoo's adjustments.

Historical prices already reflect adjustments; recorded split factors must not be
applied again. The September 25 endpoint is intentional and does not trigger a
refresh. No module downloads data, fills gaps, exports results, or modifies input
files. Keep data, old results, and local environments out of commits.

## Calculation conventions

Each signal is exposure to one ticker, as a fraction of that ticker simulation's
equity. Zero is cash and one is fully invested. Signals are decided at the close
and earn the following close-to-close adjusted return. Costs and cash interest
are excluded in this foundation, including the mean-reversion evaluation.

Leading missing signals represent warm-up. Evaluation starts after every ticker
has a usable prior-day signal; later position gaps are rejected. Both equity
curves start at one on the preceding close, while metrics use actual return days.

Annualization uses 252 trading days. Annualized return is compounded growth;
volatility uses the sample standard deviation. Maximum drawdown includes the
starting investment. Win rate is the fraction of all evaluation days with positive
returns, including flat days in the denominator; it is not a completed-trade win rate.

Sharpe is left undefined unless an explicit risk-free input is supplied: either an
annual decimal rate or a Series of daily risk-free returns matching the evaluation
dates. The runner selects those dates from a supplied daily risk-free Series and
fails if a date is missing; it never fills missing rates. A constant annual rate
is converted by compounding over 252 days. Sharpe
uses daily excess returns and is undefined when their standard deviation is zero.

## Local checks

Install the libraries listed in `requirements.txt` in your Python environment.
Run the tests with the existing data folder explicitly selected:

```sh
BACKTEST_DATA=data .venv/bin/python -B -m pytest -p no:cacheprovider -q
```

Tests skip if that input is not supplied;
a skipped suite is not a verified analysis. The tests use existing market observations
and in-memory test positions, and do not create or save market data.

For a headless environment, set `MPLBACKEND=Agg` when running the tests. This
renders charts without opening windows. The Phase 2 checks cover covariance,
weight constraints, shared Sharpe/volatility definitions, SPY alignment,
reproducible simulations, chart rendering, and invalid inputs. The 2% rate in
these checks tests the formulas only; it is not a selected market assumption.
