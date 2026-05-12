from __future__ import annotations

"""
변경 요약:
1. Do-Not-Do List dict repr 버그 수정
   - _safe_text() 추가
   - _normalize_risk()에서 do_not_do_list를 반드시 str list로 정규화
   - render_daily_packet_markdown(), render_telegram_summary() 모두 안전 출력 적용

2. Manual News Notes 날짜 필터링 추가
   - _read_manual_news_notes()가 파일 전체를 읽지 않고 오늘 날짜의 "## YYYY-MM-DD" 섹션만 반환
   - 해당 날짜 섹션이 없으면 "오늘 수동 뉴스 메모 없음" 반환

3. Data Quality Notes 사용자 친화화
   - _clean_data_quality_message() 추가
   - TypeError:, Exception:, Traceback 포함 메시지를 "자동 수집 실패 — fallback 사용"으로 대체
   - 200자 초과 메시지는 truncate
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DO_NOT_DO = [
    "장초반 첫 5~15분 갭상승 종목 무근거 추격 금지",
    "D급 종목 물타기 금지",
    "손절가 없는 진입 금지",
    "VIX 상승 중 고베타 종목 포지션 확대 금지",
    "CPI/FOMC/대형 실적 전후 과대 진입 금지",
    "시장 모드 Caution/Defensive에서 신규 공격 매매 금지",
    "뉴스 하나만 보고 차트·섹터 확인 없이 진입 금지",
]

DEFAULT_QUESTIONS = [
    "오늘 시장 모드와 이벤트 리스크를 고려할 때 공격/방어 중 어느 쪽에 가까운가?",
    "A/B급 종목 중 실제로 SAVE 또는 TradingView에서 추가 확인할 우선순위는 무엇인가?",
    "D급 또는 이벤트 리스크 종목에서 피해야 할 행동은 무엇인가?",
]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _today_str() -> str:
    return datetime.now().astimezone().date().isoformat()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _safe_text(item: Any) -> str:
    """
    dict/list/None 등이 그대로 repr로 출력되는 문제를 방지한다.
    특히 do_not_do_list가 {"id": ..., "text": ..., "severity": ...} 형태일 때 text만 출력한다.
    """
    if item is None:
        return ""

    if isinstance(item, dict):
        value = item.get("text") or item.get("rule") or item.get("name") or item.get("message")
        if value is not None and str(value).strip():
            return str(value).strip()
        return str(item).strip()

    return str(item).strip()


def _clean_text(value: Any, default: str = "N/A") -> str:
    text = _safe_text(value)
    return text if text else default


def _first_present(mapping: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, "", []):
            return mapping[key]
    return default


def _clean_data_quality_message(text: str) -> str:
    """
    사용자에게 그대로 노출하기 부적절한 기술 예외 메시지를 정리한다.
    """
    cleaned = str(text).strip()

    if not cleaned:
        return ""

    technical_prefixes = (
        "TypeError:",
        "Exception:",
        "Traceback",
        "ValueError:",
        "KeyError:",
        "RuntimeError:",
        "ConnectionError:",
        "TimeoutError:",
        "JSONDecodeError:",
    )

    if cleaned.startswith(technical_prefixes) or "Traceback (most recent call last)" in cleaned:
        return "자동 수집 실패 — fallback 사용"

    if len(cleaned) > 200:
        return cleaned[:197].rstrip() + "..."

    return cleaned


def _normalize_reason_list(value: Any) -> list[str]:
    items = _as_list(value)
    normalized: list[str] = []

    for item in items:
        text = _safe_text(item)
        if text:
            normalized.append(text)

    return normalized


def _normalize_data_quality_list(value: Any) -> list[str]:
    items = _normalize_reason_list(value)
    cleaned: list[str] = []

    for item in items:
        message = _clean_data_quality_message(item)
        if message and message not in cleaned:
            cleaned.append(message)

    return cleaned


def _format_bullet_items(items: list[Any], empty_text: str = "없음") -> str:
    if not items:
        return f"- {empty_text}"

    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            lines.append(f"- {_format_dict_short(item)}")
        else:
            text = _safe_text(item)
            lines.append(f"- {text if text else empty_text}")
    return "\n".join(lines)


def _format_numbered_items(items: list[Any], empty_text: str = "없음") -> str:
    if not items:
        return f"1. {empty_text}"

    lines: list[str] = []
    for idx, item in enumerate(items, start=1):
        text = _safe_text(item)
        if not text:
            text = empty_text
        lines.append(f"{idx}. {text}")
    return "\n".join(lines)


def _format_dict_short(item: dict[str, Any]) -> str:
    ticker = item.get("ticker")
    name = item.get("name") or item.get("title")
    date = item.get("date")
    time_et = item.get("time_et") or item.get("time")
    impact = item.get("impact")
    flag = item.get("risk_flag") or item.get("flag")
    note = item.get("note") or item.get("summary") or item.get("description")

    parts: list[str] = []

    if ticker:
        parts.append(str(ticker))
    if name:
        parts.append(str(name))
    if date:
        parts.append(str(date))
    if time_et:
        parts.append(f"{time_et} ET")
    if impact:
        parts.append(f"impact={impact}")
    if flag:
        parts.append(f"flag={flag}")
    if note:
        parts.append(str(note))

    if parts:
        return " | ".join(parts)

    text = _safe_text(item)
    return text if text else json.dumps(item, ensure_ascii=False, default=str)


def _normalize_market_regime(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}

    mode = _first_present(raw, ["mode", "market_mode", "regime"], "Unknown")
    score = _first_present(raw, ["score", "market_score"], "N/A")
    event_overlay = _first_present(raw, ["event_overlay", "overlay"], "None")
    summary = _first_present(raw, ["summary", "reason", "description"], "시장 모드 요약 없음")

    positive = _normalize_reason_list(
        _first_present(raw, ["positive_evidence", "positive_reasons", "positives"], [])
    )
    negative = _normalize_reason_list(
        _first_present(raw, ["negative_evidence", "negative_reasons", "negatives"], [])
    )

    return {
        "mode": _clean_text(mode),
        "score": score,
        "event_overlay": _clean_text(event_overlay, "None"),
        "summary": _clean_text(summary, "시장 모드 요약 없음"),
        "positive_evidence": positive,
        "negative_evidence": negative,
    }


def _normalize_events(raw: Any) -> dict[str, list[Any]]:
    if not isinstance(raw, dict):
        raw = {}

    today = _first_present(raw, ["today", "events_today"], [])
    next_24h = _first_present(raw, ["next_24h", "events_next_24h"], [])
    earnings = _first_present(
        raw,
        [
            "earnings_watchlist_7d",
            "watchlist_earnings_7d",
            "watchlist_earnings_within_7d",
            "earnings_within_7d",
            "earnings",
        ],
        [],
    )
    manual = _first_present(raw, ["manual_events", "manual"], [])

    return {
        "today": _as_list(today),
        "next_24h": _as_list(next_24h),
        "watchlist_earnings_within_7d": _as_list(earnings),
        "manual_events": _as_list(manual),
    }


def _normalize_ranking(raw: Any) -> dict[str, list[dict[str, Any]]]:
    items = _as_list(raw)
    grouped: dict[str, list[dict[str, Any]]] = {"A": [], "B": [], "C": [], "D": []}

    for item in items:
        if isinstance(item, str):
            normalized = {
                "ticker": item,
                "grade": "C",
                "score": "N/A",
                "positive_reasons": [],
                "negative_reasons": [],
                "event_flags": [],
            }
        elif isinstance(item, dict):
            grade = str(item.get("grade", "C")).upper().strip()
            if grade not in grouped:
                grade = "C"

            normalized = {
                "ticker": _clean_text(item.get("ticker") or item.get("symbol"), "UNKNOWN"),
                "grade": grade,
                "score": item.get("score", "N/A"),
                "positive_reasons": _normalize_reason_list(
                    item.get("positive_reasons") or item.get("positives") or []
                ),
                "negative_reasons": _normalize_reason_list(
                    item.get("negative_reasons") or item.get("negatives") or []
                ),
                "event_flags": _normalize_reason_list(item.get("event_flags") or item.get("flags") or []),
            }
        else:
            continue

        grouped[normalized["grade"]].append(normalized)

    for grade in grouped:
        grouped[grade].sort(key=lambda x: _safe_sort_score(x.get("score")), reverse=True)

    return grouped


def _safe_sort_score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -9999.0


def _normalize_setups(raw: Any) -> dict[str, list[Any]]:
    if not isinstance(raw, dict):
        raw = {}

    return {
        "breakout": _as_list(raw.get("breakout", [])),
        "pullback": _as_list(raw.get("pullback", [])),
        "avoid": _as_list(raw.get("avoid", [])),
    }


def _normalize_risk(raw: Any) -> dict[str, list[Any]]:
    if not isinstance(raw, dict):
        raw = {}

    warnings = _first_present(raw, ["risk_warnings", "warnings"], [])
    do_not_do = _first_present(raw, ["do_not_do_list", "do_not_do", "global_do_not_do"], DEFAULT_DO_NOT_DO)

    cleaned_do_not_do: list[str] = []
    for item in _as_list(do_not_do):
        text = _safe_text(item)
        if text and text not in cleaned_do_not_do:
            cleaned_do_not_do.append(text)

    for required in DEFAULT_DO_NOT_DO:
        if required not in cleaned_do_not_do:
            cleaned_do_not_do.append(required)

    return {
        "risk_warnings": _as_list(warnings),
        "do_not_do_list": cleaned_do_not_do,
        "no_trade_flags": _as_list(raw.get("no_trade_flags", [])),
        "ticker_specific_risks": _as_list(raw.get("ticker_specific_risks", [])),
    }


def _normalize_data_quality(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        raw = {}

    return {
        "missing": _normalize_data_quality_list(raw.get("missing", [])),
        "delayed": _normalize_data_quality_list(raw.get("delayed", [])),
        "fallback_used": _normalize_data_quality_list(raw.get("fallback_used", [])),
    }


def _extract_dated_markdown_section(text: str, target_date: str) -> str:
    """
    manual_news_notes.md에서 특정 날짜 섹션만 추출한다.

    지원 형식:
    ## 2026-05-12
    ### 2026-05-12

    다음 ## 또는 ### 날짜/섹션 헤더가 나오기 전까지를 해당 섹션으로 본다.
    """
    if not text.strip():
        return ""

    lines = text.splitlines()
    start_index: int | None = None

    header_pattern = re.compile(r"^(#{2,6})\s+" + re.escape(target_date) + r"\s*$")
    any_section_pattern = re.compile(r"^#{2,6}\s+\S+")

    for idx, line in enumerate(lines):
        if header_pattern.match(line.strip()):
            start_index = idx + 1
            break

    if start_index is None:
        return ""

    collected: list[str] = []
    for line in lines[start_index:]:
        stripped = line.strip()

        if any_section_pattern.match(stripped):
            break

        collected.append(line)

    result = "\n".join(collected).strip()
    return result


def _read_manual_news_notes(path: str | Path, target_date: str | None = None) -> str:
    """
    manual_news_notes.md 전체가 아니라 target_date 섹션만 읽는다.
    target_date가 없으면 오늘 날짜를 사용한다.
    """
    p = Path(path)
    if not p.exists():
        return "오늘 수동 뉴스 메모 없음"

    text = p.read_text(encoding="utf-8").strip()
    if not text:
        return "오늘 수동 뉴스 메모 없음"

    date_to_find = target_date or _today_str()
    section = _extract_dated_markdown_section(text, date_to_find)

    if not section:
        return "오늘 수동 뉴스 메모 없음"

    return section


def _format_ranking_item(item: dict[str, Any]) -> str:
    ticker = item.get("ticker", "UNKNOWN")
    score = item.get("score", "N/A")

    reasons: list[str] = []
    positive = item.get("positive_reasons", [])
    negative = item.get("negative_reasons", [])
    flags = item.get("event_flags", [])

    if positive:
        reasons.append("긍정: " + ", ".join(map(str, positive)))
    if negative:
        reasons.append("부정: " + ", ".join(map(str, negative)))
    if flags:
        reasons.append("이벤트: " + ", ".join(map(str, flags)))

    detail = " / ".join(reasons) if reasons else "세부 사유 없음"
    return f"{ticker} | score={score} | {detail}"


def _format_ranking_section(items: list[dict[str, Any]], empty_text: str) -> str:
    if not items:
        return f"- {empty_text}"
    return "\n".join(f"- {_format_ranking_item(item)}" for item in items)


def build_daily_packet(
    context: dict[str, Any] | None = None,
    *,
    session: str = "post_close",
    manual_news_path: str | Path = "data/manual_news_notes.md",
    generated_at: str | None = None,
    settings: dict[str, Any] | None = None,
    date: str | None = None,
    timezone: str | None = None,
    timezone_user: str | None = None,
    market_regime: Any = None,
    event_risk: Any = None,
    events: Any = None,
    watchlist_ranking: Any = None,
    rankings: Any = None,
    watchlist_rankings: Any = None,
    setup_candidates: Any = None,
    setups: Any = None,
    risk: Any = None,
    risk_engine: Any = None,
    data_quality: Any = None,
    questions: Any = None,
    manual_news_notes: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """
    Daily Packet dict를 생성한다.

    main.py가 context dict 방식으로 호출해도 되고,
    build_daily_packet(settings=..., market_regime=..., rankings=...)처럼
    keyword argument 방식으로 호출해도 동작하도록 호환성을 보장한다.

    지원 입력:
    - context dict
    - settings
    - market_regime
    - event_risk or events
    - watchlist_ranking or rankings or watchlist_rankings
    - setup_candidates or setups
    - risk or risk_engine
    - data_quality
    - questions
    - manual_news_notes
    """

    merged: dict[str, Any] = {}

    if context:
        if not isinstance(context, dict):
            raise TypeError("context must be a dict or None")
        merged.update(context)

    explicit_values = {
        "settings": settings,
        "date": date,
        "timezone": timezone,
        "timezone_user": timezone_user,
        "market_regime": market_regime,
        "event_risk": event_risk,
        "events": events,
        "watchlist_ranking": watchlist_ranking,
        "rankings": rankings,
        "watchlist_rankings": watchlist_rankings,
        "setup_candidates": setup_candidates,
        "setups": setups,
        "risk": risk,
        "risk_engine": risk_engine,
        "data_quality": data_quality,
        "questions": questions,
        "manual_news_notes": manual_news_notes,
    }

    for key, value in explicit_values.items():
        if value is not None:
            merged[key] = value

    for key, value in extra.items():
        if value is not None:
            merged[key] = value

    alias_map = {
        "market_regime_result": "market_regime",
        "regime_result": "market_regime",
        "event_risk_result": "event_risk",
        "events_merged": "event_risk",
        "merged_events": "event_risk",
        "ranking_result": "watchlist_ranking",
        "ranked_watchlist": "watchlist_ranking",
        "watchlist_result": "watchlist_ranking",
        "setup_result": "setup_candidates",
        "setup_matches": "setup_candidates",
        "risk_result": "risk",
        "risk_output": "risk",
        "risk_engine_result": "risk",
    }

    for alias_key, target_key in alias_map.items():
        if target_key not in merged and alias_key in merged:
            merged[target_key] = merged[alias_key]

    settings_dict = merged.get("settings", {})
    if not isinstance(settings_dict, dict):
        settings_dict = {}

    settings_session = settings_dict.get("session", {})
    if not isinstance(settings_session, dict):
        settings_session = {}

    packet_date = str(merged.get("date") or _today_str())

    context_session = merged.get("session")
    if isinstance(context_session, str) and context_session.strip():
        resolved_session = context_session.strip()
    else:
        resolved_session = session

    resolved_timezone = (
        merged.get("timezone")
        or merged.get("timezone_user")
        or settings_session.get("timezone_user")
        or "Asia/Seoul"
    )

    market_regime_payload = _normalize_market_regime(merged.get("market_regime", {}))

    event_risk_payload = _normalize_events(
        merged.get("event_risk") or merged.get("events") or {}
    )

    ranking_raw = (
        merged.get("watchlist_ranking")
        or merged.get("rankings")
        or merged.get("watchlist_rankings")
        or []
    )
    watchlist_ranking_payload = _normalize_ranking(ranking_raw)

    setup_candidates_payload = _normalize_setups(
        merged.get("setup_candidates") or merged.get("setups") or {}
    )

    risk_payload = _normalize_risk(
        merged.get("risk") or merged.get("risk_engine") or {}
    )

    data_quality_payload = _normalize_data_quality(
        merged.get("data_quality", {})
    )

    manual_news_payload = merged.get("manual_news_notes")
    if manual_news_payload is None:
        manual_news_payload = _read_manual_news_notes(
            manual_news_path,
            target_date=packet_date,
        )

    questions_payload = _normalize_reason_list(
        merged.get("questions") or DEFAULT_QUESTIONS
    )
    if not questions_payload:
        questions_payload = DEFAULT_QUESTIONS.copy()

    packet = {
        "date": packet_date,
        "session": resolved_session,
        "timezone": str(resolved_timezone),
        "generated_at": generated_at or merged.get("generated_at") or _now_iso(),
        "market_regime": market_regime_payload,
        "event_risk": event_risk_payload,
        "watchlist_ranking": watchlist_ranking_payload,
        "setup_candidates": setup_candidates_payload,
        "risk": risk_payload,
        "manual_news_notes": str(manual_news_payload).strip() or "오늘 수동 뉴스 메모 없음",
        "questions": questions_payload,
        "data_quality": data_quality_payload,
    }

    return packet


def render_daily_packet_markdown(packet: dict[str, Any]) -> str:
    market = packet["market_regime"]
    events = packet["event_risk"]
    ranking = packet["watchlist_ranking"]
    setups = packet["setup_candidates"]
    risk = packet["risk"]
    dq = packet["data_quality"]

    md = f"""# Personal Trading OS Daily Packet

