# backtesting_2_fa26_uiuc
Repository for Backtesting group 2 for Fall 2026 semester's Financial Engineering club projects.

The tickers being used for phase 1 are: SPY, QQQ, IWM, AAPL, JPM, XOM, JNJ, PG, WMT, CAT

To make changes, create a new branch for your changes, commit the changes to that branch, and then create a pull request to merge the branch with `main`.

## Current work

This branch starts a small, offline backtesting foundation. A trading strategy and
risk-free input have not yet been selected, so there is no strategy implementation
or main analysis script. Completed coding work goes to `zy066299-Kevin-Zhao` and
then through a pull request into `main`.

- `data.py` reads the approved dataset, verifies its raw-file checksum, compares
  adjusted prices with the raw observations, and checks the NYSE trading calendar.
- `backtest.py` applies supplied positions to the following day's returns and
  compares each ticker with buy-and-hold over the same dates.
- `metrics.py` calculates performance statistics from a daily return table.
- `tests/test_core.py` checks these functions against existing local observations.

The selected strategy, main script, plots, and portfolio analysis will be added
only when their required choices and scope are supplied. Each file keeps the role
in the agreed plan. All source, tests, comments, and blank lines combined must stay
below 500 lines; the full-project planning target is about 350-360 lines.

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
are excluded in this foundation; strategy-specific assumptions remain to be set.

Leading missing signals represent warm-up. Evaluation starts after every ticker
has a usable prior-day signal; later position gaps are rejected. Both equity
curves start at one on the preceding close, while metrics use actual return days.

Annualization uses 252 trading days. Annualized return is compounded growth;
volatility uses the sample standard deviation. Maximum drawdown includes the
starting investment. Win rate is the fraction of all evaluation days with positive
returns, including flat days in the denominator; it is not a completed-trade win rate.

Sharpe is left undefined unless an explicit risk-free input is supplied: either an
annual decimal rate or a Series of daily risk-free returns matching the evaluation
dates. A constant annual rate is converted by compounding over 252 days. Sharpe
uses daily excess returns and is undefined when their standard deviation is zero.

## Local checks

Install the libraries listed in `requirements.txt` in your Python environment.
Run the tests with `BACKTEST_DATA` set explicitly to the existing data folder, using
`python -B -m pytest -p no:cacheprovider -q`. Tests skip if that input is not supplied;
a skipped suite is not a verified analysis. The tests use existing market observations
and in-memory test positions, and do not create or save market data.
