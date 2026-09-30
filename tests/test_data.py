from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase1_backtest.data import (
    ALL_VALUE_COLUMNS,
    DataDownloadError,
    clean_market_data,
    download_market_data,
    normalize_yfinance_frame,
)

YFINANCE_FIELDS = (
    "Open",
    "High",
    "Low",
    "Close",
    "Adj Close",
    "Volume",
    "Dividends",
    "Stock Splits",
    "Capital Gains",
    "Repaired?",
)


def _ticker_values(base: float, *, split_on_second_day: float = 0.0) -> dict[str, list[object]]:
    return {
        "Open": [base, base + 1.0],
        "High": [base + 2.0, base + 3.0],
        "Low": [base - 1.0, base],
        "Close": [base + 1.0, base + 2.0],
        "Adj Close": [base + 0.5, base + 1.5],
        "Volume": [1_000, 1_100],
        "Dividends": [0.0, 0.25],
        "Stock Splits": [0.0, split_on_second_day],
        "Capital Gains": [0.0, 0.0],
        "Repaired?": [False, True],
    }


def _multiindex_frame(
    ticker_values: dict[str, dict[str, list[object]]],
    *,
    ticker_first: bool = True,
) -> pd.DataFrame:
    dates = pd.DatetimeIndex(["2024-01-02", "2024-01-03"], name="Date")
    data: dict[tuple[str, str], list[object]] = {}
    for ticker, values in ticker_values.items():
        for field in YFINANCE_FIELDS:
            key = (ticker, field) if ticker_first else (field, ticker)
            data[key] = values[field]
    names = ("Ticker", "Price") if ticker_first else ("Price", "Ticker")
    frame = pd.DataFrame(data, index=dates)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=names)
    return frame


def _clean_input(
    ticker: str,
    dates: list[str],
    *,
    close: list[float] | None = None,
    adjusted_close: list[float] | None = None,
    stock_splits: list[float] | None = None,
) -> pd.DataFrame:
    count = len(dates)
    close_values = close or [100.0 + offset for offset in range(count)]
    adjusted_values = adjusted_close or close_values
    split_values = stock_splits or [0.0] * count
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "ticker": [ticker] * count,
            "open": close_values,
            "high": [value + 1.0 for value in close_values],
            "low": [value - 1.0 for value in close_values],
            "close": close_values,
            "adj_close": adjusted_values,
            "volume": [1_000] * count,
            "dividends": [0.0] * count,
            "stock_splits": split_values,
            "capital_gains": [0.0] * count,
            "repaired": [False] * count,
        }
    )


@pytest.mark.parametrize("ticker_first", [True, False])
def test_normalize_yfinance_frame_supports_both_multiindex_layouts(
    ticker_first: bool,
) -> None:
    frame = _multiindex_frame(
        {
            "SPY": _ticker_values(100.0),
            "AAPL": _ticker_values(200.0, split_on_second_day=4.0),
        },
        ticker_first=ticker_first,
    )

    normalized = normalize_yfinance_frame(frame, ("SPY", "AAPL"))

    assert list(normalized.columns) == ["date", "ticker", *ALL_VALUE_COLUMNS]
    assert len(normalized) == 4
    assert normalized["date"].dt.tz is None
    assert normalized[["date", "ticker"]].equals(
        normalized[["date", "ticker"]].sort_values(["date", "ticker"]).reset_index(drop=True)
    )

    aapl_second_day = normalized.loc[
        normalized["ticker"].eq("AAPL") & normalized["date"].eq(pd.Timestamp("2024-01-03"))
    ].squeeze()
    assert aapl_second_day["adj_close"] == pytest.approx(201.5)
    assert aapl_second_day["stock_splits"] == pytest.approx(4.0)
    assert bool(aapl_second_day["repaired"]) is True


def test_clean_market_data_uses_adjusted_close_for_return_across_split() -> None:
    raw = _clean_input(
        "AAPL",
        ["2024-06-06", "2024-06-07", "2024-06-10"],
        close=[100.0, 51.0, 52.0],
        adjusted_close=[50.0, 51.0, 52.0],
        stock_splits=[0.0, 2.0, 0.0],
    )
    sessions = pd.to_datetime(["2024-06-06", "2024-06-07", "2024-06-10"])

    result = clean_market_data(raw, ticker_order=("AAPL",), expected_sessions=sessions)

    split_day = pd.Timestamp("2024-06-07")
    assert result.daily_returns.loc[split_day, "AAPL"] == pytest.approx(0.02)
    assert result.daily_returns.loc[split_day, "AAPL"] != pytest.approx(-0.49)
    cleaned_return = result.cleaned.loc[result.cleaned["date"].eq(split_day), "adj_return"].item()
    assert cleaned_return == pytest.approx(0.02)
    assert result.corporate_actions.to_dict("records") == [
        {
            "date": split_day,
            "ticker": "AAPL",
            "dividends": 0.0,
            "stock_splits": 2.0,
            "capital_gains": 0.0,
        }
    ]


def test_clean_market_data_reports_missing_expected_session() -> None:
    raw = _clean_input("SPY", ["2024-01-02", "2024-01-04"])
    expected_sessions = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])

    result = clean_market_data(
        raw,
        ticker_order=("SPY",),
        expected_sessions=expected_sessions,
    )

    spy_quality = result.quality_report["per_ticker"]["SPY"]
    assert spy_quality["missing_session_count"] == 1
    assert spy_quality["missing_sessions"] == ["2024-01-03"]
    assert spy_quality["unexpected_session_count"] == 0
    assert pd.Timestamp("2024-01-03") in result.adjusted_close.index
    assert pd.isna(result.adjusted_close.loc["2024-01-03", "SPY"])


def test_download_market_data_retries_all_null_ticker_until_recovered() -> None:
    batch_values = {
        "SPY": _ticker_values(100.0),
        "AAPL": {field: [np.nan, np.nan] for field in YFINANCE_FIELDS},
    }
    recovered_aapl = _multiindex_frame({"AAPL": _ticker_values(200.0)})
    calls: list[object] = []

    def fake_download(*, tickers: object, **kwargs: object) -> pd.DataFrame:
        calls.append(tickers)
        assert kwargs["auto_adjust"] is False
        assert kwargs["actions"] is True
        assert kwargs["repair"] is True
        assert kwargs["keepna"] is True
        if isinstance(tickers, list):
            return _multiindex_frame(batch_values)
        if calls.count("AAPL") == 1:
            return pd.DataFrame()
        return recovered_aapl

    result = download_market_data(
        ("SPY", "AAPL"),
        "2024-01-02",
        "2024-01-04",
        download_fn=fake_download,
        retries=2,
    )

    assert calls == [["SPY", "AAPL"], "AAPL", "AAPL"]
    assert set(result["ticker"]) == {"SPY", "AAPL"}
    assert result.loc[result["ticker"].eq("AAPL"), "adj_close"].notna().all()


def test_download_market_data_raises_after_missing_ticker_exhausts_retries() -> None:
    batch = _multiindex_frame({"SPY": _ticker_values(100.0)})
    calls: list[object] = []

    def fake_download(*, tickers: object, **_kwargs: object) -> pd.DataFrame:
        calls.append(tickers)
        if isinstance(tickers, list):
            return batch
        return pd.DataFrame()

    with pytest.raises(
        DataDownloadError,
        match=r"No usable adjusted-close data returned for: AAPL",
    ):
        download_market_data(
            ("SPY", "AAPL"),
            "2024-01-02",
            "2024-01-04",
            download_fn=fake_download,
            retries=2,
        )

    assert calls == [["SPY", "AAPL"], "AAPL", "AAPL"]
