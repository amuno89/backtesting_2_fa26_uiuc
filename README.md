# backtesting_2_fa26_uiuc
Repository for Backtesting group 2 for Fall 2026 semester's Financial Engineering club projects.

The tickers being used for phase 1 are: SPY, QQQ, IWM, AAPL, JPM, XOM, JNJ, PG, WMT, CAT

To make changes, create a new branch for your changes, commit the changes to that branch, and then create a pull request to merge the branch with `main`.

## Current work

This is a small, offline backtesting foundation with one entry point: `run.py`.
The command-line runner uses buy-and-hold; RSI mean reversion is available through
the same Python workflow. A risk-free input has not been selected.
Completed coding work goes to `zy066299-Kevin-Zhao`
and then through a pull request into `main`.

- `run.py` loads the data once, calls the calculations, and returns their results.
- `data.py` reads the approved dataset, verifies its raw-file checksum, compares
  adjusted prices with the raw observations, and checks the NYSE trading calendar.
- `backtest.py` applies supplied positions to the following day's returns and
  compares each ticker with buy-and-hold over the same dates.
- `metrics.py` calculates performance statistics from a daily return table.
- `mean_reversion.py` returns RSI-based signals independently of Golden Cross.
- `tests/test_core.py` checks these functions against existing local observations.

Other strategies, plots, and portfolio analysis will be added
only when their required choices and scope are supplied. Each file keeps the role
in the agreed plan. All source, tests, comments, and blank lines combined must stay
below 500 lines. The complete mean-reversion addition, including tests, must add
no more than 100 code lines.

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

When requested, Phase 2 will pass `asset_returns` to `portfolio.py`, and Phase 3
will pass the approved strategy-return tables to the same portfolio functions.
Both phases can use `summarize` with portfolio names as columns and `equity_curve`
for growth calculations. The matched evaluation dates make comparisons fair;
`prices` retains the full history when an explicitly different period is required.

The portfolio and plotting modules are not implemented
yet. Phase 3 must not mistake a benchmark-only result for a selected strategy or
claim diversification across different strategies when only one is supplied.

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
