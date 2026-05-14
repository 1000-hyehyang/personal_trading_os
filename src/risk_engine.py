"""
Risk engine for Personal Trading OS MVP.

Role:
- Generate risk_warnings
- Generate do_not_do_list
- Generate no_trade_flags
- Generate ticker_specific_risks

Inputs:
- market_regime result
- watchlist_ranker result
- events_merged.json
- rules.yaml
- manual_news_notes.md

This module does not place trades and does not provide buy/sell recommendations.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


REQUIRED_DO_NOT_DO = [
    "장초반 첫 5~15분 갭상승 종목 무근거 추격 금지",
    "D급 종목 물타기 금지",
    "손절가 없는 진입 금지",
    "VIX 상승 중 고베타 종목 포지션 확대 금지",
    "CPI/FOMC/대형 실적 전후 과대 진입 금지",
    "시장 모드 Caution/Defensive에서 신규 공격 매매 금지",
    "뉴스 하나만 보고 차트·섹터 확인 없이 진입 금지",
]

DEFAULT_RULES = {
    "global_do_not_do": REQUIRED_DO_NOT_DO,
    "risk_modes": {
        "risk_on": {"position_multiplier": 1.0},
        "mild_risk_on": {"position_multiplier": 0.8},
        "neutral": {"position_multiplier": 0.6},
        "caution": {"position_multiplier": 0.4},
        "defensive": {"position_multiplier": 0.2},
    },
}

DEFAULT_HIGH_BETA_TICKERS = {
    "TSLA",
    "COIN",
    "PLTR",
    "RBLX",
    "RKLB",
    "ASTS",
    "SNOW",
    "DDOG",
    "NET",
    "MDB",
    "CRWD",
    "ARM",
    "AMD",
    "MSTR",
    "HOOD",
    "SHOP",
}


def load_rules_config(path: str | Path = "config/rules.yaml") -> dict[str, Any]:
    """
    Load rules.yaml.

    Supports:
    - global_do_not_do as list[str]
    - global_do_not_do as list[dict] with text field
    - risk_modes with normalized keys:
      risk_on, mild_risk_on, neutral, caution, defensive
    - risk_modes with display keys:
      Risk-On, Mild Risk-On, Neutral, Caution, Defensive
    """
    config_path = Path(path)
    if not config_path.exists():
        return DEFAULT_RULES

    if yaml is None:
        raise RuntimeError("pyyaml is required to load rules.yaml")

    try:
        with config_path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
    except Exception:
        return DEFAULT_RULES

    if not isinstance(loaded, dict):
        return DEFAULT_RULES

    merged = dict(DEFAULT_RULES)
    merged.update(loaded)

    if "global_do_not_do" not in merged:
        merged["global_do_not_do"] = REQUIRED_DO_NOT_DO

    if "risk_modes" not in merged:
        merged["risk_modes"] = DEFAULT_RULES["risk_modes"]

    return merged


def load_manual_news_notes(path: str | Path = "data/manual_news_notes.md") -> str:
    """
    Load manual news notes as plain text.
    """
    notes_path = Path(path)
    if not notes_path.exists():
        return ""

    try:
        return notes_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return notes_path.read_text(encoding="utf-8-sig", errors="ignore")
    except Exception:
        return ""


def run_risk_engine(
    market_regime: dict[str, Any] | str | None,
    watchlist_ranker_result: list[dict[str, Any]] | dict[str, Any] | None,
    events_merged: dict[str, Any] | list[dict[str, Any]] | None,
    rules_config: dict[str, Any] | None = None,
    manual_news_notes: str | None = None,
    high_beta_tickers: set[str] | None = None,
) -> dict[str, Any]:
    """
    Main API for risk engine.
    """
    rules = _merge_rules(rules_config)
    high_beta = high_beta_tickers or DEFAULT_HIGH_BETA_TICKERS

    mode = _extract_market_mode(market_regime)
    normalized_mode = _normalize_mode_key(mode)
    position_multiplier = _get_position_multiplier(rules, mode)

    rankings = _normalize_rankings(watchlist_ranker_result)
    event_context = _normalize_events(events_merged)
    notes = manual_news_notes or ""

    do_not_do_list = _build_do_not_do_list(rules)
    risk_warnings: list[str] = []
    no_trade_flags: list[str] = []
    ticker_specific_risks: dict[str, list[str]] = {}

    is_caution = normalized_mode in {"caution", "defensive"}
    is_defensive = normalized_mode == "defensive"
    vix_rising = _detect_vix_rising(market_regime)
    vix_spike = _detect_vix_spike(market_regime)
    high_impact_macro_today = event_context["high_impact_macro_today"]
    fomc_today = event_context["fomc_today"]
    fomc_minutes_today = event_context["fomc_minutes_today"]

    if is_caution:
        warning = "시장 모드가 Caution/Defensive입니다. 신규 공격 매매를 제한하고 포지션 사이즈를 축소하세요."
        if position_multiplier is not None:
            warning += f" 권장 position_multiplier: {position_multiplier}"
        risk_warnings.append(warning)

    if is_defensive:
        risk_warnings.append("Defensive 모드입니다. Breakout/Pullback 신규 공격 매매보다 관찰 우선입니다.")
        no_trade_flags.append("Defensive mode")

    if vix_rising:
        risk_warnings.append("VIX 상승 감지: 고베타 종목 포지션 확대와 장초반 추격을 피하세요.")

    if vix_spike:
        no_trade_flags.append("VIX spike or sharp VIX rise")

    if high_impact_macro_today:
        risk_warnings.append("High-impact macro event today: 발표 전후 과대 진입과 첫 반응 추격을 피하세요.")
        no_trade_flags.append("High-impact macro event today")

    if fomc_today:
        risk_warnings.append("FOMC 이벤트 당일입니다. 첫 방향성 반응 추격을 피하고 확인 후 판단하세요.")

    if fomc_minutes_today:
        risk_warnings.append("FOMC Minutes 이벤트 당일입니다. 변동성 확대 가능성에 주의하세요.")

    if event_context["manual_event_high"]:
        risk_warnings.append("수동 입력 고영향 이벤트가 있습니다. manual events와 뉴스 메모를 확인하세요.")

    if notes.strip():
        risk_warnings.append("manual_news_notes.md에 수동 뉴스 메모가 있습니다. 뉴스 하나만 보고 진입하지 말고 차트·섹터를 확인하세요.")

    grade_counts = _count_grades(rankings)
    total_ranked = sum(grade_counts.values())
    cd_count = grade_counts.get("C", 0) + grade_counts.get("D", 0)
    d_count = grade_counts.get("D", 0)

    if d_count > 0:
        risk_warnings.append(f"D급 종목 {d_count}개 감지: 물타기 및 반등 예측 금지.")

    if total_ranked > 0 and cd_count / total_ranked >= 0.6:
        no_trade_flags.append("Majority of watchlist is C/D grade")

    if _detect_qqq_spy_divergence(market_regime):
        no_trade_flags.append("QQQ and SPY direction divergence")

    if _detect_smh_weak(market_regime):
        no_trade_flags.append("SMH weakness")

    if _detect_d_grade_only_strength(rankings):
        no_trade_flags.append("Only D-grade names are showing short-term strength")

    event_risk_by_ticker = event_context["ticker_events"]
    manual_note_by_ticker = _extract_manual_note_tickers(notes, rankings)

    for row in rankings:
        ticker = str(row.get("ticker") or row.get("symbol") or "").upper().strip()
        if not ticker:
            continue

        risks: list[str] = []
        grade = str(row.get("grade") or "").upper()
        event_flags = {str(x).lower() for x in _as_list(row.get("event_flags"))}
        negative_reasons = [str(x) for x in _as_list(row.get("negative_reasons"))]

        if grade == "D":
            risks.append("D급 종목: 물타기 금지, 반등 예측 금지.")

        if grade == "C":
            risks.append("C급 종목: 명확한 셋업 전까지 대기 우선.")

        if ticker in high_beta and vix_rising:
            risks.append("고베타 종목 + VIX 상승: 포지션 확대 금지.")

        if ticker in event_risk_by_ticker:
            risks.extend(event_risk_by_ticker[ticker])

        if "earnings_today" in event_flags:
            risks.append("어닝 당일: 신규 진입 및 과대 포지션 주의.")
        if "earnings_tomorrow" in event_flags:
            risks.append("어닝 익일/직전 리스크: 변동성 확대 주의.")
        if "earnings_within_7d" in event_flags:
            risks.append("어닝 7일 이내: 스윙 진입 주의.")
        if any(flag in event_flags for flag in ["macro_high_today", "fomc_today", "manual_event_high"]):
            risks.append("고영향 이벤트 플래그 보유: 이벤트 전후 과대 진입 금지.")

        for reason in negative_reasons:
            if reason and reason not in risks:
                risks.append(reason)

        if ticker in manual_note_by_ticker:
            risks.append("manual_news_notes.md에 해당 티커 메모 있음: 뉴스·차트·섹터 교차 확인 필요.")

        if risks:
            ticker_specific_risks[ticker] = _unique_keep_order(risks)

    no_trade_bias = len(_unique_keep_order(no_trade_flags)) >= 2

    return {
        "risk_warnings": _unique_keep_order(risk_warnings),
        "do_not_do_list": do_not_do_list,
        "no_trade_flags": _unique_keep_order(no_trade_flags),
        "no_trade_bias": no_trade_bias,
        "ticker_specific_risks": ticker_specific_risks,
        "risk_context": {
            "market_mode": mode,
            "normalized_market_mode": normalized_mode,
            "position_multiplier": position_multiplier,
            "vix_rising": vix_rising,
            "vix_spike": vix_spike,
            "high_impact_macro_today": high_impact_macro_today,
            "fomc_today": fomc_today,
            "fomc_minutes_today": fomc_minutes_today,
            "grade_counts": grade_counts,
            "manual_news_notes_present": bool(notes.strip()),
        },
    }


def build_risk_report(
    market_regime: dict[str, Any] | str | None,
    watchlist_ranker_result: list[dict[str, Any]] | dict[str, Any] | None,
    events_merged: dict[str, Any] | list[dict[str, Any]] | None,
    rules_config: dict[str, Any] | None = None,
    manual_news_notes: str | None = None,
) -> dict[str, Any]:
    """
    Backward-compatible alias.
    """
    return run_risk_engine(
        market_regime=market_regime,
        watchlist_ranker_result=watchlist_ranker_result,
        events_merged=events_merged,
        rules_config=rules_config,
        manual_news_notes=manual_news_notes,
    )


def evaluate_risk(
    market_regime: dict[str, Any] | str | None,
    watchlist_ranker_result: list[dict[str, Any]] | dict[str, Any] | None,
    events_merged: dict[str, Any] | list[dict[str, Any]] | None,
    rules_config: dict[str, Any] | None = None,
    manual_news_notes: str | None = None,
) -> dict[str, Any]:
    """
    Backward-compatible alias.
    """
    return run_risk_engine(
        market_regime=market_regime,
        watchlist_ranker_result=watchlist_ranker_result,
        events_merged=events_merged,
        rules_config=rules_config,
        manual_news_notes=manual_news_notes,
    )


def _merge_rules(rules_config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(rules_config, dict):
        return DEFAULT_RULES

    merged = dict(DEFAULT_RULES)
    merged.update(rules_config)

    if "global_do_not_do" not in merged:
        merged["global_do_not_do"] = REQUIRED_DO_NOT_DO

    if "risk_modes" not in merged:
        merged["risk_modes"] = DEFAULT_RULES["risk_modes"]

    return merged


def _build_do_not_do_list(rules: dict[str, Any]) -> list[str]:
    """
    Build final do-not-do list.

    Supports both:
    global_do_not_do:
      - "장초반..."
      - "D급..."

    and:
    global_do_not_do:
      - id: no_chase_gap_open
        text: "장초반..."
        severity: high
    """
    raw_items = _as_list(rules.get("global_do_not_do"))
    extracted: list[str] = []

    for item in raw_items:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
        else:
            text = str(item).strip()

        if text:
            extracted.append(text)

    extracted.extend(REQUIRED_DO_NOT_DO)
    return _unique_keep_order(extracted)


def _get_position_multiplier(rules: dict[str, Any], mode: str) -> float | int | None:
    """
    Support both normalized internal keys and real YAML display keys.

    Examples:
    - risk_on
    - Risk-On
    - Mild Risk-On
    - mild_risk_on
    - Caution
    - Defensive
    """
    risk_modes = rules.get("risk_modes", {})
    if not isinstance(risk_modes, dict):
        return None

    normalized_mode = _normalize_mode_key(mode)
    candidate_keys = [
        mode,
        str(mode).strip(),
        normalized_mode,
        normalized_mode.replace("_", "-"),
        normalized_mode.replace("_", " ").title(),
        _display_mode_key(normalized_mode),
    ]

    for key in candidate_keys:
        if key in risk_modes and isinstance(risk_modes[key], dict):
            value = risk_modes[key].get("position_multiplier")
            if value is not None:
                return value

    for key, value in risk_modes.items():
        if not isinstance(value, dict):
            continue
        if _normalize_mode_key(str(key)) == normalized_mode:
            multiplier = value.get("position_multiplier")
            if multiplier is not None:
                return multiplier

    default_value = DEFAULT_RULES["risk_modes"].get(normalized_mode, {}).get("position_multiplier")
    return default_value


def _display_mode_key(normalized_mode: str) -> str:
    mapping = {
        "risk_on": "Risk-On",
        "mild_risk_on": "Mild Risk-On",
        "neutral": "Neutral",
        "caution": "Caution",
        "defensive": "Defensive",
    }
    return mapping.get(normalized_mode, normalized_mode)


def _normalize_events(events_merged: dict[str, Any] | list[dict[str, Any]] | None) -> dict[str, Any]:
    all_events: list[dict[str, Any]] = []

    if isinstance(events_merged, list):
        all_events.extend([x for x in events_merged if isinstance(x, dict)])
    elif isinstance(events_merged, dict):
        for key in [
            "events_today",
            "events_next_24h",
            "next_24h",
            "earnings_watchlist_7d",
            "manual_events",
            "events",
        ]:
            value = events_merged.get(key)
            if isinstance(value, list):
                all_events.extend([x for x in value if isinstance(x, dict)])

        flags = events_merged.get("risk_flags")
        if isinstance(flags, list):
            for flag in flags:
                all_events.append({"risk_flag": flag, "impact": "high"})

    high_impact_macro_today = False
    fomc_today = False
    fomc_minutes_today = False
    manual_event_high = False
    ticker_events: dict[str, list[str]] = {}

    today = date.today()

    for event in all_events:
        event_type = str(event.get("type") or "").lower()
        name = str(event.get("name") or event.get("event") or "").lower()
        impact = str(event.get("impact") or "").lower()
        risk_flag = str(event.get("risk_flag") or event.get("flag") or "").lower()
        ticker = str(event.get("ticker") or event.get("symbol") or "").upper().strip()

        # Determine whether this event falls on today (or has no date — undated
        # events are synthetic flags already filtered by add_event_risk_flags).
        event_date_str = str(event.get("date") or "")[:10]
        try:
            event_date: date | None = date.fromisoformat(event_date_str) if event_date_str else None
        except ValueError:
            event_date = None
        is_event_today = event_date is None or event_date == today

        is_high = impact == "high" or "high" in risk_flag
        is_macro = event_type in {"macro", "economic", "fomc"} or any(
            keyword in name
            for keyword in ["cpi", "ppi", "fomc", "pce", "gdp", "payroll", "employment"]
        )

        # *_today flags: only activate when the event is actually dated today
        if is_event_today and is_high and is_macro and (
            "today" in risk_flag
            or risk_flag in {"macro_high_today", "fomc_today", "fomc_minutes_today"}
            or not risk_flag
        ):
            high_impact_macro_today = True

        if is_event_today and (
            "fomc_today" in risk_flag
            or ("fomc" in name and "minutes" not in name and is_high)
        ):
            fomc_today = True

        if is_event_today and (
            "fomc_minutes_today" in risk_flag
            or ("fomc" in name and "minutes" in name)
        ):
            fomc_minutes_today = True

        if "manual" in str(event.get("source") or "").lower() and is_high:
            manual_event_high = True

        if risk_flag == "manual_event_high":
            manual_event_high = True

        if ticker:
            risk_text = _event_to_ticker_risk(event)
            ticker_events.setdefault(ticker, []).append(risk_text)

    return {
        "all_events": all_events,
        "high_impact_macro_today": high_impact_macro_today,
        "fomc_today": fomc_today,
        "fomc_minutes_today": fomc_minutes_today,
        "manual_event_high": manual_event_high,
        "ticker_events": {k: _unique_keep_order(v) for k, v in ticker_events.items()},
    }


def _event_to_ticker_risk(event: dict[str, Any]) -> str:
    name = str(event.get("name") or event.get("event") or "이벤트")
    risk_flag = str(event.get("risk_flag") or event.get("flag") or "")
    impact = str(event.get("impact") or "")

    if risk_flag:
        return f"{name}: {risk_flag} 플래그."
    if impact:
        return f"{name}: {impact} impact 이벤트."
    return f"{name}: 이벤트 리스크."


def _normalize_rankings(data: list[dict[str, Any]] | dict[str, Any] | None) -> list[dict[str, Any]]:
    if data is None:
        return []

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
                    copied = dict(item)
                    copied.setdefault("grade", grade)
                    rows.append(copied)

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


def _normalize_mode_key(mode: str) -> str:
    normalized = str(mode).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "risk_on": "risk_on",
        "mild_risk_on": "mild_risk_on",
        "neutral": "neutral",
        "caution": "caution",
        "defensive": "defensive",
    }
    return aliases.get(normalized, normalized)


def _detect_vix_rising(market_regime: dict[str, Any] | str | None) -> bool:
    if not isinstance(market_regime, dict):
        return False

    for key in ["vix_rising", "vix_up", "vix_is_rising"]:
        if key in market_regime:
            return _to_bool(market_regime.get(key))

    change = _to_float(
        market_regime.get("vix_change_pct")
        or market_regime.get("vix_pct_change")
        or market_regime.get("vix_change")
    )
    if change is not None and change > 0:
        return True

    evidence = _lower_join(
        _as_list(market_regime.get("negative_evidence"))
        + _as_list(market_regime.get("reasons"))
        + _as_list(market_regime.get("warnings"))
    )
    return "vix" in evidence and ("상승" in evidence or "급등" in evidence or "rising" in evidence)


def _detect_vix_spike(market_regime: dict[str, Any] | str | None) -> bool:
    if not isinstance(market_regime, dict):
        return False

    for key in ["vix_spike", "vix_surge"]:
        if key in market_regime:
            return _to_bool(market_regime.get(key))

    change = _to_float(
        market_regime.get("vix_change_pct")
        or market_regime.get("vix_pct_change")
        or market_regime.get("vix_change")
    )
    return change is not None and change >= 5.0


def _detect_qqq_spy_divergence(market_regime: dict[str, Any] | str | None) -> bool:
    if not isinstance(market_regime, dict):
        return False

    for key in ["qqq_spy_divergence", "qqq_spy_direction_mismatch"]:
        if key in market_regime:
            return _to_bool(market_regime.get(key))

    evidence = _lower_join(
        _as_list(market_regime.get("negative_evidence"))
        + _as_list(market_regime.get("warnings"))
    )
    return ("qqq" in evidence and "spy" in evidence) and (
        "불일치" in evidence or "divergence" in evidence or "mismatch" in evidence
    )


def _detect_smh_weak(market_regime: dict[str, Any] | str | None) -> bool:
    if not isinstance(market_regime, dict):
        return False

    for key in ["smh_weak", "semiconductor_weak"]:
        if key in market_regime:
            return _to_bool(market_regime.get(key))

    evidence = _lower_join(
        _as_list(market_regime.get("negative_evidence"))
        + _as_list(market_regime.get("warnings"))
    )
    return "smh" in evidence and ("약세" in evidence or "weak" in evidence)


def _detect_d_grade_only_strength(rankings: list[dict[str, Any]]) -> bool:
    strong_rows = []
    for row in rankings:
        signals = row.get("signals") if isinstance(row.get("signals"), dict) else {}
        is_strong = _to_bool(row.get("short_term_strength")) or _to_bool(signals.get("short_term_strength"))
        is_strong = is_strong or "급등" in _lower_join(row.get("positive_reasons"))
        if is_strong:
            strong_rows.append(row)

    if not strong_rows:
        return False

    return all(str(row.get("grade") or "").upper() == "D" for row in strong_rows)


def _count_grades(rankings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for row in rankings:
        grade = str(row.get("grade") or "").upper()
        if grade in counts:
            counts[grade] += 1
    return counts


def _extract_manual_note_tickers(notes: str, rankings: list[dict[str, Any]]) -> set[str]:
    upper_notes = notes.upper()
    tickers = {
        str(row.get("ticker") or row.get("symbol") or "").upper().strip()
        for row in rankings
    }
    return {ticker for ticker in tickers if ticker and ticker in upper_notes}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple) or isinstance(value, set):
        return list(value)
    return [value]


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    return normalized in {"true", "1", "yes", "y", "up", "rising", "positive"}


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _lower_join(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, list):
        return " ".join(str(x) for x in value).lower()
    return str(value).lower()


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