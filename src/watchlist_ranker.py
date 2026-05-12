"""
watchlist_ranker.py

Personal Trading OS MVP
- Watchlist A/B/C/D ranking module
- Inputs:
  1. indicator data from indicators.py
  2. market regime result from market_regime.py
  3. output/events_merged.json
  4. config/watchlist.yaml

This module does not make buy/sell decisions.
It only ranks watchlist tickers for observation priority.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml


RankedTicker = Dict[str, Any]
IndicatorMap = Dict[str, Dict[str, Any]]


DEFAULT_EARNINGS_RISK_WINDOW_DAYS = 7
DEFAULT_NEAR_20D_HIGH_PCT = 0.03
DEFAULT_NEAR_20D_LOW_PCT = 0.03


def load_watchlist_from_yaml(path: str | Path) -> List[str]:
    """
    Load watchlist tickers from config/watchlist.yaml.

    Supported formats:
    1) Dict format:
       watchlist:
         - NVDA
         - AMD

    2) Plain list format:
       - NVDA
       - AMD
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"watchlist.yaml not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if isinstance(data, dict):
        raw_watchlist = data.get("watchlist", [])
    elif isinstance(data, list):
        raw_watchlist = data
    else:
        raw_watchlist = []

    watchlist: List[str] = []
    for item in raw_watchlist:
        if item is None:
            continue
        ticker = str(item).strip().upper()
        if ticker:
            watchlist.append(ticker)

    return watchlist


def load_events_merged_json(path: str | Path) -> List[Dict[str, Any]]:
    """
    Load and flatten output/events_merged.json.

    The event file can be shaped in several ways depending on earlier modules.
    This function accepts common structures such as:

    {
      "events_today": [...],
      "events_next_24h": [...],
      "earnings_watchlist_7d": [...],
      "manual_events": [...]
    }

    or:

    {
      "events": [...]
    }

    or simply:

    [...]
    """
    path = Path(path)

    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return flatten_events(data)


def flatten_events(data: Any) -> List[Dict[str, Any]]:
    """
    Convert nested event payloads into a flat list of event dictionaries.
    """
    if data is None:
        return []

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if not isinstance(data, dict):
        return []

    candidate_keys = [
        "events",
        "all_events",
        "events_today",
        "events_next_24h",
        "events_this_week",
        "earnings",
        "earnings_watchlist_7d",
        "manual_events",
        "macro_events",
        "company_events",
    ]

    flattened: List[Dict[str, Any]] = []

    for key in candidate_keys:
        value = data.get(key)
        if isinstance(value, list):
            flattened.extend(x for x in value if isinstance(x, dict))
        elif isinstance(value, dict):
            flattened.extend(flatten_events(value))

    # Some modules may nest by date:
    # {"2026-05-12": [{...}, {...}]}
    for value in data.values():
        if isinstance(value, list):
            flattened.extend(x for x in value if isinstance(x, dict))

    # De-duplicate by stable JSON representation.
    seen = set()
    unique: List[Dict[str, Any]] = []
    for event in flattened:
        key = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            unique.append(event)

    return unique


def rank_from_files(
    indicators_by_ticker: IndicatorMap,
    market_regime: Optional[Dict[str, Any]],
    events_merged_path: str | Path,
    watchlist_yaml_path: str | Path,
    today: Optional[date | str] = None,
) -> List[RankedTicker]:
    """
    Convenience wrapper for main.py.

    Example:
        ranked = rank_from_files(
            indicators_by_ticker=indicators,
            market_regime=market_regime_result,
            events_merged_path="output/events_merged.json",
            watchlist_yaml_path="config/watchlist.yaml",
        )
    """
    watchlist = load_watchlist_from_yaml(watchlist_yaml_path)
    events = load_events_merged_json(events_merged_path)

    return rank_watchlist(
        indicators_by_ticker=indicators_by_ticker,
        market_regime=market_regime,
        events=events,
        watchlist=watchlist,
        today=today,
    )


