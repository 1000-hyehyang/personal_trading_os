from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _compact_packet_json(packet: dict[str, Any]) -> str:
    """
    Daily Packet dict를 사람이 읽기 쉬운 JSON 문자열로 변환한다.
    ensure_ascii=False를 사용해 한글이 깨지지 않도록 한다.
    """
    return json.dumps(packet, ensure_ascii=False, indent=2, default=str)


def _extract_grade_tickers(packet: dict[str, Any], grade: str) -> list[str]:
    """
    Daily Packet의 watchlist_ranking에서 특정 등급의 ticker 목록을 추출한다.
    """
    ranking = packet.get("watchlist_ranking", {})
    if not isinstance(ranking, dict):
        return []

    items = ranking.get(grade, [])
    if not isinstance(items, list):
        return []

    tickers: list[str] = []
    for item in items:
        if isinstance(item, dict):
            ticker = item.get("ticker") or item.get("symbol")
            if ticker:
                tickers.append(str(ticker))

    return tickers


def _extract_manual_news(packet: dict[str, Any]) -> str:
    """
    Daily Packet에 포함된 수동 뉴스 메모를 안전하게 추출한다.
    """
    text = str(packet.get("manual_news_notes", "")).strip()
    return text if text else "수동 뉴스 메모 없음"


def _join_or_none(items: list[str]) -> str:
    """
    ticker 목록을 쉼표로 연결한다. 비어 있으면 '없음'을 반환한다.
    """
    return ", ".join(items) if items else "없음"


def build_gpt_prompt(packet: dict[str, Any]) -> str:
    """
    ChatGPT Pro에 붙여넣을 트레이딩 플랜 생성용 프롬프트를 만든다.

    조건:
    - Daily Packet 기반 트레이딩 플랜 생성
    - 데이터에 없는 숫자/뉴스/날짜 생성 금지
    - 매수/매도 단정 금지
    - Bull / Neutral / Bear 시나리오 포함
    - 오늘 우선순위 종목과 피해야 할 종목 정리
    - SAVE/TradingView에서 확인할 뉴스 항목 표시
    """
    a_grade = _join_or_none(_extract_grade_tickers(packet, "A"))
    b_grade = _join_or_none(_extract_grade_tickers(packet, "B"))
    d_grade = _join_or_none(_extract_grade_tickers(packet, "D"))

    market_regime = packet.get("market_regime", {})
    if not isinstance(market_regime, dict):
        market_regime = {}

    packet_json = _compact_packet_json(packet)
    manual_news = _extract_manual_news(packet)

    return f"""너는 개인 미국 주식 트레이더를 위한 장전/장마감 트레이딩 플랜 보조자다.

아래 Daily Packet만 근거로 오늘의 트레이딩 플랜을 작성하라.

핵심 제한:
1. Daily Packet에 없는 숫자, 가격, 뉴스, 날짜, 이벤트, 기업 발표를 만들지 마라.
2. 매수/매도 단정 표현을 쓰지 마라.
3. 투자 조언처럼 표현하지 마라.
4. 확정적 예측 대신 조건부 시나리오로 작성하라.
5. 뉴스 자동 수집이 없는 MVP이므로 SAVE/TradingView에서 확인해야 할 항목을 별도로 표시하라.
6. 데이터가 부족한 항목은 "확인 필요"라고 표시하라.
7. 장초반 추격, D급 물타기, 이벤트 전후 과대 진입 위험을 반드시 점검하라.

현재 요약:
- Date: {packet.get("date", "N/A")}
- Session: {packet.get("session", "N/A")}
- Market Mode: {market_regime.get("mode", "Unknown")}
- Event Overlay: {market_regime.get("event_overlay", "None")}
- A급: {a_grade}
- B급: {b_grade}
- D급: {d_grade}

작성 형식:

# Today Trading Plan

## 1. 한 줄 결론
- 공격 / 중립 / 방어 중 어떤 운영에 가까운지 조건부로 요약

## 2. Market Context
- 시장 모드
- 이벤트 오버레이
- 긍정 근거
- 부정 근거
- 데이터 품질 한계

## 3. Bull Scenario
- 어떤 조건이면 리스크를 조금 더 허용할 수 있는지
- 확인해야 할 가격 행동과 섹터 흐름
- 단, 매수 지시 금지

## 4. Neutral Scenario
- 관망 또는 제한적 관찰 조건
- A/B급 종목을 어떻게 구분해서 볼지

## 5. Bear Scenario
- 어떤 조건이면 방어 모드로 전환해야 하는지
- D급, 이벤트 리스크, VIX/시장 모드 충돌을 강조

## 6. 오늘 우선순위 종목
- A급과 B급 중심
- 각 종목별로 "왜 볼지"와 "무엇을 확인할지"만 작성
- Daily Packet에 없는 뉴스나 수치 생성 금지

## 7. 오늘 피해야 할 종목 / 행동
- D급 종목
- Avoid 후보
- 이벤트 리스크 종목
- 장초반 추격 위험

## 8. SAVE / TradingView 확인 필요 뉴스
- 수동 뉴스 메모 기반
- 개별 티커 뉴스 확인 필요 항목
- 뉴스가 없으면 "확인 필요"로 표시

## 9. 실행 전 체크리스트
- 장초반 5~15분 추격 여부
- 손절 기준 존재 여부
- 이벤트 전후 과대 진입 여부
- D급 물타기 여부
- 시장 모드와 포지션 크기 일치 여부

아래는 Daily Packet 원문 JSON이다.

=== DAILY_PACKET_JSON_START ===
{packet_json}
=== DAILY_PACKET_JSON_END ===

수동 뉴스 메모:

=== MANUAL_NEWS_NOTES_START ===
{manual_news}
=== MANUAL_NEWS_NOTES_END ===
""".strip() + "\n"


