"""
Phase 12 regression tests.

Covers the five fixes from the Phase 12-B review:
1. fetch_prices list[dict] format -> calculate_indicators_for_tickers
2. fallback_calculate_indicators produces 20DMA/50DMA/200DMA keys
3. positive_reasons flows through to fallback_render_daily_packet
4. Future-dated fomc_minutes_today flag is NOT activated today
5. manual_news_notes section 7 shows only today's date section
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ---------------------------------------------------------------------------
# Test 1 — H1: calculate_indicators_for_tickers accepts list[dict] format
# ---------------------------------------------------------------------------

def test_calculate_indicators_accepts_list_of_dicts():
    """fetch_prices returns dict[str, list[dict]]; indicators must not silently fail."""
    from indicators import calculate_indicators_for_tickers

    # Build a minimal list[dict] price series (60 rows so MAs are meaningful)
    rows = []
    for i in range(60):
        rows.append({
            "date": f"2026-0{(i // 30) + 3}-{(i % 30) + 1:02d}",
            "open": 100.0 + i * 0.1,
            "high": 101.0 + i * 0.1,
            "low": 99.0 + i * 0.1,
            "close": 100.0 + i * 0.1,
            "volume": 1_000_000,
        })

    price_data = {"AAPL": rows}
    indicators, notes = calculate_indicators_for_tickers(price_data)

    assert "AAPL" in indicators, f"AAPL missing from indicators; notes={notes}"
    snap = indicators["AAPL"]
    assert snap.get("20DMA") is not None, "20DMA should be computed"
    assert snap.get("50DMA") is not None, "50DMA should be computed"
    assert snap.get("close") is not None, "close should be present"

    # No calculation errors
    calc_errors = [n for n in notes if "AAPL" in n and "failed" in n]
    assert not calc_errors, f"Unexpected errors: {calc_errors}"


# ---------------------------------------------------------------------------
# Test 2 — H2: fallback_calculate_indicators outputs canonical MA key names
# ---------------------------------------------------------------------------

def test_fallback_calculate_indicators_has_canonical_ma_keys():
    """fallback_calculate_indicators must output 20DMA/50DMA/200DMA."""
    from main import fallback_calculate_indicators

    rows = []
    for i in range(210):
        rows.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "close": 200.0 + i * 0.05,
            "volume": 500_000,
        })

    result = fallback_calculate_indicators({"SPY": rows})

    assert "SPY" in result, "SPY should be in fallback result"
    snap = result["SPY"]
    assert "20DMA" in snap, f"20DMA missing; keys={list(snap.keys())}"
    assert "50DMA" in snap, f"50DMA missing; keys={list(snap.keys())}"
    assert "200DMA" in snap, f"200DMA missing; keys={list(snap.keys())}"
    assert snap["20DMA"] is not None, "20DMA must not be None"
    assert snap["50DMA"] is not None, "50DMA must not be None"
    assert snap["200DMA"] is not None, "200DMA must not be None"


# ---------------------------------------------------------------------------
# Test 3 — H3: positive_reasons appear in fallback_render_daily_packet output
# ---------------------------------------------------------------------------

def test_fallback_render_shows_positive_reasons():
    """market_regime returns positive_reasons; daily packet must not show '없음'."""
    from main import fallback_render_daily_packet

    payload = {
        "date": "2026-05-14",
        "session": "post_close",
        "generated_at": "2026-05-14T20:00:00",
        "market_regime": {
            "mode": "Risk-On",
            "score": 5,
            "event_overlay": "None",
            "summary": "Risk-On / score 5",
            "positive_reasons": ["QQQ가 SPY보다 5일 상대강도 우위", "VIX 전일 대비 하락"],
            "negative_reasons": [],
        },
        "events": {},
        "watchlist_ranking": [],
        "setup_candidates": {},
        "risk": {"do_not_do_list": [], "risk_warnings": [], "no_trade_flags": []},
        "manual_news_notes": "",
        "data_quality_notes": [],
        "step_results": {},
    }

    output = fallback_render_daily_packet(payload)

    assert "QQQ가 SPY보다 5일 상대강도 우위" in output, (
        "positive_reasons should appear in daily packet"
    )
    assert "없음" not in output.split("### Positive Evidence")[1].split("###")[0], (
        "Positive Evidence section must not show '없음' when reasons exist"
    )


# ---------------------------------------------------------------------------
# Test 4 — H4: future-dated fomc_minutes event does NOT fire today's warning
# ---------------------------------------------------------------------------

def test_future_fomc_minutes_does_not_fire_today():
    """FOMC Minutes event dated 7 days from now must not set fomc_minutes_today."""
    from risk_engine import _normalize_events

    future_date = (date.today() + timedelta(days=7)).isoformat()

    events_merged = {
        "events": [
            {
                "date": future_date,
                "type": "fed",
                "name": "FOMC Minutes 확인",
                "impact": "high",
                "risk_flags": ["fomc_minutes_today"],
            }
        ],
        "events_today": [],
        "events_next_24h": [],
        "manual_events": [],
        "risk_flags": [],
    }

    result = _normalize_events(events_merged)

    assert result["fomc_minutes_today"] is False, (
        f"fomc_minutes_today must be False for future event; got {result['fomc_minutes_today']}"
    )
    assert result["fomc_today"] is False, (
        f"fomc_today must be False for future event; got {result['fomc_today']}"
    )


def test_today_fomc_minutes_does_fire():
    """FOMC Minutes event dated today MUST set fomc_minutes_today."""
    from risk_engine import _normalize_events

    today_str = date.today().isoformat()

    events_merged = {
        "events": [
            {
                "date": today_str,
                "type": "fed",
                "name": "FOMC Minutes 확인",
                "impact": "high",
                "risk_flags": ["fomc_minutes_today"],
            }
        ],
        "events_today": [],
        "events_next_24h": [],
        "manual_events": [],
        "risk_flags": [],
    }

    result = _normalize_events(events_merged)

    assert result["fomc_minutes_today"] is True, (
        f"fomc_minutes_today must be True for today's event; got {result['fomc_minutes_today']}"
    )


# ---------------------------------------------------------------------------
# Test 5 — M2: Section 7 shows only today's date section from manual_news_notes
# ---------------------------------------------------------------------------

def test_section7_date_filtered():
    """fallback_render_daily_packet Section 7 must show only today's notes."""
    from main import fallback_render_daily_packet

    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    manual_notes = f"""## {yesterday_str}
어제 메모입니다.

## {today_str}
오늘 메모입니다. 반도체 강세.

## 2026-01-01
오래된 메모.
"""

    payload = {
        "date": today_str,
        "session": "post_close",
        "generated_at": f"{today_str}T20:00:00",
        "market_regime": {
            "mode": "Neutral",
            "score": 0,
            "event_overlay": "None",
            "summary": "Neutral / score 0",
            "positive_reasons": [],
            "negative_reasons": [],
        },
        "events": {},
        "watchlist_ranking": [],
        "setup_candidates": {},
        "risk": {"do_not_do_list": [], "risk_warnings": [], "no_trade_flags": []},
        "manual_news_notes": manual_notes,
        "data_quality_notes": [],
        "step_results": {},
    }

    output = fallback_render_daily_packet(payload)

    section7_start = output.find("## 7. Manual News Notes")
    section7_end = output.find("## 8.", section7_start)
    section7 = output[section7_start:section7_end]

    assert "오늘 메모입니다. 반도체 강세." in section7, (
        "Today's notes must appear in Section 7"
    )
    assert "어제 메모입니다." not in section7, (
        "Yesterday's notes must NOT appear in Section 7"
    )
    assert "오래된 메모." not in section7, (
        "Old notes must NOT appear in Section 7"
    )