def rank_watchlist(
    indicators_by_ticker: IndicatorMap,
    market_regime: Optional[Dict[str, Any]] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    watchlist: Optional[Iterable[str]] = None,
    today: Optional[date | str] = None,
    earnings_risk_window_days: int = DEFAULT_EARNINGS_RISK_WINDOW_DAYS,
    near_20d_high_pct: float = DEFAULT_NEAR_20D_HIGH_PCT,
    near_20d_low_pct: float = DEFAULT_NEAR_20D_LOW_PCT,
) -> List[RankedTicker]:
    """
    Rank watchlist tickers into A/B/C/D grades.

    Positive scoring:
    - Close above 20DMA: +2
    - Close above 50DMA: +2
    - Close above 200DMA: +1
    - 20DMA above 50DMA: +1
    - Volume >= 20-day average volume: +1
    - Near 20-day high: +1
    - 5-day relative strength vs SPY positive: +1
    - 5-day relative strength vs QQQ positive: +1
    - Related sector ETF strong: +1

    Negative scoring:
    - Close below 50DMA: -2
    - Close below 200DMA: -2
    - Volume decline with price decline: -1
    - Near 20-day low: -1
    - Earnings within 7 calendar days: -1
    - Earnings today or tomorrow: -2

    Data quality:
    - Missing critical indicator data prevents aggressive promotion.
    - If 50DMA or 200DMA judgment is missing, grade is capped at C.
    - If multiple core fields are missing, grade is capped at C.
    """
    today_date = _coerce_date(today) or date.today()
    events = events or []
    market_regime = market_regime or {}

    tickers = _resolve_tickers(indicators_by_ticker, watchlist)
    results: List[RankedTicker] = []

    for ticker in tickers:
        ticker = ticker.upper()
        raw_indicators = indicators_by_ticker.get(ticker, {}) or {}

        score = 0
        positive_reasons: List[str] = []
        negative_reasons: List[str] = []
        event_flags: List[str] = []
        data_quality_notes: List[str] = []

        close = _get_number(
            raw_indicators,
            [
                "close",
                "last_close",
                "Close",
                "latest_close",
                "price",
            ],
        )
        prev_close = _get_number(
            raw_indicators,
            [
                "prev_close",
                "previous_close",
                "close_prev",
            ],
        )
        dma20 = _get_number(
            raw_indicators,
            [
                "dma20",
                "20dma",
                "ma20",
                "sma20",
                "20DMA",
                "MA20",
                "SMA20",
                "moving_average_20",
                "twenty_dma",
            ],
        )
        dma50 = _get_number(
            raw_indicators,
            [
                "dma50",
                "50dma",
                "ma50",
                "sma50",
                "50DMA",
                "MA50",
                "SMA50",
                "moving_average_50",
                "fifty_dma",
            ],
        )
        dma200 = _get_number(
            raw_indicators,
            [
                "dma200",
                "200dma",
                "ma200",
                "sma200",
                "200DMA",
                "MA200",
                "SMA200",
                "moving_average_200",
                "two_hundred_dma",
            ],
        )

        above_20dma = _get_bool_or_compare(
            raw_indicators,
            bool_keys=[
                "above_20dma",
                "close_above_20dma",
                "is_above_20dma",
                "above_ma20",
                "close_above_ma20",
            ],
            close=close,
            average=dma20,
        )
        above_50dma = _get_bool_or_compare(
            raw_indicators,
            bool_keys=[
                "above_50dma",
                "close_above_50dma",
                "is_above_50dma",
                "above_ma50",
                "close_above_ma50",
            ],
            close=close,
            average=dma50,
        )
        above_200dma = _get_bool_or_compare(
            raw_indicators,
            bool_keys=[
                "above_200dma",
                "close_above_200dma",
                "is_above_200dma",
                "above_ma200",
                "close_above_ma200",
            ],
            close=close,
            average=dma200,
        )

        if above_20dma is True:
            score += 2
            positive_reasons.append("20일선 위")
        elif above_20dma is None:
            data_quality_notes.append("20DMA 판단 데이터 부족")

        if above_50dma is True:
            score += 2
            positive_reasons.append("50일선 위")
        elif above_50dma is False:
            score -= 2
            negative_reasons.append("50일선 아래")
        else:
            data_quality_notes.append("50DMA 판단 데이터 부족")

        if above_200dma is True:
            score += 1
            positive_reasons.append("200일선 위")
        elif above_200dma is False:
            score -= 2
            negative_reasons.append("200일선 아래")
        else:
            data_quality_notes.append("200DMA 판단 데이터 부족")

        if dma20 is not None and dma50 is not None:
            if dma20 > dma50:
                score += 1
                positive_reasons.append("20일선이 50일선 위")
        else:
            data_quality_notes.append("20일선/50일선 방향성 판단 데이터 부족")

        volume_above_avg = _is_volume_above_20d_avg(raw_indicators)
        if volume_above_avg is True:
            score += 1
            positive_reasons.append("거래량 20일 평균 이상")
        elif volume_above_avg is False:
            if close is not None and prev_close is not None:
                if close < prev_close:
                    score -= 1
                    negative_reasons.append("거래량 동반 하락")
            elif close is not None:
                data_quality_notes.append("거래량 동반 하락 판단을 위한 전일 종가 데이터 부족")
        else:
            data_quality_notes.append("거래량 20일 평균 판단 데이터 부족")

        near_20d_high = _is_near_20d_high(
            raw_indicators=raw_indicators,
            close=close,
            near_pct=near_20d_high_pct,
        )
        if near_20d_high is True:
            score += 1
            positive_reasons.append("20일 고점 근처")
        elif near_20d_high is None:
            data_quality_notes.append("20일 고점 근처 판단 데이터 부족")

        near_20d_low = _is_near_20d_low(
            raw_indicators=raw_indicators,
            close=close,
            near_pct=near_20d_low_pct,
        )
        if near_20d_low is True:
            score -= 1
            negative_reasons.append("20일 저점 근처")
        elif near_20d_low is None:
            data_quality_notes.append("20일 저점 근처 판단 데이터 부족")

        spy_positive, spy_missing = _is_relative_strength_positive(
            raw_indicators,
            bool_keys=[
                "rs_5d_vs_spy_positive",
                "relative_strength_5d_vs_spy_positive",
                "outperforming_spy_5d",
            ],
            value_keys=[
                "rs_5d_vs_spy",
                "relative_strength_5d_vs_spy",
                "relative_strength_vs_spy_5d",
                "spy_relative_strength_5d",
            ],
        )
        if spy_positive is True:
            score += 1
            positive_reasons.append("SPY 대비 5일 상대강도 우위")
        elif spy_missing:
            data_quality_notes.append("SPY 대비 5일 상대강도 데이터 부족")

        qqq_positive, qqq_missing = _is_relative_strength_positive(
            raw_indicators,
            bool_keys=[
                "rs_5d_vs_qqq_positive",
                "relative_strength_5d_vs_qqq_positive",
                "outperforming_qqq_5d",
            ],
            value_keys=[
                "rs_5d_vs_qqq",
                "relative_strength_5d_vs_qqq",
                "relative_strength_vs_qqq_5d",
                "qqq_relative_strength_5d",
            ],
        )
        if qqq_positive is True:
            score += 1
            positive_reasons.append("QQQ 대비 5일 상대강도 우위")
        elif qqq_missing:
            data_quality_notes.append("QQQ 대비 5일 상대강도 데이터 부족")

        sector_strong = _get_bool(
            raw_indicators,
            [
                "sector_strong",
                "is_sector_strong",
                "sector_etf_strong",
                "sector_outperforming",
            ],
        )
        if sector_strong is True:
            score += 1
            positive_reasons.append("관련 섹터 ETF 강세")

        event_score_delta, ticker_event_flags, ticker_event_negative_reasons = (
            _score_earnings_events(
                ticker=ticker,
                events=events,
                today=today_date,
                risk_window_days=earnings_risk_window_days,
            )
        )
        score += event_score_delta
        event_flags.extend(ticker_event_flags)
        negative_reasons.extend(ticker_event_negative_reasons)

        _add_market_regime_notes(
            market_regime=market_regime,
            data_quality_notes=data_quality_notes,
            event_flags=event_flags,
        )

        grade = score_to_grade(score)

        if _has_insufficient_core_data(data_quality_notes):
            if grade in {"A", "B"}:
                grade = "C"
                data_quality_notes.append("데이터 부족으로 등급을 C로 제한")
            elif grade == "D":
                data_quality_notes.append("데이터 부족 및 약세 신호로 D 유지")

        results.append(
            {
                "ticker": ticker,
                "grade": grade,
                "score": int(score),
                "positive_reasons": positive_reasons,
                "negative_reasons": negative_reasons,
                "event_flags": _dedupe(event_flags),
                "data_quality_notes": _dedupe(data_quality_notes),
            }
        )

    return sorted(
        results,
        key=lambda x: (
            _grade_sort_rank(x["grade"]),
            -int(x["score"]),
            x["ticker"],
        ),
    )


