"""
tests/test_indicators.py

Unit tests for src/indicators.py.

Run:
  .\\.venv\\Scripts\\python.exe -m pytest tests\\test_indicators.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from indicators import (  # noqa: E402
    IndicatorConfig,
    add_indicator_columns,
    calculate_indicators_for_tickers,
    latest_indicator_snapshot,
)


def make_price_df(days: int = 220) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=days, freq="D")

    close = pd.Series(range(100, 100 + days), index=dates, dtype="float64")
    high = close + 1.0
    low = close - 1.0
    open_ = close - 0.5
    volume = pd.Series(range(1_000_000, 1_000_000 + days), index=dates, dtype="float64")

    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=dates,
    )


def make_bday_price_df(days: int = 220) -> pd.DataFrame:
    """
    Business-day version for market-like test data.

    Existing make_price_df is intentionally kept for backward compatibility.
    """
    dates = pd.bdate_range("2025-01-01", periods=days)

    close = pd.Series(range(100, 100 + days), index=dates, dtype="float64")
    high = close + 1.0
    low = close - 1.0
    open_ = close - 0.5
    volume = pd.Series(range(1_000_000, 1_000_000 + days), index=dates, dtype="float64")

    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        },
        index=dates,
    )


def make_multiindex_price_ticker_df(ticker: str = "AAPL", days: int = 220) -> pd.DataFrame:
    """
    Build a yfinance-like 2-level MultiIndex DataFrame:

        ('Open', 'AAPL')
        ('High', 'AAPL')
        ('Low', 'AAPL')
        ('Close', 'AAPL')
        ('Volume', 'AAPL')
    """
    base = make_bday_price_df(days=days)

    multi_columns = pd.MultiIndex.from_tuples(
        [(col, ticker) for col in base.columns],
        names=["Price", "Ticker"],
    )

    out = base.copy()
    out.columns = multi_columns

    return out


def make_zero_volume_price_df(days: int = 220) -> pd.DataFrame:
    """
    Used for index-like symbols such as ^VIX where volume can be missing or zero.
    """
    df = make_bday_price_df(days=days)
    df["Volume"] = 0.0
    return df


def test_add_indicator_columns_contains_required_outputs() -> None:
    df = make_price_df()
    result = add_indicator_columns(df)

    expected_columns = {
        "close",
        "change_pct",
        "20DMA",
        "50DMA",
        "200DMA",
        "volume",
        "volume_20d_avg",
        "volume_ratio",
        "5D_return",
        "20D_return",
        "20D_high_proximity",
        "20D_low_proximity",
        "close_above_20dma",
        "close_above_50dma",
        "close_above_200dma",
    }

    assert expected_columns.issubset(set(result.columns))


def test_moving_averages_are_correct_on_latest_row() -> None:
    df = make_price_df(days=220)
    result = add_indicator_columns(df)
    latest = result.iloc[-1]

    closes = df["Close"]

    assert latest["20DMA"] == pytest.approx(closes.tail(20).mean())
    assert latest["50DMA"] == pytest.approx(closes.tail(50).mean())
    assert latest["200DMA"] == pytest.approx(closes.tail(200).mean())


def test_change_pct_and_returns_are_percent_values() -> None:
    df = make_price_df(days=30)
    result = add_indicator_columns(df)
    latest = result.iloc[-1]

    closes = df["Close"]

    expected_1d = ((closes.iloc[-1] / closes.iloc[-2]) - 1.0) * 100.0
    expected_5d = ((closes.iloc[-1] / closes.iloc[-6]) - 1.0) * 100.0
    expected_20d = ((closes.iloc[-1] / closes.iloc[-21]) - 1.0) * 100.0

    assert latest["change_pct"] == pytest.approx(expected_1d)
    assert latest["5D_return"] == pytest.approx(expected_5d)
    assert latest["20D_return"] == pytest.approx(expected_20d)


def test_volume_ratio_is_volume_divided_by_20d_average() -> None:
    df = make_price_df(days=30)
    result = add_indicator_columns(df)
    latest = result.iloc[-1]

    expected_avg = df["Volume"].tail(20).mean()
    expected_ratio = df["Volume"].iloc[-1] / expected_avg

    assert latest["volume_20d_avg"] == pytest.approx(expected_avg)
    assert latest["volume_ratio"] == pytest.approx(expected_ratio)


def test_high_low_proximity_calculation() -> None:
    df = make_price_df(days=30)
    result = add_indicator_columns(df)
    latest = result.iloc[-1]

    close = df["Close"].iloc[-1]
    high_20d = df["High"].tail(20).max()
    low_20d = df["Low"].tail(20).min()

    expected_high_proximity = ((close / high_20d) - 1.0) * 100.0
    expected_low_proximity = ((close / low_20d) - 1.0) * 100.0

    assert latest["20D_high_proximity"] == pytest.approx(expected_high_proximity)
    assert latest["20D_low_proximity"] == pytest.approx(expected_low_proximity)


def test_close_above_dma_flags_are_booleans() -> None:
    df = make_price_df(days=220)
    snapshot = latest_indicator_snapshot(df, ticker="TEST")

    assert snapshot["ticker"] == "TEST"
    assert isinstance(snapshot["close_above_20dma"], bool)
    assert isinstance(snapshot["close_above_50dma"], bool)
    assert isinstance(snapshot["close_above_200dma"], bool)

    # Up-trending test data should close above all moving averages.
    assert snapshot["close_above_20dma"] is True
    assert snapshot["close_above_50dma"] is True
    assert snapshot["close_above_200dma"] is True


def test_latest_indicator_snapshot_is_json_friendly() -> None:
    df = make_price_df(days=220)
    snapshot = latest_indicator_snapshot(df, ticker="NVDA")

    assert snapshot["ticker"] == "NVDA"
    assert isinstance(snapshot["date"], str)
    assert isinstance(snapshot["close"], float)
    assert isinstance(snapshot["volume"], float)
    assert snapshot["close"] is not None


def test_calculate_indicators_for_tickers_handles_bad_ticker_without_crashing() -> None:
    good_df = make_price_df(days=220)
    bad_df = pd.DataFrame()

    indicators, notes = calculate_indicators_for_tickers(
        {
            "GOOD": good_df,
            "BAD": bad_df,
        }
    )

    assert "GOOD" in indicators
    assert "BAD" not in indicators
    assert len(notes) == 1
    assert "BAD" in notes[0]


def test_missing_close_raises_value_error() -> None:
    df = pd.DataFrame(
        {
            "Volume": [100, 200, 300],
        },
        index=pd.date_range("2025-01-01", periods=3),
    )

    with pytest.raises(ValueError):
        add_indicator_columns(df)


def test_custom_indicator_config() -> None:
    df = make_price_df(days=20)
    config = IndicatorConfig(
        ma_short=3,
        ma_mid=5,
        ma_long=10,
        volume_avg_window=3,
        return_short_window=2,
        return_mid_window=4,
        high_low_window=5,
    )

    result = add_indicator_columns(df, config=config)
    latest = result.iloc[-1]

    closes = df["Close"]

    assert latest["20DMA"] == pytest.approx(closes.tail(3).mean())
    assert latest["50DMA"] == pytest.approx(closes.tail(5).mean())
    assert latest["200DMA"] == pytest.approx(closes.tail(10).mean())


def test_latest_indicator_snapshot_accepts_yfinance_2level_multiindex_columns() -> None:
    """
    Regression test for yfinance 0.2.x single-ticker MultiIndex output.

    The old implementation joined ('Close', 'AAPL') into 'close_aapl',
    causing the indicator logic to fail to find 'close'.
    """
    df = make_multiindex_price_ticker_df(ticker="AAPL", days=220)

    snapshot = latest_indicator_snapshot(df, ticker="AAPL")

    assert snapshot["ticker"] == "AAPL"
    assert snapshot["close"] is not None
    assert snapshot["volume"] is not None
    assert snapshot["20DMA"] is not None
    assert snapshot["close_above_20dma"] is True


def test_zero_volume_symbol_does_not_crash_and_volume_ratio_is_none() -> None:
    """
    Index-like symbols such as ^VIX can have missing or zero volume.

    Expected:
    - indicator calculation should not crash
    - volume is 0
    - volume_20d_avg is 0
    - volume_ratio becomes None after JSON-friendly conversion
    """
    df = make_zero_volume_price_df(days=220)

    snapshot = latest_indicator_snapshot(df, ticker="^VIX")

    assert snapshot["ticker"] == "^VIX"
    assert snapshot["close"] is not None
    assert snapshot["volume"] == 0.0
    assert snapshot["volume_20d_avg"] == 0.0
    assert snapshot["volume_ratio"] is None


def test_bday_price_df_works_with_indicator_calculation() -> None:
    """
    Business-day data should work the same way as daily calendar data.
    """
    df = make_bday_price_df(days=220)

    snapshot = latest_indicator_snapshot(df, ticker="QQQ")

    assert snapshot["ticker"] == "QQQ"
    assert snapshot["close"] is not None
    assert snapshot["20DMA"] is not None
    assert snapshot["50DMA"] is not None
    assert snapshot["200DMA"] is not None