def test_section7_no_today_section_shows_fallback():
    """If no today section in manual_news_notes, Section 7 shows fallback message."""
    from main import fallback_render_daily_packet

    today_str = date.today().isoformat()

    manual_notes = """## 2020-01-01
오래된 메모만 있음.
"""

    payload = {
        "date": today_str,
        "session": "post_close",
        "generated_at": f"{today_str}T20:00:00",
        "market_regime": {
            "mode": "Neutral",
            "score": 0,
            "event_overlay": "None",
            "summary": "Neutral / score 0",
            "positive_reasons": [],
            "negative_reasons": [],
        },
        "events": {},
        "watchlist_ranking": [],
        "setup_candidates": {},
        "risk": {"do_not_do_list": [], "risk_warnings": [], "no_trade_flags": []},
        "manual_news_notes": manual_notes,
        "data_quality_notes": [],
        "step_results": {},
    }

    output = fallback_render_daily_packet(payload)

    section7_start = output.find("## 7. Manual News Notes")
    section7_end = output.find("## 8.", section7_start)
    section7 = output[section7_start:section7_end]

    assert "오늘 수동 뉴스 메모 없음" in section7, (
        "Fallback message should appear when no today section exists"
    )
    assert "오래된 메모만 있음." not in section7, (
        "Old notes must NOT appear in Section 7"
    )
