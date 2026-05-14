"""
src/indicators.py

Price indicator calculation module for Personal Trading OS MVP.

Responsibilities:
- Calculate ticker-level technical indicators from OHLCV price history.
- Keep indicator logic independent from yfinance/network/config.
- Return latest indicator snapshot for downstream modules:
  market_regime.py, watchlist_ranker.py, setup_matcher.py, packet_builder.py

Python: 3.12
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {"close", "volume"}


@dataclass(frozen=True)
class IndicatorConfig:
    ma_short: int = 20
    ma_mid: int = 50
    ma_long: int = 200
    volume_avg_window: int = 20
    return_short_window: int = 5
    return_mid_window: int = 20
    high_low_window: int = 20


def _flatten_yfinance_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize possible yfinance MultiIndex columns.

    yfinance 0.2.x may return a 2-level MultiIndex even for a single ticker:
        ('Close', 'AAPL')
        ('Volume', 'AAPL')

    In that case, the correct OHLCV column name is level 0:
        Close
        Volume

    For other MultiIndex shapes, fall back to joined column names.
    """
    if not isinstance(df.columns, pd.MultiIndex):
        return df

    out = df.copy()

    if out.columns.nlevels == 2:
        out.columns = out.columns.get_level_values(0)
    else:
        out.columns = [
            "_".join(str(part) for part in col if str(part) != "").strip()
            for col in out.columns.to_flat_index()
        ]

    return out


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize OHLCV DataFrame column names to lowercase.

    Accepts columns such as:
    - Open, High, Low, Close, Adj Close, Volume
    - open, high, low, close, volume
    - yfinance 2-level MultiIndex columns such as ('Close', 'AAPL')
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    out = _flatten_yfinance_columns(out)

    rename_map: dict[Any, str] = {}
    for col in out.columns:
        normalized = str(col).strip().lower().replace(" ", "_")
        rename_map[col] = normalized

    out = out.rename(columns=rename_map)

    # Prefer regular close. If missing, fall back to adj_close.
    if "close" not in out.columns and "adj_close" in out.columns:
        out["close"] = out["adj_close"]

    return out


def _safe_pct_change(series: pd.Series, periods: int) -> pd.Series:
    """
    pandas pct_change wrapper that avoids noisy inf values.
    """
    result = series.pct_change(periods=periods) * 100.0
    return result.replace([np.inf, -np.inf], np.nan)


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """
    Divide two series and return NaN when denominator is zero or missing.
    """
    denominator = denominator.replace(0, np.nan)
    result = numerator / denominator
    return result.replace([np.inf, -np.inf], np.nan)


def add_indicator_columns(
    price_df: pd.DataFrame,
    config: IndicatorConfig | None = None,
) -> pd.DataFrame:
    """
    Add rolling indicators to a full OHLCV price DataFrame.

    Returned columns include:
    - close
    - change_pct
    - 20DMA
    - 50DMA
    - 200DMA
    - 20DMA_valid
    - 50DMA_valid
    - 200DMA_valid
    - volume
    - volume_20d_avg
    - volume_ratio
    - 5D_return
    - 20D_return
    - 20D_high_proximity
    - 20D_low_proximity
    - close_above_20dma
    - close_above_50dma
    - close_above_200dma

    Important:
    - DMA values are calculated with min_periods=1 for graceful MVP operation.
    - Use *_valid flags to decide whether the corresponding DMA has enough
      real observations for scoring.
    """
    cfg = config or IndicatorConfig()
    df = _normalize_columns(price_df)

    if df.empty:
        return pd.DataFrame()

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Price DataFrame missing required columns: {sorted(missing)}")

    df = df.sort_index().copy()

    # Ensure numeric calculation columns.
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "high" not in df.columns:
        df["high"] = df["close"]

    if "low" not in df.columns:
        df["low"] = df["close"]

    df["change_pct"] = _safe_pct_change(df["close"], 1)

    df["20DMA"] = df["close"].rolling(cfg.ma_short, min_periods=1).mean()
    df["50DMA"] = df["close"].rolling(cfg.ma_mid, min_periods=1).mean()
    df["200DMA"] = df["close"].rolling(cfg.ma_long, min_periods=1).mean()

    df["20DMA_valid"] = df["close"].rolling(cfg.ma_short).count() >= cfg.ma_short
    df["50DMA_valid"] = df["close"].rolling(cfg.ma_mid).count() >= cfg.ma_mid
    df["200DMA_valid"] = df["close"].rolling(cfg.ma_long).count() >= cfg.ma_long

    df["volume_20d_avg"] = df["volume"].rolling(
        cfg.volume_avg_window,
        min_periods=1,
    ).mean()
    df["volume_ratio"] = _safe_ratio(df["volume"], df["volume_20d_avg"])

    df["5D_return"] = _safe_pct_change(df["close"], cfg.return_short_window)
    df["20D_return"] = _safe_pct_change(df["close"], cfg.return_mid_window)

    rolling_20d_high = df["high"].rolling(cfg.high_low_window, min_periods=1).max()
    rolling_20d_low = df["low"].rolling(cfg.high_low_window, min_periods=1).min()

    # Interpretation:
    # - 20D_high_proximity = close / 20D high - 1, percent.
    #   0 means exactly at the 20D high, negative means below high.
    # - 20D_low_proximity = close / 20D low - 1, percent.
    #   0 means exactly at the 20D low, positive means above low.
    df["20D_high_proximity"] = (_safe_ratio(df["close"], rolling_20d_high) - 1.0) * 100.0
    df["20D_low_proximity"] = (_safe_ratio(df["close"], rolling_20d_low) - 1.0) * 100.0

    df["close_above_20dma"] = df["close"] > df["20DMA"]
    df["close_above_50dma"] = df["close"] > df["50DMA"]
    df["close_above_200dma"] = df["close"] > df["200DMA"]

    return df


