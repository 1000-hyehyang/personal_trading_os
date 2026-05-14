"""
Market regime scoring module for Personal Trading OS MVP.

Input:
- indicators produced by indicators.py as either:
  1) dict keyed by ticker
  2) pandas DataFrame with ticker column or ticker index
- events_merged.json data as dict/list or file path

Output:
{
    "mode": "Mild Risk-On",
    "score": 3,
    "positive_reasons": [],
    "negative_reasons": [],
    "event_overlay": "Caution" 또는 None,
    "data_quality_notes": []
}
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None  # type: ignore


MARKET_TICKERS = [
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

DEFENSIVE_SECTOR_TICKERS = ["XLP", "XLU", "XLV"]


def load_events_merged(path: str | Path) -> dict[str, Any]:
    """
    Load events_merged.json.

    Returns an empty dict if the file is missing or invalid.
    This prevents the market regime module from failing the whole run.
    """
    event_path = Path(path)

    if not event_path.exists():
        return {
            "_data_quality_notes": [
                f"events_merged.json not found: {event_path}"
            ]
        }

    try:
        with event_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

        if isinstance(data, list):
            return {"events_today": data}

        return {
            "_data_quality_notes": [
                f"events_merged.json has unsupported root type: {type(data).__name__}"
            ]
        }

    except Exception as exc:
        return {
            "_data_quality_notes": [
                f"Failed to load events_merged.json: {event_path} ({exc})"
            ]
        }


def determine_market_regime(
    indicators: Any,
    events: Optional[Any] = None,
    *,
    events_path: Optional[str | Path] = None,
    as_of_date: Optional[str | date | datetime] = None,
) -> dict[str, Any]:
    """
    Main public function.

    Parameters
    ----------
    indicators:
        Ticker indicator dictionary or pandas DataFrame.

    events:
        Parsed events_merged.json object.
        Can be dict or list.

    events_path:
        Optional path to output/events_merged.json.
        Used only if events is None.

    as_of_date:
        Optional date used for event matching.
        If omitted, this module tries to infer it from events["date"],
        otherwise uses local current date.

    Returns
    -------
    dict:
        Market regime result.
    """
    data_quality_notes: list[str] = []

    normalized = _normalize_indicators(indicators, data_quality_notes)

    if events is None and events_path is not None:
        events = load_events_merged(events_path)

    events = _normalize_events(events, data_quality_notes)

    if isinstance(events, dict):
        data_quality_notes.extend(events.get("_data_quality_notes", []))

    current_date = _resolve_as_of_date(as_of_date, events)

    score = 0
    positive_reasons: list[str] = []
    negative_reasons: list[str] = []

    def add_positive(reason: str) -> None:
        nonlocal score
        score += 1
        positive_reasons.append(reason)

    def add_negative(reason: str) -> None:
        nonlocal score
        score -= 1
        negative_reasons.append(reason)

    # +1: SPY above 20DMA
    if _has_ticker(normalized, "SPY", data_quality_notes):
        if _close_above_ma(normalized, "SPY", 20, data_quality_notes):
            add_positive("SPY가 20일선 위")
    # +1: QQQ above 20DMA
    if _has_ticker(normalized, "QQQ", data_quality_notes):
        if _close_above_ma(normalized, "QQQ", 20, data_quality_notes):
            add_positive("QQQ가 20일선 위")

    # +1 / -1: SPY above/below 50DMA
    if _has_ticker(normalized, "SPY", data_quality_notes):
        above_50 = _close_above_ma(normalized, "SPY", 50, data_quality_notes)
        if above_50 is True:
            add_positive("SPY가 50일선 위")
        elif above_50 is False:
            add_negative("SPY가 50일선 아래")

    # +1 / -1: QQQ above/below 50DMA
    if _has_ticker(normalized, "QQQ", data_quality_notes):
        above_50 = _close_above_ma(normalized, "QQQ", 50, data_quality_notes)
        if above_50 is True:
            add_positive("QQQ가 50일선 위")
        elif above_50 is False:
            add_negative("QQQ가 50일선 아래")

    # +1: QQQ 5D RS > SPY
    qqq_vs_spy = _relative_strength(normalized, "QQQ", "SPY", data_quality_notes)
    if qqq_vs_spy is True:
        add_positive("QQQ가 SPY보다 5일 상대강도 우위")

    # +1: SMH 5D RS > QQQ
    smh_vs_qqq = _relative_strength(normalized, "SMH", "QQQ", data_quality_notes)
    if smh_vs_qqq is True:
        add_positive("SMH가 QQQ보다 5일 상대강도 우위")

    # -1: IWM weaker than SPY
    iwm_vs_spy = _relative_strength(normalized, "IWM", "SPY", data_quality_notes)
    if iwm_vs_spy is False:
        add_negative("IWM이 SPY보다 5일 상대강도 약세")

    # +1 / -1: VIX down or spike
    vix_change_pct = _get_change_pct(normalized, "^VIX", data_quality_notes)
    if vix_change_pct is not None:
        if vix_change_pct < 0:
            add_positive("VIX가 전일 대비 하락")
        elif vix_change_pct >= 5:
            add_negative("VIX가 전일 대비 5% 이상 상승 — Defensive bias")

    # -1: VIX above 20DMA
    if _has_ticker(normalized, "^VIX", data_quality_notes):
        vix_above_20 = _close_above_ma(normalized, "^VIX", 20, data_quality_notes)
        if vix_above_20 is True:
            add_negative("VIX가 20일선 위")

    # +1: HYG above 20DMA
    if _has_ticker(normalized, "HYG", data_quality_notes):
        if _close_above_ma(normalized, "HYG", 20, data_quality_notes):
            add_positive("HYG가 20일선 위")

    # -1: TLT weak + QQQ weak
    tlt_weak = _is_weak(normalized, "TLT", data_quality_notes)
    qqq_weak = _is_weak(normalized, "QQQ", data_quality_notes)
    if tlt_weak is True and qqq_weak is True:
        add_negative("TLT 약세 + QQQ 약세")

    # -1: only defensive sectors strong
    defensive_only = _defensive_sectors_only_strong(normalized, data_quality_notes)
    if defensive_only is True:
        add_negative("방어 섹터만 강함")

    mode = _mode_from_score(score)

    event_overlay = _detect_event_overlay(events, current_date, data_quality_notes)
    if event_overlay == "Caution":
        negative_reasons.append("High-impact macro/FOMC event today — Caution overlay")

    return {
        "mode": mode,
        "score": score,
        "positive_reasons": positive_reasons,
        "negative_reasons": negative_reasons,
        "event_overlay": event_overlay,
        "data_quality_notes": _dedupe_preserve_order(data_quality_notes),
    }


# Backward-friendly alias names.
calculate_market_regime = determine_market_regime
get_market_regime = determine_market_regime


def _normalize_indicators(indicators: Any, notes: list[str]) -> dict[str, dict[str, Any]]:
    """
    Convert dict/DataFrame indicators into:
    {
        "SPY": {"close": 100, "dma_20": 95, ...},
        ...
    }
    """
    if indicators is None:
        notes.append("Indicators input is None.")
        return {}

    if isinstance(indicators, dict):
        return _normalize_dict_indicators(indicators, notes)

    if pd is not None and isinstance(indicators, pd.DataFrame):
        return _normalize_dataframe_indicators(indicators, notes)

    notes.append(f"Unsupported indicators input type: {type(indicators).__name__}")
    return {}


def _normalize_dict_indicators(
    indicators: dict[Any, Any],
    notes: list[str],
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}

    for raw_ticker, raw_row in indicators.items():
        ticker = str(raw_ticker).strip().upper()

        if raw_row is None:
            notes.append(f"{ticker}: indicator row is None.")
            continue

        if isinstance(raw_row, dict):
            normalized[ticker] = dict(raw_row)
            continue

        if hasattr(raw_row, "to_dict"):
            try:
                normalized[ticker] = raw_row.to_dict()
                continue
            except Exception:
                pass

        notes.append(f"{ticker}: unsupported indicator row type {type(raw_row).__name__}.")

    return normalized


def _normalize_dataframe_indicators(df: Any, notes: list[str]) -> dict[str, dict[str, Any]]:
    if df.empty:
        notes.append("Indicators DataFrame is empty.")
        return {}

    work = df.copy()

    ticker_col = _find_column(
        work,
        [
            "ticker",
            "Ticker",
            "symbol",
            "Symbol",
        ],
    )

    normalized: dict[str, dict[str, Any]] = {}

    if ticker_col:
        for _, row in work.iterrows():
            ticker = str(row.get(ticker_col, "")).strip().upper()
            if not ticker:
                notes.append("DataFrame row skipped because ticker is empty.")
                continue
            normalized[ticker] = row.to_dict()
    else:
        for idx, row in work.iterrows():
            ticker = str(idx).strip().upper()
            if not ticker:
                notes.append("DataFrame row skipped because index ticker is empty.")
                continue
            normalized[ticker] = row.to_dict()

    return normalized


def _normalize_events(events: Any, notes: list[str]) -> dict[str, Any]:
    if events is None:
        return {}

    if isinstance(events, dict):
        return events

    if isinstance(events, list):
        return {"events_today": events}

    notes.append(f"Unsupported events input type: {type(events).__name__}")
    return {}


def _resolve_as_of_date(
    as_of_date: Optional[str | date | datetime],
    events: dict[str, Any],
) -> date:
    if as_of_date is not None:
        parsed = _parse_date(as_of_date)
        if parsed is not None:
            return parsed

    event_date = events.get("date")
    parsed_event_date = _parse_date(event_date)
    if parsed_event_date is not None:
        return parsed_event_date

    return date.today()


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except Exception:
        return None


def _has_ticker(
    data: dict[str, dict[str, Any]],
    ticker: str,
    notes: list[str],
) -> bool:
    if ticker not in data:
        notes.append(f"{ticker}: missing indicator data.")
        return False
    return True


def _find_column(df: Any, candidates: list[str]) -> Optional[str]:
    columns = list(df.columns)
    lowered = {str(col).lower(): col for col in columns}

    for candidate in candidates:
        if candidate in columns:
            return candidate
        lowered_candidate = candidate.lower()
        if lowered_candidate in lowered:
            return lowered[lowered_candidate]

    return None


def _get_value(
    row: dict[str, Any],
    candidates: list[str],
) -> Optional[float]:
    lowered = {str(k).lower(): k for k in row.keys()}

    for key in candidates:
        actual_key = None

        if key in row:
            actual_key = key
        elif key.lower() in lowered:
            actual_key = lowered[key.lower()]

        if actual_key is None:
            continue

        raw_value = row.get(actual_key)

        if raw_value is None:
            continue

        try:
            # pandas/numpy NaN safe handling
            if pd is not None and pd.isna(raw_value):
                continue
        except Exception:
            pass

        try:
            return float(raw_value)
        except (TypeError, ValueError):
            continue

    return None


def _close_value(row: dict[str, Any]) -> Optional[float]:
    return _get_value(
        row,
        [
            "close",
            "Close",
            "last",
            "Last",
            "price",
            "Price",
            "adj_close",
            "Adj Close",
            "adjclose",
        ],
    )


def _ma_value(row: dict[str, Any], period: int) -> Optional[float]:
    return _get_value(
        row,
        [
            f"dma_{period}",
            f"DMA_{period}",
            f"{period}dma",
            f"{period}DMA",
            f"ma_{period}",
            f"MA_{period}",
            f"sma_{period}",
            f"SMA_{period}",
            f"{period}_dma",
            f"{period}_DMA",
            f"moving_average_{period}",
            f"close_{period}dma",
        ],
    )


def _return_5d_value(row: dict[str, Any]) -> Optional[float]:
    return _get_value(
        row,
        [
            "return_5d",
            "Return_5D",
            "ret_5d",
            "Ret_5D",
            "change_5d",
            "Change_5D",
            "change_5d_pct",
            "Change_5D_Pct",
            "pct_change_5d",
            "Pct_Change_5D",
            "five_day_return",
            "5d_return",
        ],
    )


def _get_change_pct(
    data: dict[str, dict[str, Any]],
    ticker: str,
    notes: list[str],
) -> Optional[float]:
    row = data.get(ticker)
    if row is None:
        notes.append(f"{ticker}: missing indicator data for daily change.")
        return None

    value = _get_value(
        row,
        [
            "change_pct",
            "Change %",
            "change_percent",
            "pct_change",
            "daily_change_pct",
            "1d_change_pct",
            "return_1d",
            "Return_1D",
        ],
    )

    if value is not None:
        return value

    close = _close_value(row)
    previous_close = _get_value(
        row,
        [
            "previous_close",
            "Previous Close",
            "prev_close",
            "Prev Close",
            "close_prev",
            "prior_close",
        ],
    )

    if close is None or previous_close is None or previous_close == 0:
        notes.append(f"{ticker}: daily change unavailable.")
        return None

    return ((close / previous_close) - 1.0) * 100.0


def _close_above_ma(
    data: dict[str, dict[str, Any]],
    ticker: str,
    period: int,
    notes: list[str],
) -> Optional[bool]:
    row = data.get(ticker)

    if row is None:
        notes.append(f"{ticker}: missing indicator data.")
        return None

    close = _close_value(row)
    ma = _ma_value(row, period)

    if close is None:
        notes.append(f"{ticker}: close unavailable.")
        return None

    if ma is None:
        notes.append(f"{ticker}: {period}DMA unavailable.")
        return None

    return close > ma


def _relative_strength(
    data: dict[str, dict[str, Any]],
    ticker: str,
    benchmark: str,
    notes: list[str],
) -> Optional[bool]:
    """
    Returns True if ticker 5D return > benchmark 5D return.
    Returns False if ticker 5D return <= benchmark 5D return.
    Returns None if missing.
    """
    if ticker not in data:
        notes.append(f"{ticker}: missing indicator data for relative strength.")
        return None

    if benchmark not in data:
        notes.append(f"{benchmark}: missing benchmark data for {ticker} relative strength.")
        return None

    ticker_row = data[ticker]
    benchmark_row = data[benchmark]

    # Prefer direct precomputed relative-strength fields if available.
    direct_value = _get_value(
        ticker_row,
        [
            f"rs_5d_vs_{benchmark}",
            f"RS_5D_vs_{benchmark}",
            f"relative_strength_5d_vs_{benchmark}",
            f"rel_strength_5d_vs_{benchmark}",
        ],
    )

    if direct_value is not None:
        return direct_value > 0

    ticker_ret = _return_5d_value(ticker_row)
    benchmark_ret = _return_5d_value(benchmark_row)

    if ticker_ret is None or benchmark_ret is None:
        notes.append(f"{ticker} vs {benchmark}: 5D return unavailable for relative strength.")
        return None

    return ticker_ret > benchmark_ret


def _is_weak(
    data: dict[str, dict[str, Any]],
    ticker: str,
    notes: list[str],
) -> Optional[bool]:
    """
    Weak means either:
    - close below 20DMA, or
    - 5D return is negative.
    """
    if ticker not in data:
        notes.append(f"{ticker}: missing indicator data for weakness check.")
        return None

    above_20 = _close_above_ma(data, ticker, 20, notes)
    if above_20 is False:
        return True

    ret_5d = _return_5d_value(data[ticker])
    if ret_5d is not None and ret_5d < 0:
        return True

    if above_20 is None and ret_5d is None:
        notes.append(f"{ticker}: weakness check unavailable.")

    return False


def _defensive_sectors_only_strong(
    data: dict[str, dict[str, Any]],
    notes: list[str],
) -> Optional[bool]:
    """
    Detect 'only defensive sectors strong'.

    This rule needs defensive sector ETFs such as XLP/XLU/XLV.
    The MVP market ticker list may not always include them, so this function
    records a data quality note instead of failing.
    """
    available_defensive = [ticker for ticker in DEFENSIVE_SECTOR_TICKERS if ticker in data]

    if not available_defensive:
        notes.append(
            "방어 섹터만 강함 rule skipped: XLP/XLU/XLV data unavailable."
        )
        return None

    defensive_strong = []
    for ticker in available_defensive:
        ret = _return_5d_value(data[ticker])
        above_20 = _close_above_ma(data, ticker, 20, notes)

        if ret is not None:
            defensive_strong.append(ret > 0)
        elif above_20 is not None:
            defensive_strong.append(above_20)

    if not defensive_strong or not any(defensive_strong):
        return False

    growth_tickers = ["QQQ", "SMH", "XLK"]
    growth_weak_values = []

    for ticker in growth_tickers:
        if ticker not in data:
            continue

        weak = _is_weak(data, ticker, notes)
        if weak is not None:
            growth_weak_values.append(weak)

    if not growth_weak_values:
        notes.append("방어 섹터 rule: growth sector comparison data unavailable.")
        return None

    return all(growth_weak_values)


def _mode_from_score(score: int) -> str:
    if score >= 5:
        return "Risk-On"
    if 2 <= score <= 4:
        return "Mild Risk-On"
    if -1 <= score <= 1:
        return "Neutral"
    if -4 <= score <= -2:
        return "Caution"
    return "Defensive"


def _detect_event_overlay(
    events: dict[str, Any],
    as_of_date: date,
    notes: list[str],
) -> Optional[str]:
    """
    Caution overlay if:
    - macro_high_today
    - fomc_today
    - fomc_minutes_today
    - high-impact macro/FOMC event in events_today on as_of_date
    """
    if not events:
        notes.append("Event overlay skipped: events data unavailable.")
        return None

    flags = _collect_event_flags(events)

    caution_flags = {
        "macro_high_today",
        "fomc_today",
        "fomc_minutes_today",
        "manual_event_high",
    }

    if any(flag in flags for flag in caution_flags):
        return "Caution"

    today_events = _collect_today_events(events)

    for event in today_events:
        if not isinstance(event, dict):
            continue

        event_date = _parse_date(event.get("date")) or as_of_date

        if event_date != as_of_date:
            continue

        impact = str(event.get("impact", "")).strip().lower()
        event_type = str(event.get("type", "")).strip().lower()
        risk_flag = str(event.get("risk_flag", "")).strip().lower()
        name = str(event.get("name", "")).strip().lower()

        is_high = impact == "high"
        is_macro = event_type in {"macro", "economic", "fomc"} or any(
            keyword in name
            for keyword in [
                "cpi",
                "ppi",
                "pce",
                "fomc",
                "minutes",
                "employment",
                "nonfarm",
                "payroll",
                "gdp",
            ]
        )
        is_today_flag = risk_flag in {
            "macro_high_today",
            "fomc_today",
            "fomc_minutes_today",
            "manual_event_high",
        }

        if is_today_flag or (is_high and is_macro):
            return "Caution"

    return None


def _collect_event_flags(events: dict[str, Any]) -> set[str]:
    flags: set[str] = set()

    possible_flag_containers = [
        events.get("event_flags"),
        events.get("risk_flags"),
        events.get("flags"),
    ]

    for container in possible_flag_containers:
        if isinstance(container, list):
            flags.update(str(item).strip().lower() for item in container)
        elif isinstance(container, dict):
            for key, value in container.items():
                if bool(value):
                    flags.add(str(key).strip().lower())

    for key, value in events.items():
        key_text = str(key).strip().lower()
        if key_text.endswith("_today") or key_text in {
            "macro_high_today",
            "fomc_today",
            "fomc_minutes_today",
            "manual_event_high",
        }:
            if bool(value):
                flags.add(key_text)

    for event in _collect_today_events(events):
        if isinstance(event, dict):
            risk_flag = str(event.get("risk_flag", "")).strip().lower()
            if risk_flag:
                flags.add(risk_flag)

    return flags


def _collect_today_events(events: dict[str, Any]) -> list[Any]:
    today_str = date.today().isoformat()
    collected: list[Any] = []

    for key in [
        "events_today",
        "today",
        "macro_events_today",
        "economic_events_today",
        "manual_events_today",
    ]:
        value = events.get(key)

        if isinstance(value, list):
            for item in value:
                # Defensive: skip items dated in the future even if they
                # somehow ended up in an *_today bucket.
                if isinstance(item, dict):
                    item_date = str(item.get("date") or "")[:10]
                    if item_date and item_date != today_str:
                        continue
                collected.append(item)

    # Some event calendar modules may use nested structures.
    event_risk = events.get("event_risk")
    if isinstance(event_risk, dict):
        for key in [
            "events_today",
            "today",
            "macro_events_today",
            "economic_events_today",
            "manual_events_today",
        ]:
            value = event_risk.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        item_date = str(item.get("date") or "")[:10]
                        if item_date and item_date != today_str:
                            continue
                    collected.append(item)

    return collected


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)

    return result