def score_to_grade(score: int | float) -> str:
    """
    Convert numeric score to A/B/C/D grade.
    """
    if score >= 7:
        return "A"
    if 4 <= score <= 6:
        return "B"
    if 1 <= score <= 3:
        return "C"
    return "D"


def group_rankings_by_grade(rankings: List[RankedTicker]) -> Dict[str, List[RankedTicker]]:
    """
    Helper for packet_builder.py.

    Returns:
        {
          "A": [...],
          "B": [...],
          "C": [...],
          "D": [...]
        }
    """
    grouped = {"A": [], "B": [], "C": [], "D": []}

    for item in rankings:
        grade = str(item.get("grade", "C")).upper()
        if grade not in grouped:
            grade = "C"
        grouped[grade].append(item)

    return grouped


def _resolve_tickers(
    indicators_by_ticker: IndicatorMap,
    watchlist: Optional[Iterable[str]],
) -> List[str]:
    if watchlist is not None:
        tickers = [str(x).strip().upper() for x in watchlist if str(x).strip()]
    else:
        tickers = [str(x).strip().upper() for x in indicators_by_ticker.keys() if str(x).strip()]

    seen = set()
    unique: List[str] = []
    for ticker in tickers:
        if ticker not in seen:
            seen.add(ticker)
            unique.append(ticker)

    return unique


