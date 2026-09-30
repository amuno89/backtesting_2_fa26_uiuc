# Backtesting Group 2 — Phase 1

This repository contains the Fall 2026 Financial Engineering Club project's reproducible Phase 1 data pipeline and strategy backtests.

The Phase 1 universe is:

`SPY, QQQ, IWM, AAPL, JPM, XOM, JNJ, PG, WMT, CAT`

## What is implemented

- Daily OHLCV, adjusted close, dividends, stock splits, and capital gains downloaded with `yfinance`.
- Data validation against the NYSE trading calendar, including missing-session, duplicate, null, invalid-price, volume, repair, and corporate-action checks.
- A true equal-dollar buy-and-hold benchmark whose shares remain fixed and whose weights drift.
- A 50/200-day moving-average crossover strategy.
- A 12-month cross-sectional momentum strategy that buys the top three names at each month-end.
- An RSI(14) mean-reversion strategy that owns names only while RSI is below 30.
- An event-driven portfolio simulator with one-session signal lag, cash, drifting weights, and optional transaction costs.
- Detailed strategy files and a performance summary containing return, CAGR, volatility, Sharpe ratio, drawdown, turnover, costs, and exposure.

Every return and price-derived signal uses adjusted close. Raw close and corporate-action fields are retained for inspection; dividends are not added to adjusted returns a second time.

## Setup

Python 3.10 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

The `yfinance[repair]` version is pinned in `pyproject.toml` so the provider interface and repair dependencies are reproducible.

## Run the workflow

Download, clean, and backtest in one command:

```bash
phase1-backtest all --start 2010-01-01 --end 2026-09-28
```

`--start` is inclusive and `--end` is exclusive, matching `yfinance`. The default end is today, which excludes the current potentially incomplete session. The default start is `2010-01-01`; both dates are configurable because the project brief does not prescribe a sample period.

The two stages can also be run separately:

```bash
phase1-backtest download --start 2010-01-01 --end 2026-09-28
phase1-backtest backtest
```

To reserve downloaded history for indicator warm-up while evaluating a later period:

```bash
phase1-backtest all \
  --start 2010-01-01 \
  --backtest-start 2011-01-03 \
  --transaction-cost-bps 5
```

The same interface is available without the installed console script:

```bash
python -m phase1_backtest all --start 2010-01-01
```

## Outputs

Generated data is kept out of Git because Yahoo data can be revised and may be subject to provider terms. Each run preserves the exact local source snapshot and its SHA-256 hash.

```text
data/
├── raw/daily_ohlcv.csv
├── cleaned/daily_ohlcv.csv
├── cleaned/adjusted_close.csv
├── cleaned/daily_returns.csv
├── quality/corporate_actions.csv
└── quality/quality_report.json

results/
├── performance_summary.csv
├── equity_curves.csv
├── daily_returns.csv
└── strategies/<strategy>/
    ├── daily_performance.csv
    ├── target_weights.csv
    ├── held_weights.csv
    ├── end_of_day_weights.csv
    └── strategy signal and indicator files (active strategies)
```

The quality report records the request, package version, source hash, expected NYSE sessions, missing dates by ticker, row removals, corporate-action counts, and warnings. Prices are never forward- or backward-filled. A backtest fails clearly if its adjusted-price matrix contains a missing value.

## Backtest conventions

- Signals use information available through close `t` and first earn the return from `t` to `t+1`.
- Strategies are long-only, unlevered, and hold zero-return cash when no ticker qualifies.
- Moving-average and RSI portfolios rebalance when their eligible set changes.
- Momentum uses `P[t] / P[t-252] - 1`, deterministic ticker-order tie-breaking, and equal weights among the top three at the final observed session of each calendar month.
- Buy-and-hold invests 10% in each ticker at the first evaluation close and never rebalances.
- Transaction costs default to zero and can be set in one-way basis points. Turnover accounts for weights drifting between trades.
- Summary metrics cover the requested evaluation range, including strategy warm-up if `--backtest-start` is not supplied.

These choices are explicit defaults because no dates, transaction costs, momentum portfolio size, or RSI exit rule were specified in the project brief.

## Tests

Unit tests use deterministic synthetic prices and mocked downloader responses; they do not depend on live Yahoo data.

```bash
ruff check .
pytest
```

To make changes, create a new branch, commit the changes to that branch, and open a pull request into `main`.
