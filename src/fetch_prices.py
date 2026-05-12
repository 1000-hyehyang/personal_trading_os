"""
src/fetch_prices.py

Price data fetching module for Personal Trading OS MVP.

Responsibilities:
- Load all tickers from config/watchlist.yaml
- Support nested watchlist.yaml sections
- Load lookback_period and interval from config/settings.yaml
- Fetch OHLCV data using yfinance
- Handle special Yahoo tickers such as ^VIX and ^TNX
- Avoid killing the whole program when one ticker fails
- Save/read cache/prices_cache.json
- Return a main.py-friendly standard price payload

Standard return shape:
    {
        "AAPL": [
            {
                "date": "2026-05-12",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "adj_close": 100.5,
                "volume": 12345678,
            }
        ]
    }

Python: 3.12
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
import yfinance as yf


DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOOKBACK_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"
CACHE_STALE_HOURS = 36

WATCHLIST_PATH = Path("config") / "watchlist.yaml"
SETTINGS_PATH = Path("config") / "settings.yaml"
PRICES_CACHE_PATH = Path("cache") / "prices_cache.json"


# ============================================================
# Time / JSON helpers
# ============================================================

def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _json_safe_number(value: Any) -> float | int | None:
    try:
        if value is None or pd.isna(value):
            return None

        number = float(value)

        if number.is_integer():
            return int(number)

        return number
    except Exception:
        return None


# ============================================================
# Config loading
# ============================================================

def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}

    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")

    return data


def _coerce_ticker_value(value: Any) -> str | None:
    """
    Convert YAML watchlist item into ticker string.

    YAML treats TRUE/FALSE as booleans when unquoted.
    Those are config mistakes, not ticker strings.
    If the user wants a ticker-like string, it should be quoted:
        - "TRUE"
    """
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    ticker = str(value).strip().upper()
    if not ticker:
        return None

    return ticker


def _collect_tickers_recursive(value: Any) -> list[str]:
    """
    Recursively collect tickers from nested YAML sections.

    Supports:
        watchlist:
          mega_cap_tech:
            - MSFT
            - AAPL
          semiconductors:
            - NVDA

        sectors:
          broad_technology:
            - XLK
    """
    tickers: list[str] = []

    if value is None:
        return tickers

    if isinstance(value, str):
        ticker = _coerce_ticker_value(value)
        if ticker:
            tickers.append(ticker)
        return tickers

    if isinstance(value, list):
        for item in value:
            tickers.extend(_collect_tickers_recursive(item))
        return tickers

    if isinstance(value, dict):
        for nested_value in value.values():
            tickers.extend(_collect_tickers_recursive(nested_value))
        return tickers

    return tickers


def load_watchlist_tickers(project_root: Path | str | None = None) -> list[str]:
    """
    Load every data ticker from config/watchlist.yaml.

    This intentionally collects only known ticker sections to avoid accidentally
    treating metadata values such as "semiconductor" or "high_beta" as tickers.
    """
    root = Path(project_root) if project_root else DEFAULT_PROJECT_ROOT
    path = root / WATCHLIST_PATH
    config = _load_yaml(path)

    ticker_sections = [
        "market_core",
        "volatility",
        "rates_credit",
        "sectors",
        "watchlist",
    ]

    tickers: list[str] = []

    for section in ticker_sections:
        tickers.extend(_collect_tickers_recursive(config.get(section, [])))

    required = [
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "SMH",
        "XLK",
        "TLT",
        "HYG",
        "UUP",
        "^VIX",
        "^TNX",
    ]
    tickers.extend(required)

    seen: set[str] = set()
    unique_tickers: list[str] = []

    for ticker in tickers:
        if ticker not in seen:
            unique_tickers.append(ticker)
            seen.add(ticker)

    return unique_tickers


def load_price_settings(project_root: Path | str | None = None) -> dict[str, str]:
    """
    Load price settings from config/settings.yaml.
    """
    root = Path(project_root) if project_root else DEFAULT_PROJECT_ROOT
    path = root / SETTINGS_PATH
    config = _load_yaml(path)

    data_settings = config.get("data", {})
    if not isinstance(data_settings, dict):
        data_settings = {}

    provider = str(data_settings.get("provider", "yfinance")).strip() or "yfinance"
    lookback_period = (
        str(data_settings.get("lookback_period", DEFAULT_LOOKBACK_PERIOD)).strip()
        or DEFAULT_LOOKBACK_PERIOD
    )
    interval = (
        str(data_settings.get("interval", DEFAULT_INTERVAL)).strip()
        or DEFAULT_INTERVAL
    )

    return {
        "provider": provider,
        "lookback_period": lookback_period,
        "interval": interval,
    }


def resolve_price_settings(
    project_root: Path | str | None = None,
    settings: dict[str, Any] | None = None,
    lookback_period: str | None = None,
    interval: str | None = None,
) -> dict[str, str]:
    """
    Resolve price settings from:
    1. explicit function arguments
    2. settings dict passed by main.py
    3. config/settings.yaml
    """
    file_settings = load_price_settings(project_root)

    if settings is None:
        resolved = dict(file_settings)
    else:
        data_settings = settings.get("data", settings)
        if not isinstance(data_settings, dict):
            data_settings = {}

        resolved = {
            "provider": str(data_settings.get("provider", file_settings["provider"])).strip()
            or file_settings["provider"],
            "lookback_period": str(
                data_settings.get("lookback_period", file_settings["lookback_period"])
            ).strip()
            or file_settings["lookback_period"],
            "interval": str(data_settings.get("interval", file_settings["interval"])).strip()
            or file_settings["interval"],
        }

    if lookback_period:
        resolved["lookback_period"] = str(lookback_period).strip()

    if interval:
        resolved["interval"] = str(interval).strip()

    return resolved


# ============================================================
# DataFrame normalization
# ============================================================

def _flatten_yfinance_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize possible yfinance MultiIndex columns.

    yfinance 0.2.x may return a 2-level MultiIndex even for a single ticker:
        ('Close', 'AAPL')
        ('Volume', 'AAPL')

    In that case, the correct OHLCV column name is level 0:
        Close
        Volume
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


def _normalize_price_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize yfinance output to a clean OHLCV DataFrame.
    """
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    df = raw_df.copy()
    df = _flatten_yfinance_columns(df)

    rename_map: dict[Any, str] = {}
    for col in df.columns:
        normalized = str(col).strip().lower().replace(" ", "_")
        rename_map[col] = normalized

    df = df.rename(columns=rename_map)

    if "close" not in df.columns and "adj_close" in df.columns:
        df["close"] = df["adj_close"]

    if "volume" not in df.columns:
        df["volume"] = 0

    for col in ["open", "high", "low"]:
        if col not in df.columns and "close" in df.columns:
            df[col] = df["close"]

    final_cols = [
        col
        for col in ["open", "high", "low", "close", "adj_close", "volume"]
        if col in df.columns
    ]

    if "close" not in final_cols:
        return pd.DataFrame()

    df = df[final_cols].copy()
    df = df.dropna(subset=["close"])

    if df.empty:
        return pd.DataFrame()

    df.index = pd.to_datetime(df.index, errors="coerce")
    df = df[~df.index.isna()]
    df = df.sort_index()

    for col in final_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["close"])

    return df


