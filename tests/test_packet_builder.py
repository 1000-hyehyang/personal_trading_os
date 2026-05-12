from __future__ import annotations

import json
from pathlib import Path

from src.packet_builder import (
    build_daily_packet,
    render_daily_packet_markdown,
    render_telegram_summary,
    save_daily_packet_outputs,
)
from src.prompt_builder import build_gpt_prompt, build_claude_prompt, save_prompt_outputs


def _sample_context() -> dict:
    return {
        "date": "2026-05-12",
        "session": "post_close",
        "timezone": "Asia/Seoul",
        "market_regime": {
            "mode": "Mild Risk-On",
            "score": 3,
            "event_overlay": "Caution",
            "summary": "기술주 흐름은 양호하지만 이벤트 리스크가 존재",
            "positive_evidence": ["SPY 20DMA 위", "QQQ 20DMA 위"],
            "negative_evidence": ["High-impact macro event today"],
        },
        "event_risk": {
            "today": [
                {
                    "type": "macro",
                    "name": "CPI",
                    "time_et": "08:30",
                    "impact": "high",
                    "source": "manual",
                }
            ],
            "next_24h": [],
            "earnings_within_7d": [
                {
                    "type": "earnings",
                    "ticker": "NVDA",
                    "date": "2026-05-15",
                    "impact": "high",
                    "risk_flag": "earnings_within_7d",
                }
            ],
            "manual_events": [
                {
                    "date": "2026-05-12",
                    "name": "수동 확인 이벤트",
                    "impact": "medium",
                }
            ],
        },
        "watchlist_ranking": [
            {
                "ticker": "NVDA",
                "grade": "A",
                "score": 8,
                "positive_reasons": ["20일선 위", "QQQ 대비 상대강도 우위"],
                "negative_reasons": ["어닝 7일 이내"],
                "event_flags": ["earnings_within_7d"],
            },
            {
                "ticker": "MSFT",
                "grade": "B",
                "score": 5,
                "positive_reasons": ["50일선 위"],
                "negative_reasons": [],
                "event_flags": [],
            },
            {
                "ticker": "TSLA",
                "grade": "D",
                "score": -1,
                "positive_reasons": [],
                "negative_reasons": ["50일선 아래"],
                "event_flags": [],
            },
        ],
        "setup_candidates": {
            "breakout": [{"ticker": "NVDA", "reason": "20일 고점 근처"}],
            "pullback": [{"ticker": "MSFT", "reason": "20일선 근처"}],
            "avoid": [{"ticker": "TSLA", "reason": "D급"}],
        },
        "risk": {
            "risk_warnings": [
                "High-impact macro event today: 발표 전후 신규 진입 주의",
                "D급 종목 물타기 금지",
            ],
            "do_not_do_list": [
                {"id": "no_chase", "text": "장초반 첫 5~15분 갭상승 종목 무근거 추격 금지"},
                {"id": "no_d_avg", "text": "D급 종목 물타기 금지"},
            ],
        },
        "manual_news_notes": "# Manual News Notes\n\n- NVDA: TradingView 뉴스 확인 필요",
        "data_quality": {
            "missing": ["FMP optional key"],
            "delayed": [],
            "fallback_used": ["manual events"],
        },
    }


def test_build_daily_packet_normalizes_required_sections() -> None:
    packet = build_daily_packet(_sample_context())

    assert packet["market_regime"]["mode"] == "Mild Risk-On"
    assert packet["market_regime"]["event_overlay"] == "Caution"
    assert packet["watchlist_ranking"]["A"][0]["ticker"] == "NVDA"
    assert packet["watchlist_ranking"]["B"][0]["ticker"] == "MSFT"
    assert packet["watchlist_ranking"]["D"][0]["ticker"] == "TSLA"
    assert "장초반 첫 5~15분 갭상승 종목 무근거 추격 금지" in packet["risk"]["do_not_do_list"]
    assert "D급 종목 물타기 금지" in packet["risk"]["do_not_do_list"]


def test_render_daily_packet_markdown_contains_spec_sections() -> None:
    packet = build_daily_packet(_sample_context())
    md = render_daily_packet_markdown(packet)

    assert "# Personal Trading OS Daily Packet" in md
    assert "## 1. Market Regime" in md
    assert "## 2. Event Risk" in md
    assert "## 3. Watchlist Ranking" in md
    assert "## 4. Setup Candidates" in md
    assert "## 5. Risk Warnings" in md
    assert "## 6. Today's Do-Not-Do List" in md
    assert "## 7. Manual News Notes" in md
    assert "## 8. Questions for GPT / Claude" in md
    assert "## 9. Data Quality Notes" in md
    assert "NVDA" in md
    assert "TSLA" in md