Date: {packet.get("date", "N/A")}
Session: {packet.get("session", "N/A")}
Timezone: {packet.get("timezone", "N/A")}
Generated At: {packet.get("generated_at", "N/A")}

## 1. Market Regime

- Mode: {market.get("mode", "Unknown")}
- Score: {market.get("score", "N/A")}
- Event Overlay: {market.get("event_overlay", "None")}
- Summary: {market.get("summary", "시장 모드 요약 없음")}

### Positive Evidence
{_format_bullet_items(market.get("positive_evidence", []), "긍정 근거 없음")}

### Negative Evidence
{_format_bullet_items(market.get("negative_evidence", []), "부정 근거 없음")}

## 2. Event Risk

### Today
{_format_bullet_items(events.get("today", []), "오늘 표시할 이벤트 없음")}

### Next 24 Hours
{_format_bullet_items(events.get("next_24h", []), "향후 24시간 이벤트 없음")}

### Watchlist Earnings Within 7 Days
{_format_bullet_items(events.get("watchlist_earnings_within_7d", []), "관심종목 7일 이내 어닝 없음")}

### Manual Events
{_format_bullet_items(events.get("manual_events", []), "수동 이벤트 없음")}

## 3. Watchlist Ranking

### A Grade - Priority Watch
{_format_ranking_section(ranking.get("A", []), "A급 종목 없음")}

