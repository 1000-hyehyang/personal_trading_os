"""
Setup candidate classifier for Personal Trading OS MVP.

Role:
- Classify watchlist ranking results into Breakout / Pullback / Avoid.
- Read setup rules from config/setups.yaml structure:
  - required
  - preferred
  - required_any
  - reject_if
- Apply conservative behavior when market mode is Caution or Defensive.

This module does not fetch price data.
It consumes already-calculated watchlist ranking / indicator results.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


DEFAULT_SETUPS_CONFIG: dict[str, Any] = {
    "setups": {
        "breakout": {
            "description": "전고점 또는 20일 고점 근처 돌파 후보",
            "required": [
                "close_above_20dma",
                "close_above_50dma",
                "near_20d_high",
                "volume_above_20d_avg",
            ],
            "preferred": [
                "market_mode_not_defensive",
                "sector_strong",
                "relative_strength_vs_qqq_positive",
            ],
            "reject_if": [
                "vix_spike",
                "earnings_today",
                "earnings_tomorrow",
                "high_impact_macro_today",
            ],
        },
        "pullback": {
            "description": "상승 추세 중 20일선 근처 눌림 후보",
            "required": [
                "close_above_50dma",
                "price_near_20dma",
                "rsi_not_overheated",
            ],
            "preferred": [
                "sector_not_weak",
                "market_mode_not_defensive",
            ],
            "reject_if": [
                "vix_spike",
                "earnings_today",
                "high_impact_macro_today",
            ],
        },
        "avoid": {
            "description": "회피 또는 리스크 관리 대상",
            "required_any": [
                "close_below_50dma",
                "close_below_200dma",
                "market_mode_defensive",
                "major_event_high_impact",
            ],
        },
    }
}


@dataclass(frozen=True)
class SetupMatch:
    ticker: str
    setup_type: str
    description: str
    matched_required: list[str]
    matched_preferred: list[str]
    matched_required_any: list[str]
    matched_reject_if: list[str]
    missing_required: list[str]
    reasons: list[str]
    grade: str | None = None
    score: int | float | None = None
    event_flags: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "setup_type": self.setup_type,
            "description": self.description,
            "matched_required": self.matched_required,
            "matched_preferred": self.matched_preferred,
            "matched_required_any": self.matched_required_any,
            "matched_reject_if": self.matched_reject_if,
            "missing_required": self.missing_required,
            "reasons": self.reasons,
            "grade": self.grade,
            "score": self.score,
            "event_flags": self.event_flags or [],
        }


def load_setups_config(path: str | Path = "config/setups.yaml") -> dict[str, Any]:
    """
    Load setups.yaml. If it is missing or invalid, return the default MVP config.
    """
    config_path = Path(path)
    if not config_path.exists():
        return DEFAULT_SETUPS_CONFIG

    if yaml is None:
        raise RuntimeError("pyyaml is required to load setups.yaml")

    try:
        with config_path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
    except Exception:
        return DEFAULT_SETUPS_CONFIG

    if not isinstance(loaded, dict) or "setups" not in loaded:
        return DEFAULT_SETUPS_CONFIG

    return loaded


def match_setups(
    watchlist_rankings: list[dict[str, Any]] | dict[str, Any],
    market_regime: dict[str, Any] | str | None = None,
    setups_config: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Main API.

    Returns:
    {
      "breakout": [...],
      "pullback": [...],
      "avoid": [...]
    }
    """
    config = setups_config or DEFAULT_SETUPS_CONFIG
    setups = config.get("setups", {}) if isinstance(config, dict) else {}
    rows = _normalize_rankings(watchlist_rankings)
    mode = _extract_market_mode(market_regime)
    is_defensive = _is_defensive_mode(mode)
    is_caution = _is_caution_mode(mode)

    output: dict[str, list[dict[str, Any]]] = {
        "breakout": [],
        "pullback": [],
        "avoid": [],
    }

    for row in rows:
        ticker = str(row.get("ticker") or row.get("symbol") or "").upper().strip()
        if not ticker:
            continue

        signals = _build_signal_map(row=row, market_mode=mode, market_regime=market_regime)

        avoid_rule = setups.get("avoid", {})
        avoid_match = _evaluate_setup_rule(
            ticker=ticker,
            setup_type="avoid",
            rule=avoid_rule,
            row=row,
            signals=signals,
        )

        if avoid_match is not None:
            avoid_dict = avoid_match.to_dict()

            if is_defensive:
                avoid_dict = _append_unique_reason(
                    avoid_dict,
                    "Defensive mode — no active setup",
                )

            output["avoid"].append(avoid_dict)
            continue

        if is_defensive:
            output["avoid"].append(
                _manual_avoid_match(
                    ticker=ticker,
                    row=row,
                    reason="Defensive mode — no active setup",
                    market_mode=mode,
                )
            )
            continue

        breakout_rule = setups.get("breakout", {})
        breakout_match = _evaluate_setup_rule(
            ticker=ticker,
            setup_type="breakout",
            rule=breakout_rule,
            row=row,
            signals=signals,
        )

        if breakout_match is not None:
            if is_caution:
                output["avoid"].append(
                    _manual_avoid_match(
                        ticker=ticker,
                        row=row,
                        reason="Caution mode — breakout blocked",
                        market_mode=mode,
                    )
                )
            else:
                output["breakout"].append(breakout_match.to_dict())
            continue

        pullback_rule = setups.get("pullback", {})
        pullback_match = _evaluate_setup_rule(
            ticker=ticker,
            setup_type="pullback",
            rule=pullback_rule,
            row=row,
            signals=signals,
        )
        if pullback_match is not None:
            output["pullback"].append(pullback_match.to_dict())

    output["breakout"] = _sort_candidates(output["breakout"])
    output["pullback"] = _sort_candidates(output["pullback"])
    output["avoid"] = _sort_candidates(output["avoid"], reverse=False)

    return output


