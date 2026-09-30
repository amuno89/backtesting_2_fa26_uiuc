"""Command-line entry point for the Phase 1 workflow."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from phase1_backtest.config import DEFAULT_START_DATE, PHASE1_TICKERS
from phase1_backtest.data import download_and_clean, load_adjusted_close
from phase1_backtest.reporting import run_phase1_backtests


def _add_tickers(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=list(PHASE1_TICKERS),
        help="Ticker universe (default: the 10 Phase 1 symbols).",
    )


def _add_download_arguments(parser: argparse.ArgumentParser) -> None:
    _add_tickers(parser)
    parser.add_argument("--start", default=DEFAULT_START_DATE, help="Inclusive YYYY-MM-DD date.")
    parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="Exclusive YYYY-MM-DD date; defaults to today so only completed sessions are used.",
    )
    parser.add_argument("--data-dir", default="data", help="Root directory for market data.")


def _add_backtest_arguments(parser: argparse.ArgumentParser, *, include_tickers: bool) -> None:
    if include_tickers:
        _add_tickers(parser)
    parser.add_argument("--output-dir", default="results", help="Directory for backtest outputs.")
    parser.add_argument(
        "--transaction-cost-bps",
        type=float,
        default=0.0,
        help="One-way transaction cost in basis points (default: 0).",
    )
    parser.add_argument(
        "--backtest-start",
        help="Optional evaluation start; earlier downloaded rows remain available as warm-up.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phase1-backtest",
        description="Download Phase 1 data and run four reproducible backtests.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    download_parser = commands.add_parser("download", help="Download and clean market data.")
    _add_download_arguments(download_parser)

    backtest_parser = commands.add_parser("backtest", help="Run strategies on cleaned data.")
    _add_tickers(backtest_parser)
    backtest_parser.add_argument("--data-dir", default="data", help="Root market-data directory.")
    _add_backtest_arguments(backtest_parser, include_tickers=False)

    all_parser = commands.add_parser("all", help="Download, clean, and backtest in one command.")
    _add_download_arguments(all_parser)
    _add_backtest_arguments(all_parser, include_tickers=False)
    return parser


def _run_download(args: argparse.Namespace) -> Path:
    artifacts = download_and_clean(
        tickers=args.tickers,
        start=args.start,
        end=args.end,
        data_dir=args.data_dir,
    )
    print(f"Cleaned adjusted prices: {artifacts.adjusted_close}")
    print(f"Data-quality report: {artifacts.quality_report}")
    return artifacts.adjusted_close


def _run_backtest(args: argparse.Namespace, price_path: Path | None = None) -> None:
    adjusted_close_path = price_path or Path(args.data_dir) / "cleaned" / "adjusted_close.csv"
    prices = load_adjusted_close(adjusted_close_path)
    tickers = tuple(dict.fromkeys(ticker.upper() for ticker in args.tickers))
    missing = [ticker for ticker in tickers if ticker not in prices.columns]
    if missing:
        raise ValueError(f"Cleaned data is missing tickers: {', '.join(missing)}")
    prices = prices.loc[:, list(tickers)]
    artifacts = run_phase1_backtests(
        prices,
        output_dir=args.output_dir,
        transaction_cost_bps=args.transaction_cost_bps,
        backtest_start=args.backtest_start,
    )
    print(f"Performance summary: {artifacts.performance_summary}")
    print(f"Equity curves: {artifacts.equity_curves}")


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "download":
        _run_download(args)
    elif args.command == "backtest":
        _run_backtest(args)
    else:
        price_path = _run_download(args)
        _run_backtest(args, price_path)