### B Grade - Secondary Watch
{_format_ranking_section(ranking.get("B", []), "B급 종목 없음")}

### C Grade - Wait
{_format_ranking_section(ranking.get("C", []), "C급 종목 없음")}

### D Grade - Avoid / Risk
{_format_ranking_section(ranking.get("D", []), "D급 종목 없음")}

## 4. Setup Candidates

### Breakout
{_format_bullet_items(setups.get("breakout", []), "Breakout 후보 없음")}

### Pullback
{_format_bullet_items(setups.get("pullback", []), "Pullback 후보 없음")}

### Avoid
{_format_bullet_items(setups.get("avoid", []), "Avoid 후보 없음")}

## 5. Risk Warnings

{_format_bullet_items(risk.get("risk_warnings", []), "리스크 경고 없음")}

## 6. Today's Do-Not-Do List

{_format_numbered_items(risk.get("do_not_do_list", []), "금지 행동 없음")}

## 7. Manual News Notes

{packet.get("manual_news_notes", "오늘 수동 뉴스 메모 없음")}

## 8. Questions for GPT / Claude

{_format_numbered_items(packet.get("questions", []), "질문 없음")}

## 9. Data Quality Notes

- Missing: {", ".join(dq.get("missing", [])) if dq.get("missing") else "없음"}
- Delayed: {", ".join(dq.get("delayed", [])) if dq.get("delayed") else "없음"}
- Fallback Used: {", ".join(dq.get("fallback_used", [])) if dq.get("fallback_used") else "없음"}
"""
    return md.strip() + "\n"


def _tickers_by_grade(packet: dict[str, Any], grade: str, max_items: int = 10) -> str:
    items = packet.get("watchlist_ranking", {}).get(grade, [])
    tickers = [str(item.get("ticker", "UNKNOWN")) for item in items[:max_items]]
    return ", ".join(tickers) if tickers else "없음"


def _event_summary(packet: dict[str, Any], max_items: int = 5) -> list[str]:
    events = packet.get("event_risk", {})
    combined = []
    combined.extend(events.get("today", []))
    combined.extend(events.get("next_24h", []))
    combined.extend(events.get("watchlist_earnings_within_7d", []))

    lines: list[str] = []
    for item in combined[:max_items]:
        if isinstance(item, dict):
            lines.append(_format_dict_short(item))
        else:
            text = _safe_text(item)
            if text:
                lines.append(text)

    return lines


def render_telegram_summary(packet: dict[str, Any]) -> str:
    market = packet.get("market_regime", {})
    risk = packet.get("risk", {})

    event_lines = _event_summary(packet)
    if not event_lines:
        event_lines = ["없음"]

    raw_do_not_do = risk.get("do_not_do_list", [])[:4]
    do_not_do = [_safe_text(item) for item in raw_do_not_do]
    do_not_do = [item for item in do_not_do if item]

    if not do_not_do:
        do_not_do = DEFAULT_DO_NOT_DO[:4]

    lines = [
        "Personal Trading OS",
        "",
        f"Date: {packet.get('date', 'N/A')}",
        f"Session: {packet.get('session', 'N/A')}",
        "",
        "시장 모드:",
        f"- {market.get('mode', 'Unknown')}",
        f"- Event Overlay: {market.get('event_overlay', 'None')}",
        "",
        "관심종목 요약:",
        f"- A급: {_tickers_by_grade(packet, 'A')}",
        f"- B급: {_tickers_by_grade(packet, 'B')}",
        f"- D급: {_tickers_by_grade(packet, 'D')}",
        "",
        "이벤트:",
    ]

    lines.extend(f"- {line}" for line in event_lines)

    lines.extend(
        [
            "",
            "오늘 금지:",
        ]
    )
    lines.extend(f"{idx}. {item}" for idx, item in enumerate(do_not_do, start=1))

    lines.extend(
        [
            "",
            "첨부:",
            "- daily_packet.md",
            "- prompt_for_gpt.txt",
            "- prompt_for_claude.txt",
        ]
    )

    return "\n".join(lines).strip() + "\n"


def save_daily_packet_outputs(
    packet: dict[str, Any],
    *,
    output_dir: str | Path = "output",
) -> dict[str, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    md_text = render_daily_packet_markdown(packet)
    telegram_text = render_telegram_summary(packet)

    paths = {
        "daily_packet_md": out / "daily_packet.md",
        "daily_packet_json": out / "daily_packet.json",
        "telegram_summary": out / "telegram_summary.txt",
    }

    paths["daily_packet_md"].write_text(md_text, encoding="utf-8")
    paths["daily_packet_json"].write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    paths["telegram_summary"].write_text(telegram_text, encoding="utf-8")

    return paths


def build_and_save_daily_packet(
    context: dict[str, Any] | None = None,
    *,
    session: str = "post_close",
    manual_news_path: str | Path = "data/manual_news_notes.md",
    output_dir: str | Path = "output",
) -> dict[str, Any]:
    packet = build_daily_packet(
        context,
        session=session,
        manual_news_path=manual_news_path,
    )
    save_daily_packet_outputs(packet, output_dir=output_dir)
    return packet


if __name__ == "__main__":
    sample_packet = build_and_save_daily_packet(
        {
            "market_regime": {
                "mode": "Neutral",
                "score": 0,
                "event_overlay": "None",
                "summary": "샘플 실행",
            },
            "watchlist_ranking": [],
            "setup_candidates": {},
            "risk": {},
            "data_quality": {"fallback_used": ["packet_builder sample mode"]},
        }
    )
    print(render_telegram_summary(sample_packet))