def _append_unique_reason(candidate: dict[str, Any], reason: str) -> dict[str, Any]:
    reasons = candidate.setdefault("reasons", [])
    if reason not in reasons:
        reasons.append(reason)
    return candidate


def classify_setups(
    watchlist_rankings: list[dict[str, Any]] | dict[str, Any],
    market_regime: dict[str, Any] | str | None = None,
    setups_config: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Backward-compatible alias.
    """
    return match_setups(
        watchlist_rankings=watchlist_rankings,
        market_regime=market_regime,
        setups_config=setups_config,
    )


def _evaluate_setup_rule(
    ticker: str,
    setup_type: str,
    rule: dict[str, Any],
    row: dict[str, Any],
    signals: dict[str, bool],
) -> SetupMatch | None:
    required = _as_list(rule.get("required"))
    preferred = _as_list(rule.get("preferred"))
    required_any = _as_list(rule.get("required_any"))
    reject_if = _as_list(rule.get("reject_if"))

    matched_reject_if = [name for name in reject_if if signals.get(name, False)]
    if matched_reject_if:
        return None

    matched_required = [name for name in required if signals.get(name, False)]
    missing_required = [name for name in required if not signals.get(name, False)]

    matched_preferred = [name for name in preferred if signals.get(name, False)]
    matched_required_any = [name for name in required_any if signals.get(name, False)]

    if required and missing_required:
        return None

    if required_any and not matched_required_any:
        return None

    if not required and not required_any:
        return None

    reasons = _build_reasons(
        setup_type=setup_type,
        matched_required=matched_required,
        matched_preferred=matched_preferred,
        matched_required_any=matched_required_any,
        matched_reject_if=matched_reject_if,
        row=row,
    )

    return SetupMatch(
        ticker=ticker,
        setup_type=setup_type,
        description=str(rule.get("description") or ""),
        matched_required=matched_required,
        matched_preferred=matched_preferred,
        matched_required_any=matched_required_any,
        matched_reject_if=matched_reject_if,
        missing_required=missing_required,
        reasons=reasons,
        grade=_safe_str(row.get("grade")),
        score=row.get("score"),
        event_flags=_as_list(row.get("event_flags")),
    )


def _manual_avoid_match(
    ticker: str,
    row: dict[str, Any],
    reason: str,
    market_mode: str,
) -> dict[str, Any]:
    return SetupMatch(
        ticker=ticker,
        setup_type="avoid",
        description="시장 모드 또는 리스크 조건으로 인해 활성 셋업 제외",
        matched_required=[],
        matched_preferred=[],
        matched_required_any=[],
        matched_reject_if=[],
        missing_required=[],
        reasons=[reason, f"Market mode: {market_mode}"],
        grade=_safe_str(row.get("grade")),
        score=row.get("score"),
        event_flags=_as_list(row.get("event_flags")),
    ).to_dict()


def _build_signal_map(
    row: dict[str, Any],
    market_mode: str,
    market_regime: dict[str, Any] | str | None = None,
) -> dict[str, bool]:
    positive_reasons = _lower_join(row.get("positive_reasons"))
    negative_reasons = _lower_join(row.get("negative_reasons"))
    event_flags = {str(x).lower() for x in _as_list(row.get("event_flags"))}
    signals_raw = row.get("signals") if isinstance(row.get("signals"), dict) else {}

    def explicit_bool(*keys: str) -> bool | None:
        for key in keys:
            if key in row:
                return _to_bool(row.get(key))
            if key in signals_raw:
                return _to_bool(signals_raw.get(key))
        return None

    close = _to_float(row.get("close"))
    dma20 = _first_float(row, ["dma20", "ma20", "20dma", "sma20", "moving_average_20"])
    dma50 = _first_float(row, ["dma50", "ma50", "50dma", "sma50", "moving_average_50"])
    dma200 = _first_float(row, ["dma200", "ma200", "200dma", "sma200", "moving_average_200"])
    high20 = _first_float(row, ["high_20d", "20d_high", "twenty_day_high"])
    low20 = _first_float(row, ["low_20d", "20d_low", "twenty_day_low"])
    volume = _first_float(row, ["volume", "latest_volume"])
    avg_volume20 = _first_float(row, ["avg_volume_20d", "volume_20d_avg", "avg_volume20"])
    rsi = _to_float(row.get("rsi") or row.get("rsi14"))

    close_above_20dma = _coalesce_bool(
        explicit_bool("close_above_20dma", "above_20dma"),
        _compare(close, dma20, ">"),
        "20일선 위" in positive_reasons or ("20dma" in positive_reasons and "above" in positive_reasons),
    )
    close_above_50dma = _coalesce_bool(
        explicit_bool("close_above_50dma", "above_50dma"),
        _compare(close, dma50, ">"),
        "50일선 위" in positive_reasons or ("50dma" in positive_reasons and "above" in positive_reasons),
    )
    close_above_200dma = _coalesce_bool(
        explicit_bool("close_above_200dma", "above_200dma"),
        _compare(close, dma200, ">"),
        "200일선 위" in positive_reasons or ("200dma" in positive_reasons and "above" in positive_reasons),
    )

    close_below_50dma = _coalesce_bool(
        explicit_bool("close_below_50dma", "below_50dma"),
        _compare(close, dma50, "<"),
        "50일선 아래" in negative_reasons or ("50dma" in negative_reasons and "below" in negative_reasons),
    )
    close_below_200dma = _coalesce_bool(
        explicit_bool("close_below_200dma", "below_200dma"),
        _compare(close, dma200, "<"),
        "200일선 아래" in negative_reasons or ("200dma" in negative_reasons and "below" in negative_reasons),
    )

    near_20d_high = _coalesce_bool(
        explicit_bool("near_20d_high", "near_twenty_day_high"),
        _near(close, high20, pct=0.03),
        "20일 고점 근처" in positive_reasons or "20d high" in positive_reasons,
    )
    near_20d_low = _coalesce_bool(
        explicit_bool("near_20d_low", "near_twenty_day_low"),
        _near(close, low20, pct=0.03),
        "20일 저점 근처" in negative_reasons or "20d low" in negative_reasons,
    )
    volume_above_20d_avg = _coalesce_bool(
        explicit_bool("volume_above_20d_avg", "volume_above_average"),
        _compare(volume, avg_volume20, ">="),
        "거래량" in positive_reasons and ("증가" in positive_reasons or "평균보다 큼" in positive_reasons),
    )

    price_near_20dma = _coalesce_bool(
        explicit_bool("price_near_20dma", "near_20dma"),
        _near(close, dma20, pct=0.035),
        "20일선 근처" in positive_reasons or "20dma near" in positive_reasons,
    )
    rsi_not_overheated = _coalesce_bool(
        explicit_bool("rsi_not_overheated"),
        None if rsi is None else rsi < 70,
        "과열" not in negative_reasons,
    )

    sector_strong = _coalesce_bool(
        explicit_bool("sector_strong"),
        "섹터 강" in positive_reasons or "sector strong" in positive_reasons,
    )
    sector_not_weak = _coalesce_bool(
        explicit_bool("sector_not_weak"),
        not ("섹터 약" in negative_reasons or "sector weak" in negative_reasons),
    )
    relative_strength_vs_qqq_positive = _coalesce_bool(
        explicit_bool("relative_strength_vs_qqq_positive", "rs_vs_qqq_positive"),
        "qqq 대비 상대강도 우위" in positive_reasons
        or "qqq보다" in positive_reasons
        or "rs_vs_qqq_positive" in positive_reasons,
    )

    earnings_today = "earnings_today" in event_flags
    earnings_tomorrow = "earnings_tomorrow" in event_flags
    high_impact_macro_today = "macro_high_today" in event_flags or "fomc_today" in event_flags
    no_high_impact_event_today = not high_impact_macro_today

    vix_spike = _detect_vix_spike(market_regime)

    major_event_high_impact = _coalesce_bool(
        explicit_bool("major_event_high_impact"),
        any(
            flag in event_flags
            for flag in {
                "macro_high_today",
                "macro_high_next_24h",
                "fomc_today",
                "fomc_minutes_today",
                "earnings_today",
                "earnings_tomorrow",
                "manual_event_high",
            }
        ),
        "이벤트 리스크" in negative_reasons or "어닝 당일" in negative_reasons,
    )

    market_mode_defensive = _is_defensive_mode(market_mode)
    market_mode_caution = _is_caution_mode(market_mode)

    return {
        "close_above_20dma": close_above_20dma,
        "close_above_50dma": close_above_50dma,
        "close_above_200dma": close_above_200dma,
        "close_below_50dma": close_below_50dma,
        "close_below_200dma": close_below_200dma,
        "near_20d_high": near_20d_high,
        "near_20d_low": near_20d_low,
        "volume_above_20d_avg": volume_above_20d_avg,
        "price_near_20dma": price_near_20dma,
        "rsi_not_overheated": rsi_not_overheated,
        "sector_strong": sector_strong,
        "sector_not_weak": sector_not_weak,
        "relative_strength_vs_qqq_positive": relative_strength_vs_qqq_positive,
        "market_mode_defensive": market_mode_defensive,
        "market_mode_caution": market_mode_caution,
        "market_mode_not_defensive": not market_mode_defensive,
        "major_event_high_impact": major_event_high_impact,
        "vix_spike": vix_spike,
        "earnings_today": earnings_today,
        "earnings_tomorrow": earnings_tomorrow,
        "high_impact_macro_today": high_impact_macro_today,
        "no_high_impact_event_today": no_high_impact_event_today,
    }


def _detect_vix_spike(market_regime: dict[str, Any] | str | None) -> bool:
    if not isinstance(market_regime, dict):
        return False

    if "vix_spike" in market_regime:
        return _to_bool(market_regime.get("vix_spike"))

    change = _to_float(
        market_regime.get("vix_change_pct")
        or market_regime.get("vix_pct_change")
        or market_regime.get("vix_change")
    )
    return change is not None and change >= 5.0


def _build_reasons(
    setup_type: str,
    matched_required: list[str],
    matched_preferred: list[str],
    matched_required_any: list[str],
    matched_reject_if: list[str],
    row: dict[str, Any],
) -> list[str]:
    label_map = {
        "close_above_20dma": "20일선 위",
        "close_above_50dma": "50일선 위",
        "close_above_200dma": "200일선 위",
        "close_below_50dma": "50일선 아래",
        "close_below_200dma": "200일선 아래",
        "near_20d_high": "20일 고점 근처",
        "near_20d_low": "20일 저점 근처",
        "volume_above_20d_avg": "거래량 20일 평균 이상",
        "price_near_20dma": "20일선 근처 눌림",
        "rsi_not_overheated": "RSI 과열 아님",
        "sector_strong": "섹터 강세",
        "sector_not_weak": "섹터 약세 아님",
        "relative_strength_vs_qqq_positive": "QQQ 대비 상대강도 우위",
        "market_mode_not_defensive": "시장 모드 Defensive 아님",
        "market_mode_defensive": "시장 모드 Defensive",
        "market_mode_caution": "시장 모드 Caution",
        "major_event_high_impact": "고영향 이벤트 리스크",
        "vix_spike": "VIX 급등",
        "earnings_today": "어닝 당일",
        "earnings_tomorrow": "어닝 익일/직전",
        "high_impact_macro_today": "고영향 매크로 이벤트 당일",
        "no_high_impact_event_today": "고영향 이벤트 당일 아님",
    }

    raw = []
    if setup_type == "avoid":
        raw.extend(matched_required_any)
    else:
        raw.extend(matched_required)
        raw.extend(matched_preferred)

    raw.extend(matched_reject_if)

    reasons = [label_map.get(x, x) for x in raw]

    negative_reasons = _as_list(row.get("negative_reasons"))
    if setup_type == "avoid":
        for reason in negative_reasons:
            if isinstance(reason, str) and reason not in reasons:
                reasons.append(reason)

    return _unique_keep_order(reasons)


def _normalize_rankings(data: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if not isinstance(data, dict):
        return []

    if isinstance(data.get("rankings"), list):
        return [x for x in data["rankings"] if isinstance(x, dict)]

    if isinstance(data.get("watchlist"), list):
        return [x for x in data["watchlist"] if isinstance(x, dict)]

    rows: list[dict[str, Any]] = []
    for grade in ["A", "B", "C", "D"]:
        items = data.get(grade) or data.get(f"{grade}_grade") or data.get(f"{grade.lower()}_grade")
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    item = dict(item)
                    item.setdefault("grade", grade)
                    rows.append(item)

    return rows


def _extract_market_mode(market_regime: dict[str, Any] | str | None) -> str:
    if market_regime is None:
        return "Neutral"
    if isinstance(market_regime, str):
        return market_regime
    if isinstance(market_regime, dict):
        return str(
            market_regime.get("mode")
            or market_regime.get("market_mode")
            or market_regime.get("regime")
            or "Neutral"
        )
    return "Neutral"


def _is_defensive_mode(mode: str) -> bool:
    normalized = str(mode).strip().lower().replace("_", "-")
    return normalized == "defensive"


def _is_caution_mode(mode: str) -> bool:
    normalized = str(mode).strip().lower().replace("_", "-")
    return normalized == "caution"


def _sort_candidates(items: list[dict[str, Any]], reverse: bool = True) -> list[dict[str, Any]]:
    grade_rank = {"A": 4, "B": 3, "C": 2, "D": 1, None: 0}

    def key_func(item: dict[str, Any]) -> tuple[int, float, str]:
        grade = item.get("grade")
        score = item.get("score")
        try:
            score_float = float(score)
        except (TypeError, ValueError):
            score_float = 0.0
        return (grade_rank.get(grade, 0), score_float, str(item.get("ticker") or ""))

    return sorted(items, key=key_func, reverse=reverse)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _lower_join(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, list):
        return " ".join(str(x) for x in value).lower()
    return str(value).lower()


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_float(row: dict[str, Any], keys: list[str]) -> float | None:
    for key in keys:
        value = _to_float(row.get(key))
        if value is not None:
            return value
    return None


def _compare(left: float | None, right: float | None, op: str) -> bool | None:
    if left is None or right is None:
        return None
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    return None


def _near(left: float | None, right: float | None, pct: float) -> bool | None:
    if left is None or right is None or right == 0:
        return None
    return abs(left - right) / abs(right) <= pct


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    return normalized in {"true", "1", "yes", "y", "above", "positive", "ok"}


def _coalesce_bool(*values: bool | None) -> bool:
    for value in values:
        if value is not None:
            return bool(value)
    return False


def _unique_keep_order(values: list[Any]) -> list[Any]:
    seen = set()
    output = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output