def _get_number(data: Dict[str, Any], keys: List[str]) -> Optional[float]:
    for key in keys:
        if key in data:
            value = data.get(key)
            try:
                if value is None or value == "":
                    continue
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _get_bool(data: Dict[str, Any], keys: List[str]) -> Optional[bool]:
    for key in keys:
        if key not in data:
            continue

        value = data.get(key)

        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "y", "1", "above"}:
                return True
            if normalized in {"false", "no", "n", "0", "below"}:
                return False

        if isinstance(value, (int, float)):
            return bool(value)

    return None


def _get_bool_or_compare(
    data: Dict[str, Any],
    bool_keys: List[str],
    close: Optional[float],
    average: Optional[float],
) -> Optional[bool]:
    explicit = _get_bool(data, bool_keys)
    if explicit is not None:
        return explicit

    if close is None or average is None:
        return None

    return close > average


def _is_volume_above_20d_avg(data: Dict[str, Any]) -> Optional[bool]:
    explicit = _get_bool(
        data,
        [
            "volume_above_20d_avg",
            "volume_above_avg20",
            "volume_above_average_20d",
            "is_volume_above_20d_avg",
        ],
    )
    if explicit is not None:
        return explicit

    volume = _get_number(
        data,
        [
            "volume",
            "Volume",
            "latest_volume",
        ],
    )
    volume_avg_20 = _get_number(
        data,
        [
            "volume_20d_avg",
            "avg_volume_20d",
            "volume_avg_20d",
            "20d_avg_volume",
            "average_volume_20d",
        ],
    )

    if volume is None or volume_avg_20 is None:
        return None

    return volume >= volume_avg_20