def _to_python_scalar(value: Any) -> Any:
    """
    Convert numpy/pandas values into JSON-friendly Python scalars.
    """
    if pd.isna(value):
        return None

    if isinstance(value, (np.bool_, bool)):
        return bool(value)

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, (np.floating, float)):
        return float(value)

    return value


def latest_indicator_snapshot(
    price_df: pd.DataFrame,
    ticker: str | None = None,
    config: IndicatorConfig | None = None,
) -> dict[str, Any]:
    """
    Return latest row indicator snapshot as a JSON-friendly dict.

    Downstream scoring note:
    - If 20DMA_valid is False, ignore 20DMA-based score/rule.
    - If 50DMA_valid is False, ignore 50DMA-based score/rule.
    - If 200DMA_valid is False, ignore 200DMA-based score/rule.
    - This is especially important when lookback_period is too short or
      a ticker has fewer than 200 valid close observations.
    """
    df = add_indicator_columns(price_df, config=config)

    if df.empty:
        raise ValueError(f"No price data available for ticker={ticker or 'UNKNOWN'}")

    latest = df.dropna(subset=["close"]).tail(1)

    if latest.empty:
        raise ValueError(f"No valid close data available for ticker={ticker or 'UNKNOWN'}")

    row = latest.iloc[0]
    date_value = latest.index[0]

    result: dict[str, Any] = {
        "ticker": ticker,
        "date": str(pd.Timestamp(date_value).date()),
        "close": _to_python_scalar(row.get("close")),
        "change_pct": _to_python_scalar(row.get("change_pct")),
        "20DMA": _to_python_scalar(row.get("20DMA")),
        "50DMA": _to_python_scalar(row.get("50DMA")),
        "200DMA": _to_python_scalar(row.get("200DMA")),
        "20DMA_valid": _to_python_scalar(row.get("20DMA_valid")),
        "50DMA_valid": _to_python_scalar(row.get("50DMA_valid")),
        "200DMA_valid": _to_python_scalar(row.get("200DMA_valid")),
        "volume": _to_python_scalar(row.get("volume")),
        "volume_20d_avg": _to_python_scalar(row.get("volume_20d_avg")),
        "volume_ratio": _to_python_scalar(row.get("volume_ratio")),
        "5D_return": _to_python_scalar(row.get("5D_return")),
        "20D_return": _to_python_scalar(row.get("20D_return")),
        "20D_high_proximity": _to_python_scalar(row.get("20D_high_proximity")),
        "20D_low_proximity": _to_python_scalar(row.get("20D_low_proximity")),
        "close_above_20dma": _to_python_scalar(row.get("close_above_20dma")),
        "close_above_50dma": _to_python_scalar(row.get("close_above_50dma")),
        "close_above_200dma": _to_python_scalar(row.get("close_above_200dma")),
    }

    return result