def _dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Convert a normalized OHLCV DataFrame to main.py-friendly records.
    """
    if df is None or df.empty:
        return []

    records: list[dict[str, Any]] = []

    for idx, row in df.iterrows():
        record = {
            "date": pd.Timestamp(idx).date().isoformat(),
            "open": _json_safe_number(row.get("open")),
            "high": _json_safe_number(row.get("high")),
            "low": _json_safe_number(row.get("low")),
            "close": _json_safe_number(row.get("close")),
            "adj_close": _json_safe_number(row.get("adj_close")),
            "volume": _json_safe_number(row.get("volume")),
        }

        if record["close"] is not None:
            records.append(record)

    return records


def _records_to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    """
    Convert cached records back to a normalized DataFrame.
    """
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    if "date" not in df.columns:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date").sort_index()

    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return _normalize_price_df(df)


def _records_payload_to_dataframes(
    prices: dict[str, list[dict[str, Any]]]
) -> dict[str, pd.DataFrame]:
    dataframes: dict[str, pd.DataFrame] = {}

    for ticker, records in prices.items():
        if not isinstance(records, list):
            continue

        df = _records_to_dataframe(records)
        if not df.empty:
            dataframes[ticker] = df

    return dataframes


# ============================================================
# Cache
# ============================================================

def _build_cache_staleness_note(generated_at_utc: Any) -> str | None:
    generated_at = _parse_utc_datetime(generated_at_utc)
    if generated_at is None:
        return "prices_cache.json generated_at_utc is missing or invalid. Data may be stale."

    now = datetime.now(timezone.utc)
    age_hours = int((now - generated_at).total_seconds() // 3600)

    if age_hours > CACHE_STALE_HOURS:
        return f"prices_cache.json is {age_hours} hours old. Data may be stale."

    return None


def load_prices_cache(
    project_root: Path | str | None = None,
    cache_path: Path | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """
    Load cache/prices_cache.json.

    Returns:
        prices_records, data_quality_notes
    """
    root = Path(project_root) if project_root else DEFAULT_PROJECT_ROOT
    path = cache_path or (root / PRICES_CACHE_PATH)

    data_quality_notes: list[str] = []

    if not path.exists():
        return {}, data_quality_notes

    try:
        with path.open("r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    except Exception as exc:
        return {}, [
            f"prices_cache.json could not be loaded. "
            f"Reason: {type(exc).__name__}: {exc}"
        ]

    if not isinstance(payload, dict):
        return {}, ["prices_cache.json root is not a JSON object. Cache ignored."]

    stale_note = _build_cache_staleness_note(payload.get("generated_at_utc"))
    if stale_note:
        data_quality_notes.append(stale_note)

    tickers_payload = payload.get("tickers", {})
    if not isinstance(tickers_payload, dict):
        data_quality_notes.append("prices_cache.json tickers field is invalid. Cache ignored.")
        return {}, data_quality_notes

    cached: dict[str, list[dict[str, Any]]] = {}

    for ticker, ticker_payload in tickers_payload.items():
        if not isinstance(ticker_payload, dict):
            data_quality_notes.append(f"{ticker}: invalid cache entry ignored.")
            continue

        records = ticker_payload.get("records", [])
        if not isinstance(records, list):
            data_quality_notes.append(f"{ticker}: invalid cache records ignored.")
            continue

        clean_records: list[dict[str, Any]] = []

        for item in records:
            if not isinstance(item, dict):
                continue

            if item.get("close") is None:
                continue

            clean_records.append(
                {
                    "date": str(item.get("date", "")),
                    "open": _json_safe_number(item.get("open")),
                    "high": _json_safe_number(item.get("high")),
                    "low": _json_safe_number(item.get("low")),
                    "close": _json_safe_number(item.get("close")),
                    "adj_close": _json_safe_number(item.get("adj_close")),
                    "volume": _json_safe_number(item.get("volume")),
                }
            )

        if clean_records:
            cached[str(ticker).upper()] = clean_records

    return cached, data_quality_notes


def save_prices_cache(
    price_records: dict[str, list[dict[str, Any]]] | dict[str, pd.DataFrame],
    project_root: Path | str | None = None,
    cache_path: Path | None = None,
    settings: dict[str, str] | None = None,
) -> None:
    """
    Save fetched price data to cache/prices_cache.json.
    """
    root = Path(project_root) if project_root else DEFAULT_PROJECT_ROOT
    path = cache_path or (root / PRICES_CACHE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "generated_at_utc": _now_utc_iso(),
        "settings": settings or {},
        "tickers": {},
    }

    for ticker, value in price_records.items():
        records: list[dict[str, Any]]

        if isinstance(value, pd.DataFrame):
            records = _dataframe_to_records(value)
        elif isinstance(value, list):
            records = [item for item in value if isinstance(item, dict)]
        else:
            continue

        if not records:
            continue

        first_date = records[0].get("date")
        last_date = records[-1].get("date")

        payload["tickers"][str(ticker).upper()] = {
            "rows": int(len(records)),
            "first_date": first_date,
            "last_date": last_date,
            "records": records,
        }

    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ============================================================
# Fetching
# ============================================================

def fetch_single_ticker_price_history(
    ticker: str,
    lookback_period: str,
    interval: str,
) -> pd.DataFrame:
    """
    Fetch one ticker using yfinance.

    Per-ticker fetching is slower than batch download, but it gives cleaner
    error handling and lets one failed ticker avoid killing the whole run.
    """
    raw = yf.download(
        tickers=ticker,
        period=lookback_period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    return _normalize_price_df(raw)


def _resolve_requested_tickers(
    tickers: list[str] | None = None,
    symbols: list[str] | None = None,
    config: dict[str, Any] | None = None,
    project_root: Path | str | None = None,
) -> list[str]:
    raw_tickers: list[Any] = []

    if tickers:
        raw_tickers.extend(tickers)
    elif symbols:
        raw_tickers.extend(symbols)
    elif isinstance(config, dict) and config.get("all_tickers"):
        raw_tickers.extend(config.get("all_tickers") or [])
    else:
        raw_tickers.extend(load_watchlist_tickers(project_root))

    seen: set[str] = set()
    result: list[str] = []

    for item in raw_tickers:
        ticker = _coerce_ticker_value(item)
        if not ticker:
            continue

        if ticker not in seen:
            seen.add(ticker)
            result.append(ticker)

    return result


def fetch_prices(
    tickers: list[str] | None = None,
    symbols: list[str] | None = None,
    project_root: Path | str | None = None,
    config: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    cache_dir: Path | str | None = None,
    lookback_period: str | None = None,
    interval: str | None = None,
    use_cache: bool = True,
    save_cache: bool = True,
    env: dict[str, Any] | None = None,
    return_legacy_tuple: bool = False,
) -> dict[str, list[dict[str, Any]]] | tuple[dict[str, pd.DataFrame], list[str]]:
    """
    Fetch price data.

    Default return:
        dict[str, list[dict]]

    This default is intentionally compatible with src/main.py's
    normalize_price_payload() and fallback_calculate_indicators().

    Legacy return is still available only when explicitly requested:
        fetch_prices(..., return_legacy_tuple=True)
    """
    del env  # accepted for compatibility; intentionally unused

    root = Path(project_root) if project_root else DEFAULT_PROJECT_ROOT

    resolved_settings = resolve_price_settings(
        project_root=root,
        settings=settings,
        lookback_period=lookback_period,
        interval=interval,
    )

    provider = resolved_settings["provider"]
    period = resolved_settings["lookback_period"]
    yf_interval = resolved_settings["interval"]

    data_quality_notes: list[str] = []

    if provider.lower() != "yfinance":
        data_quality_notes.append(
            f"Unsupported provider={provider}. Falling back to yfinance for MVP."
        )

    requested_tickers = _resolve_requested_tickers(
        tickers=tickers,
        symbols=symbols,
        config=config,
        project_root=root,
    )

    if cache_dir is not None:
        cache_path = Path(cache_dir) / "prices_cache.json"
    else:
        cache_path = root / PRICES_CACHE_PATH

    if not requested_tickers:
        data_quality_notes.append("No tickers found for price fetching.")

        if return_legacy_tuple:
            return {}, data_quality_notes

        return {}

    cached_records: dict[str, list[dict[str, Any]]] = {}
    cached_dataframes: dict[str, pd.DataFrame] = {}

    if use_cache:
        cached_records, cache_notes = load_prices_cache(root, cache_path=cache_path)
        data_quality_notes.extend(cache_notes)
        cached_dataframes = _records_payload_to_dataframes(cached_records)

    prices_records: dict[str, list[dict[str, Any]]] = {}
    prices_dataframes: dict[str, pd.DataFrame] = {}

    tickers_download_failed: list[str] = []
    tickers_no_data: list[str] = []

    for ticker in requested_tickers:
        try:
            df = fetch_single_ticker_price_history(
                ticker=ticker,
                lookback_period=period,
                interval=yf_interval,
            )

            if df.empty:
                raise ValueError("yfinance returned empty price data")

            records = _dataframe_to_records(df)

            if not records:
                raise ValueError("normalized price records are empty")

            prices_records[ticker] = records
            prices_dataframes[ticker] = df

        except Exception as exc:
            tickers_download_failed.append(ticker)

            if use_cache and ticker in cached_records and cached_records[ticker]:
                prices_records[ticker] = cached_records[ticker]

                cached_df = cached_dataframes.get(ticker)
                if cached_df is not None and not cached_df.empty:
                    prices_dataframes[ticker] = cached_df

                data_quality_notes.append(
                    f"{ticker}: download failed, using cached data. "
                    f"Reason: {type(exc).__name__}: {exc}"
                )
            else:
                tickers_no_data.append(ticker)
                data_quality_notes.append(
                    f"{ticker}: download failed and no usable cache found. "
                    f"Reason: {type(exc).__name__}: {exc}"
                )

    if save_cache and prices_records:
        try:
            save_prices_cache(
                price_records=prices_records,
                project_root=root,
                cache_path=cache_path,
                settings=resolved_settings,
            )
        except Exception as exc:
            data_quality_notes.append(
                f"prices_cache.json save failed - {type(exc).__name__}: {exc}"
            )

    if data_quality_notes:
        for note in data_quality_notes:
            logging.warning(note)

    if return_legacy_tuple:
        return prices_dataframes, data_quality_notes

    return prices_records


# ============================================================
# Compatibility aliases for main.py
# ============================================================

def fetch_price_data(
    tickers: list[str] | None = None,
    symbols: list[str] | None = None,
    project_root: Path | str | None = None,
    config: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    cache_dir: Path | str | None = None,
    lookback_period: str | None = None,
    interval: str | None = None,
    use_cache: bool = True,
    save_cache: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    return fetch_prices(
        tickers=tickers,
        symbols=symbols,
        project_root=project_root,
        config=config,
        settings=settings,
        cache_dir=cache_dir,
        lookback_period=lookback_period,
        interval=interval,
        use_cache=use_cache,
        save_cache=save_cache,
    )


def collect_prices(*args: Any, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
    return fetch_prices(*args, **kwargs)


def download_prices(*args: Any, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
    return fetch_prices(*args, **kwargs)


def get_price_data(*args: Any, **kwargs: Any) -> dict[str, list[dict[str, Any]]]:
    return fetch_prices(*args, **kwargs)


def fetch_prices_from_config(
    project_root: Path | str | None = None,
) -> dict[str, Any]:
    """
    Convenience wrapper for manual smoke tests.

    Returns a rich payload for humans/tests, while fetch_prices() itself returns
    main.py-friendly price records by default.
    """
    root = Path(project_root) if project_root else DEFAULT_PROJECT_ROOT
    requested = load_watchlist_tickers(root)
    settings = load_price_settings(root)

    prices = fetch_prices(
        tickers=requested,
        project_root=root,
        settings=settings,
        use_cache=True,
        save_cache=True,
    )

    return {
        "prices": prices,
        "settings": settings,
        "tickers_requested": requested,
        "tickers_loaded": sorted(prices.keys()),
        "tickers_download_failed": [
            ticker for ticker in requested if ticker not in prices
        ],
        "tickers_no_data": [
            ticker for ticker in requested if ticker not in prices
        ],
        "tickers_failed": [
            ticker for ticker in requested if ticker not in prices
        ],
        "data_quality_notes": [],
    }


def main() -> None:
    """
    Manual smoke test:

    PowerShell:
      .\\.venv\\Scripts\\python.exe src\\fetch_prices.py
    """
    result = fetch_prices_from_config()

    print("Price fetch complete")
    print(f"Requested: {len(result['tickers_requested'])}")
    print(f"Loaded: {len(result['tickers_loaded'])}")
    print(f"Download failed: {len(result['tickers_download_failed'])}")
    print(f"No data: {len(result['tickers_no_data'])}")

    prices = result["prices"]
    print("\nLatest Price Sample:")
    for ticker, records in list(prices.items())[:5]:
        if not records:
            continue

        latest = records[-1]
        print(
            f"- {ticker}: "
            f"date={latest.get('date')}, "
            f"close={latest.get('close')}, "
            f"volume={latest.get('volume')}"
        )


if __name__ == "__main__":
    main()