def build_claude_prompt(packet: dict[str, Any]) -> str:
    """
    Claude Max에 붙여넣을 리스크 리뷰용 프롬프트를 만든다.

    조건:
    - GPT 리포트 또는 Daily Packet 리스크 리뷰
    - 과잉확신 탐지
    - 데이터에 없는 추정 탐지
    - 장초반 추격 위험 탐지
    - 반대 시나리오 제시
    """
    packet_json = _compact_packet_json(packet)

    return f"""너는 Personal Trading OS MVP의 리스크 리뷰어다.

목표:
- GPT가 작성한 트레이딩 플랜 또는 아래 Daily Packet 자체를 검토한다.
- 문체 개선이 아니라 리스크, 과잉확신, 근거 없는 추정, 장초반 추격 위험을 찾는다.
- 최종 매수/매도 판단을 하지 않는다.

검토 기준:
1. 데이터에 없는 숫자, 가격, 날짜, 뉴스, 이벤트, 기업 발표가 추가되었는가?
2. Daily Packet의 제한적 데이터가 과도하게 해석되었는가?
3. 매수/매도 단정 또는 투자 조언처럼 들리는 표현이 있는가?
4. Bull 시나리오만 강조하고 Neutral/Bear 시나리오가 약하지 않은가?
5. 시장 모드, 이벤트 오버레이, VIX/리스크 경고와 충돌하는 아이디어가 있는가?
6. 장초반 갭상승 추격 위험이 충분히 경고되었는가?
7. D급 종목 물타기 또는 반등 예측 위험이 남아 있는가?
8. 이벤트 전후 과대 진입 위험이 무시되었는가?
9. SAVE/TradingView에서 확인해야 할 뉴스 항목이 누락되었는가?
10. 반대 시나리오가 충분히 제시되었는가?

출력 형식:

# Claude Risk Review

## 1. 최종 판정
- 사용 가능 / 수정 필요 / 사용 보류 중 하나로 판정
- 이유를 3줄 이내로 요약

## 2. 과잉확신 탐지
- 확정적 표현
- 단정적 방향성 판단
- 근거보다 강한 결론

## 3. 데이터에 없는 추정 탐지
- Daily Packet에 없는 숫자/뉴스/날짜/이벤트
- 가격 움직임과 뉴스의 단정적 연결

## 4. 장초반 추격 위험
- 갭상승 추격 가능성
- 첫 5~15분 금지 행동 위반 가능성

## 5. 시장 모드 / 이벤트 리스크 충돌
- Market Mode와 제안된 행동의 충돌
- Event Overlay와 포지션 크기/공격성 충돌

## 6. 반대 시나리오
- Bull 아이디어가 틀릴 수 있는 조건
- Neutral 또는 Bear로 전환해야 할 조건

## 7. 보수적 체크리스트
- 실행 전 확인해야 할 항목
- SAVE/TradingView 확인 필요 항목
- 데이터 부족으로 확인 필요한 항목

## 8. 수정 권고 프롬프트
- GPT에게 다시 줄 수 있는 짧은 수정 지시문 작성

아래 Daily Packet만 기준으로 리뷰하라.
Daily Packet에 없는 사실은 "확인 불가"로 표시하라.

=== DAILY_PACKET_JSON_START ===
{packet_json}
=== DAILY_PACKET_JSON_END ===
""".strip() + "\n"


def save_prompt_outputs(
    packet: dict[str, Any],
    *,
    output_dir: str | Path = "output",
) -> dict[str, Path]:
    """
    GPT/Claude 프롬프트 파일을 output 폴더에 저장한다.

    생성 파일:
    - output/prompt_for_gpt.txt
    - output/prompt_for_claude.txt
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    gpt_prompt = build_gpt_prompt(packet)
    claude_prompt = build_claude_prompt(packet)

    paths = {
        "prompt_for_gpt": out / "prompt_for_gpt.txt",
        "prompt_for_claude": out / "prompt_for_claude.txt",
    }

    paths["prompt_for_gpt"].write_text(gpt_prompt, encoding="utf-8")
    paths["prompt_for_claude"].write_text(claude_prompt, encoding="utf-8")

    return paths


def build_and_save_prompts(
    packet: dict[str, Any],
    *,
    output_dir: str | Path = "output",
) -> dict[str, Path]:
    """
    외부 main.py에서 호출하기 쉬운 wrapper 함수.
    """
    return save_prompt_outputs(packet, output_dir=output_dir)


if __name__ == "__main__":
    sample_packet = {
        "date": "2026-05-12",
        "session": "post_close",
        "timezone": "Asia/Seoul",
        "generated_at": "2026-05-12T06:50:00+09:00",
        "market_regime": {
            "mode": "Neutral",
            "score": 0,
            "event_overlay": "None",
            "summary": "샘플 Daily Packet",
            "positive_evidence": [],
            "negative_evidence": [],
        },
        "event_risk": {
            "today": [],
            "next_24h": [],
            "watchlist_earnings_within_7d": [],
            "manual_events": [],
        },
        "watchlist_ranking": {
            "A": [],
            "B": [],
            "C": [],
            "D": [],
        },
        "setup_candidates": {
            "breakout": [],
            "pullback": [],
            "avoid": [],
        },
        "risk": {
            "risk_warnings": [],
            "do_not_do_list": [],
            "no_trade_flags": [],
            "ticker_specific_risks": [],
        },
        "manual_news_notes": "수동 뉴스 메모 없음",
        "questions": [],
        "data_quality": {
            "missing": [],
            "delayed": [],
            "fallback_used": [],
        },
    }

    save_prompt_outputs(sample_packet)
    print("Generated output/prompt_for_gpt.txt")
    print("Generated output/prompt_for_claude.txt")