def _coerce_to_dataframe(value: Any, ticker: str) -> pd.DataFrame:
    """
    Accept either a pd.DataFrame or a list[dict] of OHLCV records.

    fetch_prices.py returns dict[str, list[dict]] (records format).
    indicators.py internally needs pd.DataFrame.
    This adapter bridges the two formats.
    """
    if isinstance(value, pd.DataFrame):
        return value

    if isinstance(value, list) and value:
        try:
            df = pd.DataFrame(value)
            for date_col in ("date", "Date", "datetime", "Datetime", "timestamp"):
                if date_col in df.columns:
                    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
                    df = df.set_index(date_col).sort_index()
                    break
            return df
        except Exception as exc:
            raise ValueError(
                f"Cannot convert list[dict] to DataFrame for {ticker}: {exc}"
            ) from exc

    if isinstance(value, list) and not value:
        raise ValueError(f"Empty price list for {ticker}")

    raise ValueError(
        f"Unsupported price data type for {ticker}: {type(value).__name__}"
    )


def calculate_indicators_for_tickers(
    price_data: dict[str, Any],
    config: IndicatorConfig | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """
    Calculate latest indicator snapshot for multiple tickers.

    Accepts both dict[str, pd.DataFrame] and dict[str, list[dict]] —
    the latter is what fetch_prices.py returns.

    Returns:
        indicators_by_ticker, data_quality_notes
    """
    indicators_by_ticker: dict[str, dict[str, Any]] = {}
    data_quality_notes: list[str] = []

    for ticker, raw_value in price_data.items():
        try:
            df = _coerce_to_dataframe(raw_value, ticker)
            indicators_by_ticker[ticker] = latest_indicator_snapshot(
                df,
                ticker=ticker,
                config=config,
            )
        except Exception as exc:
            data_quality_notes.append(
                f"{ticker}: indicator calculation failed - {type(exc).__name__}: {exc}"
            )

    return indicators_by_ticker, data_quality_notes


def build_snapshots(
    price_data: dict[str, pd.DataFrame] | dict[str, Any],
    config: IndicatorConfig | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Backward-compatible wrapper for older main.py scaffolding.

    Accepts either:
    1. raw price data:
        {"NVDA": DataFrame, "QQQ": DataFrame}

    2. fetch_prices result:
        {
            "prices": {"NVDA": DataFrame, ...},
            "data_quality_notes": [...]
        }

    Returns:
        {
            "NVDA": {latest indicator snapshot},
            "QQQ": {latest indicator snapshot}
        }

    Notes:
    - Data quality notes are discarded in this wrapper.
    - Use build_indicator_data() if caller needs notes.
    """
    if not price_data:
        return {}

    if "prices" in price_data and isinstance(price_data.get("prices"), dict):
        prices = price_data["prices"]
    else:
        prices = price_data

    snapshots, _notes = calculate_indicators_for_tickers(
        prices,
        config=config,
    )

    return snapshots


def build_indicator_data(
    price_data: dict[str, pd.DataFrame] | dict[str, Any],
    config: IndicatorConfig | None = None,
) -> dict[str, Any]:
    """
    Backward-compatible wrapper for older main.py scaffolding.

    Accepts either:
    1. raw price data:
        {"NVDA": DataFrame, "QQQ": DataFrame}

    2. fetch_prices result:
        {
            "prices": {"NVDA": DataFrame, ...},
            "data_quality_notes": [...]
        }

    Returns:
        {
            "indicators": dict[str, dict],
            "snapshots": dict[str, dict],
            "data_quality_notes": list[str]
        }

    Downstream scoring note:
    - If 20DMA_valid is False, ignore 20DMA-based score/rule.
    - If 50DMA_valid is False, ignore 50DMA-based score/rule.
    - If 200DMA_valid is False, ignore 200DMA-based score/rule.
    """
    existing_notes: list[str] = []

    if not price_data:
        return {
            "indicators": {},
            "snapshots": {},
            "data_quality_notes": ["No price data provided to build_indicator_data()."],
        }

    if "prices" in price_data and isinstance(price_data.get("prices"), dict):
        prices = price_data["prices"]

        incoming_notes = price_data.get("data_quality_notes", [])
        if isinstance(incoming_notes, list):
            existing_notes.extend(str(note) for note in incoming_notes)
    else:
        prices = price_data

    snapshots, indicator_notes = calculate_indicators_for_tickers(
        prices,
        config=config,
    )

    all_notes = existing_notes + indicator_notes

    return {
        "indicators": snapshots,
        "snapshots": snapshots,
        "data_quality_notes": all_notes,
    }