def _is_near_20d_high(
    raw_indicators: Dict[str, Any],
    close: Optional[float],
    near_pct: float,
) -> Optional[bool]:
    explicit = _get_bool(
        raw_indicators,
        [
            "near_20d_high",
            "is_near_20d_high",
            "near_twenty_day_high",
        ],
    )
    if explicit is not None:
        return explicit

    high_20d = _get_number(
        raw_indicators,
        [
            "high_20d",
            "twenty_day_high",
            "20d_high",
            "highest_20d",
            "rolling_high_20d",
        ],
    )

    if close is None or high_20d is None or high_20d <= 0:
        return None

    return close >= high_20d * (1 - near_pct)


def _is_near_20d_low(
    raw_indicators: Dict[str, Any],
    close: Optional[float],
    near_pct: float,
) -> Optional[bool]:
    explicit = _get_bool(
        raw_indicators,
        [
            "near_20d_low",
            "is_near_20d_low",
            "near_twenty_day_low",
        ],
    )
    if explicit is not None:
        return explicit

    low_20d = _get_number(
        raw_indicators,
        [
            "low_20d",
            "twenty_day_low",
            "20d_low",
            "lowest_20d",
            "rolling_low_20d",
        ],
    )

    if close is None or low_20d is None or low_20d <= 0:
        return None

    return close <= low_20d * (1 + near_pct)


def _is_relative_strength_positive(
    raw_indicators: Dict[str, Any],
    bool_keys: List[str],
    value_keys: List[str],
) -> Tuple[Optional[bool], bool]:
    """
    Returns:
        (is_positive, is_missing)

    Relative strength is independently scored for SPY and QQQ.
    """
    explicit = _get_bool(raw_indicators, bool_keys)
    if explicit is not None:
        return explicit, False

    value = _get_number(raw_indicators, value_keys)
    if value is None:
        return None, True

    return value > 0, False


def _score_earnings_events(
    ticker: str,
    events: List[Dict[str, Any]],
    today: date,
    risk_window_days: int,
) -> Tuple[int, List[str], List[str]]:
    """
    Earnings scoring:
    - Earnings today or tomorrow: -2
    - Earnings within 7 days: -1
    No double penalty is applied.
    """
    relevant_events = [
        event for event in events if _event_matches_ticker(event=event, ticker=ticker)
    ]

    score_delta = 0
    event_flags: List[str] = []
    negative_reasons: List[str] = []

    immediate_earnings = False
    within_window = False

    for event in relevant_events:
        if not _is_earnings_event(event):
            continue

        risk_flag = str(event.get("risk_flag", "")).strip().lower()
        event_date = _extract_event_date(event)

        if risk_flag in {
            "earnings_today",
            "earnings_tomorrow",
            "earnings_day",
            "earnings_next_day",
        }:
            immediate_earnings = True
            event_flags.append(event.get("risk_flag", "earnings_today_or_tomorrow"))
            continue

        if risk_flag == "earnings_within_7d":
            within_window = True
            event_flags.append("earnings_within_7d")

        if event_date is None:
            continue

        days_until = (event_date - today).days

        if days_until in {0, 1}:
            immediate_earnings = True
            if days_until == 0:
                event_flags.append("earnings_today")
            else:
                event_flags.append("earnings_tomorrow")
        elif 0 <= days_until <= risk_window_days:
            within_window = True
            event_flags.append("earnings_within_7d")

    if immediate_earnings:
        score_delta -= 2
        negative_reasons.append("어닝 당일/익일")
    elif within_window:
        score_delta -= 1
        negative_reasons.append("어닝 7일 이내")

    return score_delta, _dedupe(event_flags), _dedupe(negative_reasons)


