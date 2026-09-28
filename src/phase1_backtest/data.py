"""Download, validate, clean, and persist daily market data."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PRICE_COLUMNS = ("open", "high", "low", "close", "adj_close")
REQUIRED_COLUMNS = (*PRICE_COLUMNS, "volume")
ACTION_COLUMNS = ("dividends", "stock_splits", "capital_gains")
REPAIR_COLUMN = "repaired"
ALL_VALUE_COLUMNS = (*REQUIRED_COLUMNS, *ACTION_COLUMNS, REPAIR_COLUMN)


class DataDownloadError(RuntimeError):
    """Raised when Yahoo Finance does not return usable data for every symbol."""


@dataclass(frozen=True)
class CleanedMarketData:
    """In-memory outputs from the data-cleaning pipeline."""

    cleaned: pd.DataFrame
    adjusted_close: pd.DataFrame
    daily_returns: pd.DataFrame
    corporate_actions: pd.DataFrame
    quality_report: dict[str, Any]


@dataclass(frozen=True)
class DataArtifacts:
    """Paths written by :func:`download_and_clean`."""

    raw: Path
    cleaned: Path
    adjusted_close: Path
    daily_returns: Path
    corporate_actions: Path
    quality_report: Path


def _canonical_column_name(value: object) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("?", "")


def normalize_yfinance_frame(frame: pd.DataFrame, tickers: Iterable[str]) -> pd.DataFrame:
    """Convert a yfinance wide frame into tidy ``date``/``ticker`` rows.

    yfinance has returned both field-first and ticker-first MultiIndex columns
    across releases. This normalizer supports either layout and the flat layout
    returned for a single ticker.
    """

    requested = tuple(dict.fromkeys(str(ticker).upper() for ticker in tickers))
    if not requested:
        raise ValueError("At least one ticker is required.")
    if frame.empty:
        raise DataDownloadError("Yahoo Finance returned an empty data frame.")

    pieces: list[pd.DataFrame] = []
    if isinstance(frame.columns, pd.MultiIndex):
        requested_set = set(requested)
        match_counts = [
            len(requested_set.intersection(map(str, frame.columns.get_level_values(level))))
            for level in range(frame.columns.nlevels)
        ]
        ticker_level = int(np.argmax(match_counts))
        if match_counts[ticker_level] == 0:
            raise DataDownloadError("Could not identify the ticker level in yfinance columns.")
        available = set(map(str, frame.columns.get_level_values(ticker_level)))
        for ticker in requested:
            if ticker not in available:
                continue
            piece = frame.xs(ticker, axis=1, level=ticker_level, drop_level=True).copy()
            if isinstance(piece.columns, pd.MultiIndex):
                piece.columns = piece.columns.get_level_values(-1)
            piece["ticker"] = ticker
            pieces.append(piece)
    else:
        if len(requested) != 1:
            raise DataDownloadError(
                "A flat yfinance response is only valid for a single requested ticker."
            )
        piece = frame.copy()
        piece["ticker"] = requested[0]
        pieces.append(piece)

    if not pieces:
        raise DataDownloadError("Yahoo Finance returned no requested tickers.")

    normalized: list[pd.DataFrame] = []
    for piece in pieces:
        ticker = str(piece.pop("ticker").iloc[0])
        piece.columns = [_canonical_column_name(column) for column in piece.columns]
        piece = piece.loc[:, ~piece.columns.duplicated(keep="last")]
        for column in ALL_VALUE_COLUMNS:
            if column not in piece:
                if column in ACTION_COLUMNS:
                    piece[column] = 0.0
                elif column == REPAIR_COLUMN:
                    piece[column] = False
                else:
                    piece[column] = np.nan
        dates = pd.to_datetime(piece.index, utc=True).tz_convert(None).normalize()
        piece = piece.loc[:, list(ALL_VALUE_COLUMNS)].copy()
        piece.insert(0, "ticker", ticker)
        piece.insert(0, "date", dates)
        normalized.append(piece.reset_index(drop=True))

    result = pd.concat(normalized, ignore_index=True)
    for column in (*REQUIRED_COLUMNS, *ACTION_COLUMNS):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result[REPAIR_COLUMN] = result[REPAIR_COLUMN].fillna(False).astype(bool)
    return result.sort_values(["date", "ticker"], kind="stable").reset_index(drop=True)


def _has_prices(frame: pd.DataFrame, ticker: str) -> bool:
    rows = frame.loc[frame["ticker"].eq(ticker)]
    return not rows.empty and rows["adj_close"].notna().any()


def download_market_data(
    tickers: Iterable[str],
    start: str,
    end: str,
    *,
    download_fn: Callable[..., pd.DataFrame] | None = None,
    retries: int = 2,
) -> pd.DataFrame:
    """Download unadjusted OHLCV, adjusted close, and corporate actions.

    ``start`` is inclusive and ``end`` is exclusive, matching yfinance.
    Empty or all-null symbols are retried individually because batch downloads
    may log a symbol failure without raising an exception.
    """

    requested = tuple(dict.fromkeys(str(ticker).upper() for ticker in tickers))
    if not requested:
        raise ValueError("At least one ticker is required.")
    if pd.Timestamp(start) >= pd.Timestamp(end):
        raise ValueError("start must be earlier than the exclusive end date.")
    if retries < 0:
        raise ValueError("retries must be non-negative.")

    if download_fn is None:
        import yfinance as yf

        download_fn = yf.download

    kwargs: dict[str, Any] = {
        "start": start,
        "end": end,
        "interval": "1d",
        "auto_adjust": False,
        "actions": True,
        "repair": True,
        "keepna": True,
        "group_by": "ticker",
        "multi_level_index": True,
        "ignore_tz": True,
        "prepost": False,
        "rounding": False,
        "threads": False,
        "progress": False,
        "timeout": 30,
    }
    batch = download_fn(tickers=list(requested), **kwargs)
    try:
        normalized = normalize_yfinance_frame(batch, requested)
    except DataDownloadError:
        normalized = pd.DataFrame(columns=("date", "ticker", *ALL_VALUE_COLUMNS))

    missing = [ticker for ticker in requested if not _has_prices(normalized, ticker)]
    recovered: list[pd.DataFrame] = []
    for ticker in missing:
        for _attempt in range(retries):
            single = download_fn(tickers=ticker, **{**kwargs, "threads": False})
            try:
                candidate = normalize_yfinance_frame(single, (ticker,))
            except DataDownloadError:
                continue
            if _has_prices(candidate, ticker):
                recovered.append(candidate)
                break

    if recovered:
        normalized = pd.concat([normalized, *recovered], ignore_index=True)
        normalized = normalized.drop_duplicates(["date", "ticker"], keep="last")

    still_missing = [ticker for ticker in requested if not _has_prices(normalized, ticker)]
    if still_missing:
        joined = ", ".join(still_missing)
        raise DataDownloadError(f"No usable adjusted-close data returned for: {joined}")
    return normalized.sort_values(["date", "ticker"], kind="stable").reset_index(drop=True)


def nyse_sessions(start: str, end: str) -> pd.DatetimeIndex:
    """Return expected NYSE sessions for an inclusive start/exclusive end range."""

    import pandas_market_calendars as market_calendars

    start_at = pd.Timestamp(start).normalize()
    end_at = pd.Timestamp(end).normalize()
    if start_at >= end_at:
        raise ValueError("start must be earlier than the exclusive end date.")
    calendar = market_calendars.get_calendar("NYSE")
    sessions = calendar.valid_days(start_date=start_at, end_date=end_at - pd.Timedelta(days=1))
    return pd.DatetimeIndex(sessions).tz_convert(None).normalize()


def clean_market_data(
    raw: pd.DataFrame,
    *,
    ticker_order: Iterable[str] | None = None,
    expected_sessions: pd.DatetimeIndex | None = None,
) -> CleanedMarketData:
    """Validate downloaded rows and build adjusted-price return matrices.

    Bad observations are removed, but never imputed. Every removal and every
    missing expected exchange session is recorded in the quality report.
    """

    required = {"date", "ticker", *ALL_VALUE_COLUMNS}
    missing_columns = sorted(required.difference(raw.columns))
    if missing_columns:
        raise ValueError(f"Raw data is missing columns: {', '.join(missing_columns)}")
    if raw.empty:
        raise ValueError("Raw data is empty.")

    frame = raw.loc[:, ["date", "ticker", *ALL_VALUE_COLUMNS]].copy()
    frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_convert(None).dt.normalize()
    frame["ticker"] = frame["ticker"].astype(str).str.upper()
    for column in (*REQUIRED_COLUMNS, *ACTION_COLUMNS):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ACTION_COLUMNS:
        frame[column] = frame[column].fillna(0.0)
    if frame[REPAIR_COLUMN].dtype != bool:
        frame[REPAIR_COLUMN] = (
            frame[REPAIR_COLUMN]
            .astype(str)
            .str.strip()
            .str.lower()
            .map({"true": True, "1": True, "false": False, "0": False})
            .fillna(False)
        )

    duplicate_rows = int(frame.duplicated(["date", "ticker"], keep="last").sum())
    frame = frame.drop_duplicates(["date", "ticker"], keep="last")
    null_counts = {
        column: int(frame[column].isna().sum()) for column in REQUIRED_COLUMNS
    }

    nonpositive_price = frame.loc[:, PRICE_COLUMNS].le(0).any(axis=1)
    negative_volume = frame["volume"].lt(0)
    incomplete = frame.loc[:, REQUIRED_COLUMNS].isna().any(axis=1)
    invalid_ohlc = (
        frame["high"].lt(frame[["open", "low", "close"]].max(axis=1))
        | frame["low"].gt(frame[["open", "high", "close"]].min(axis=1))
    )
    invalid = incomplete | nonpositive_price | negative_volume | invalid_ohlc

    cleaned = (
        frame.loc[~invalid]
        .sort_values(["date", "ticker"], kind="stable")
        .reset_index(drop=True)
    )
    if cleaned.empty:
        raise ValueError("No valid rows remain after cleaning.")

    observed_order = tuple(dict.fromkeys(cleaned["ticker"]))
    order = tuple(dict.fromkeys(str(ticker).upper() for ticker in (ticker_order or observed_order)))
    absent = [ticker for ticker in order if ticker not in set(cleaned["ticker"])]
    if absent:
        raise ValueError(f"No clean rows remain for: {', '.join(absent)}")

    cleaned["adj_return"] = cleaned.groupby("ticker", sort=False)["adj_close"].pct_change(
        fill_method=None
    )

    if expected_sessions is None:
        expected = pd.DatetimeIndex(cleaned["date"].unique()).sort_values()
    else:
        expected = (
            pd.DatetimeIndex(expected_sessions)
            .tz_localize(None)
            .normalize()
            .unique()
            .sort_values()
        )

    adjusted_close = cleaned.pivot(index="date", columns="ticker", values="adj_close")
    adjusted_close = adjusted_close.reindex(index=expected, columns=list(order)).sort_index()
    adjusted_close.index.name = "date"
    adjusted_close.columns.name = None
    daily_returns = adjusted_close.pct_change(fill_method=None)

    action_mask = frame.loc[:, ACTION_COLUMNS].ne(0).any(axis=1)
    corporate_actions = frame.loc[
        action_mask, ["date", "ticker", *ACTION_COLUMNS]
    ].sort_values(["date", "ticker"], kind="stable")
    corporate_actions = corporate_actions.reset_index(drop=True)

    per_ticker: dict[str, dict[str, Any]] = {}
    for ticker in order:
        ticker_rows = cleaned.loc[cleaned["ticker"].eq(ticker)]
        observed = pd.DatetimeIndex(ticker_rows["date"].unique()).sort_values()
        missing_dates = expected.difference(observed)
        unexpected_dates = observed.difference(expected)
        action_rows = corporate_actions.loc[corporate_actions["ticker"].eq(ticker)]
        per_ticker[ticker] = {
            "rows": int(len(ticker_rows)),
            "first_date": observed.min().date().isoformat(),
            "last_date": observed.max().date().isoformat(),
            "missing_session_count": int(len(missing_dates)),
            "missing_sessions": [stamp.date().isoformat() for stamp in missing_dates],
            "unexpected_session_count": int(len(unexpected_dates)),
            "unexpected_sessions": [stamp.date().isoformat() for stamp in unexpected_dates],
            "dividend_events": int(action_rows["dividends"].ne(0).sum()),
            "split_events": int(action_rows["stock_splits"].ne(0).sum()),
            "capital_gain_events": int(action_rows["capital_gains"].ne(0).sum()),
            "repaired_rows": int(ticker_rows[REPAIR_COLUMN].sum()),
        }

    quality_report: dict[str, Any] = {
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "rows_received": int(len(raw)),
        "rows_after_deduplication": int(len(frame)),
        "rows_clean": int(len(cleaned)),
        "rows_removed": int(invalid.sum()),
        "duplicate_rows_removed": duplicate_rows,
        "invalid_row_counts": {
            "incomplete_ohlcv": int(incomplete.sum()),
            "nonpositive_price": int(nonpositive_price.sum()),
            "negative_volume": int(negative_volume.sum()),
            "invalid_ohlc_relationship": int(invalid_ohlc.sum()),
        },
        "null_counts_before_cleaning": null_counts,
        "expected_nyse_sessions": int(len(expected)),
        "warning_counts": {
            "zero_volume": int(cleaned["volume"].eq(0).sum()),
            "large_adjusted_return_over_50pct": int(cleaned["adj_return"].abs().gt(0.50).sum()),
            "repaired_rows": int(cleaned[REPAIR_COLUMN].sum()),
            "negative_dividends": int(cleaned["dividends"].lt(0).sum()),
            "invalid_split_factors": int(
                (
                    cleaned["stock_splits"].ne(0)
                    & (cleaned["stock_splits"].le(0) | cleaned["stock_splits"].eq(1))
                ).sum()
            ),
        },
        "per_ticker": per_ticker,
    }
    return CleanedMarketData(
        cleaned=cleaned,
        adjusted_close=adjusted_close,
        daily_returns=daily_returns,
        corporate_actions=corporate_actions,
        quality_report=quality_report,
    )


def _write_csv(frame: pd.DataFrame, path: Path, *, index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=index, date_format="%Y-%m-%d", float_format="%.10g")
    temporary.replace(path)


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def download_and_clean(
    *,
    tickers: Iterable[str],
    start: str,
    end: str | None = None,
    data_dir: str | Path = "data",
    download_fn: Callable[..., pd.DataFrame] | None = None,
) -> DataArtifacts:
    """Run the complete download/clean/save workflow."""

    resolved_end = end or date.today().isoformat()
    ticker_order = tuple(dict.fromkeys(str(ticker).upper() for ticker in tickers))
    raw = download_market_data(
        ticker_order,
        start,
        resolved_end,
        download_fn=download_fn,
    )
    sessions = nyse_sessions(start, resolved_end)
    outputs = clean_market_data(raw, ticker_order=ticker_order, expected_sessions=sessions)
    outputs.quality_report["request"] = {
        "tickers": list(ticker_order),
        "start_inclusive": start,
        "end_exclusive": resolved_end,
        "interval": "1d",
        "auto_adjust": False,
        "actions": True,
        "repair": True,
        "keepna": True,
        "return_price_field": "adj_close",
        "yfinance_version": importlib.metadata.version("yfinance"),
    }

    root = Path(data_dir)
    artifacts = DataArtifacts(
        raw=root / "raw" / "daily_ohlcv.csv",
        cleaned=root / "cleaned" / "daily_ohlcv.csv",
        adjusted_close=root / "cleaned" / "adjusted_close.csv",
        daily_returns=root / "cleaned" / "daily_returns.csv",
        corporate_actions=root / "quality" / "corporate_actions.csv",
        quality_report=root / "quality" / "quality_report.json",
    )
    _write_csv(raw, artifacts.raw)
    outputs.quality_report["source_sha256"] = hashlib.sha256(artifacts.raw.read_bytes()).hexdigest()
    _write_csv(outputs.cleaned, artifacts.cleaned)
    _write_csv(outputs.adjusted_close, artifacts.adjusted_close, index=True)
    _write_csv(outputs.daily_returns, artifacts.daily_returns, index=True)
    _write_csv(outputs.corporate_actions, artifacts.corporate_actions)
    _write_json(outputs.quality_report, artifacts.quality_report)
    return artifacts


def load_adjusted_close(path: str | Path) -> pd.DataFrame:
    """Load and validate a saved adjusted-close matrix."""

    prices = pd.read_csv(path, index_col="date", parse_dates=["date"])
    prices.index = pd.DatetimeIndex(prices.index).tz_localize(None).normalize()
    prices = prices.apply(pd.to_numeric, errors="coerce")
    if prices.empty:
        raise ValueError("Adjusted-close data is empty.")
    if prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise ValueError("Adjusted-close dates must be unique and increasing.")
    return prices