def test_render_telegram_summary_is_plain_text_and_short() -> None:
    packet = build_daily_packet(_sample_context())
    summary = render_telegram_summary(packet)

    assert "Personal Trading OS" in summary
    assert "시장 모드:" in summary
    assert "A급: NVDA" in summary
    assert "B급: MSFT" in summary
    assert "D급: TSLA" in summary
    assert "오늘 금지:" in summary
    assert "```" not in summary


def test_save_daily_packet_outputs_creates_files(tmp_path: Path) -> None:
    packet = build_daily_packet(_sample_context())
    paths = save_daily_packet_outputs(packet, output_dir=tmp_path)

    assert paths["daily_packet_md"].exists()
    assert paths["daily_packet_json"].exists()
    assert paths["telegram_summary"].exists()

    loaded = json.loads(paths["daily_packet_json"].read_text(encoding="utf-8"))
    assert loaded["market_regime"]["mode"] == "Mild Risk-On"


def test_prompt_builder_contains_required_guardrails() -> None:
    packet = build_daily_packet(_sample_context())

    gpt_prompt = build_gpt_prompt(packet)
    claude_prompt = build_claude_prompt(packet)

    assert "Daily Packet에 없는 숫자" in gpt_prompt
    assert "매수/매도 단정" in gpt_prompt
    assert "Bull Scenario" in gpt_prompt
    assert "Neutral Scenario" in gpt_prompt
    assert "Bear Scenario" in gpt_prompt
    assert "SAVE / TradingView" in gpt_prompt

    assert "과잉확신" in claude_prompt
    assert "데이터에 없는 추정" in claude_prompt
    assert "장초반 추격" in claude_prompt
    assert "반대 시나리오" in claude_prompt


def test_save_prompt_outputs_creates_prompt_files(tmp_path: Path) -> None:
    packet = build_daily_packet(_sample_context())
    paths = save_prompt_outputs(packet, output_dir=tmp_path)

    assert paths["prompt_for_gpt"].exists()
    assert paths["prompt_for_claude"].exists()

    assert "Today Trading Plan" in paths["prompt_for_gpt"].read_text(encoding="utf-8")
    assert "Claude Risk Review" in paths["prompt_for_claude"].read_text(encoding="utf-8")


def test_build_daily_packet_accepts_main_keyword_style(tmp_path: Path) -> None:
    manual_news = tmp_path / "manual_news_notes.md"
    manual_news.write_text(
        "# Manual News Notes\n\n"
        "## 2026-05-12\n\n"
        "- NVDA: TradingView 뉴스 확인 필요\n\n"
        "## 2026-05-11\n\n"
        "- OLD: 오래된 뉴스\n",
        encoding="utf-8",
    )

    packet = build_daily_packet(
        settings={
            "session": {
                "timezone_user": "Asia/Seoul",
            }
        },
        date="2026-05-12",
        session="post_close",
        market_regime={
            "mode": "Neutral",
            "score": 0,
            "event_overlay": "None",
            "summary": "키워드 인자 호환성 테스트",
        },
        rankings=[
            {
                "ticker": "NVDA",
                "grade": "A",
                "score": 8,
                "positive_reasons": ["20일선 위"],
                "negative_reasons": [],
                "event_flags": [],
            }
        ],
        setups={
            "breakout": [],
            "pullback": [],
            "avoid": [],
        },
        risk={
            "do_not_do_list": [
                {
                    "id": "no_chase",
                    "text": "장초반 첫 5~15분 갭상승 종목 무근거 추격 금지",
                    "severity": "high",
                }
            ]
        },
        data_quality={
            "fallback_used": [
                "TypeError: sample internal error message",
            ]
        },
        manual_news_path=manual_news,
    )

    assert packet["date"] == "2026-05-12"
    assert packet["session"] == "post_close"
    assert packet["timezone"] == "Asia/Seoul"
    assert packet["market_regime"]["mode"] == "Neutral"
    assert packet["watchlist_ranking"]["A"][0]["ticker"] == "NVDA"
    assert packet["risk"]["do_not_do_list"][0] == "장초반 첫 5~15분 갭상승 종목 무근거 추격 금지"
    assert "NVDA: TradingView 뉴스 확인 필요" in packet["manual_news_notes"]
    assert "OLD: 오래된 뉴스" not in packet["manual_news_notes"]
    assert packet["data_quality"]["fallback_used"][0] == "자동 수집 실패 — fallback 사용"