def _event_matches_ticker(event: Dict[str, Any], ticker: str) -> bool:
    ticker = ticker.upper()

    candidate_keys = [
        "ticker",
        "symbol",
        "Ticker",
        "Symbol",
    ]

    for key in candidate_keys:
        value = event.get(key)
        if value is None:
            continue

        if isinstance(value, str) and value.strip().upper() == ticker:
            return True

        if isinstance(value, list):
            normalized = [str(x).strip().upper() for x in value]
            if ticker in normalized:
                return True

    return False


def _is_earnings_event(event: Dict[str, Any]) -> bool:
    fields = [
        str(event.get("type", "")),
        str(event.get("category", "")),
        str(event.get("name", "")),
        str(event.get("risk_flag", "")),
    ]

    joined = " ".join(fields).lower()

    return any(
        keyword in joined
        for keyword in [
            "earning",
            "earnings",
            "실적",
            "어닝",
        ]
    )


def _extract_event_date(event: Dict[str, Any]) -> Optional[date]:
    for key in [
        "date",
        "reportDate",
        "report_date",
        "earnings_date",
        "event_date",
        "datetime",
        "timestamp",
    ]:
        if key not in event:
            continue

        parsed = _coerce_date(event.get(key))
        if parsed is not None:
            return parsed

    return None


def _coerce_date(value: Any) -> Optional[date]:
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None

        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            pass

        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue

    return None


def _add_market_regime_notes(
    market_regime: Dict[str, Any],
    data_quality_notes: List[str],
    event_flags: List[str],
) -> None:
    """
    Market regime is included as an input because downstream modules need
    the context. The scoring rules here do not directly add/subtract points
    for market mode.

    This function attaches caution flags/notes so packet_builder or risk_engine
    can display them later.
    """
    mode = str(
        market_regime.get("mode")
        or market_regime.get("market_mode")
        or ""
    ).strip()

    overlay = str(
        market_regime.get("event_overlay")
        or market_regime.get("overlay")
        or ""
    ).strip()

    if mode.lower() in {"caution", "defensive"}:
        event_flags.append(f"market_mode_{mode.lower()}")
        data_quality_notes.append(f"시장 모드 {mode}: 공격적 해석 주의")

    if overlay.lower() in {"caution", "defensive"}:
        event_flags.append(f"event_overlay_{overlay.lower()}")


def _has_insufficient_core_data(data_quality_notes: List[str]) -> bool:
    """
    Prevent aggressive A/B promotion when core ranking data is incomplete.

    Rule:
    - If 50DMA or 200DMA judgment is missing, cap A/B at C.
    - Otherwise, keep the previous missing_count >= 2 rule.
    """
    if "50DMA 판단 데이터 부족" in data_quality_notes:
        return True

    if "200DMA 판단 데이터 부족" in data_quality_notes:
        return True

    critical_keywords = [
        "20DMA 판단 데이터 부족",
        "50DMA 판단 데이터 부족",
        "200DMA 판단 데이터 부족",
        "거래량 20일 평균 판단 데이터 부족",
        "20일 고점 근처 판단 데이터 부족",
        "SPY 대비 5일 상대강도 데이터 부족",
        "QQQ 대비 5일 상대강도 데이터 부족",
    ]

    missing_count = sum(
        1 for note in data_quality_notes if note in critical_keywords
    )

    return missing_count >= 2


def _grade_sort_rank(grade: str) -> int:
    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    return order.get(str(grade).upper(), 9)


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []

    for item in items:
        if item not in seen:
            seen.add(item)
            output.append(item)

    return output