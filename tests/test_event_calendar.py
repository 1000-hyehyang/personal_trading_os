# tests/test_event_calendar.py

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import event_calendar  # noqa: E402


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def test_assign_event_impact_high_macro_keywords() -> None:
    event = {
        "date": "2026-05-14",
        "time_et": "08:30",
        "type": "macro",
        "name": "Consumer Price Index",
        "impact": "low",
        "source": "BLS",
    }

    result = event_calendar.assign_event_impact(event)

    assert result["impact"] == "high"


def test_assign_event_impact_medium_macro_keywords() -> None:
    event = {
        "date": "2026-05-14",
        "time_et": "10:00",
        "type": "macro",
        "name": "JOLTS Job Openings",
        "impact": "low",
        "source": "BLS",
    }

    result = event_calendar.assign_event_impact(event)

    assert result["impact"] == "medium"


def test_assign_event_impact_mega_cap_earnings_high() -> None:
    event = {
        "date": "2026-05-20",
        "type": "earnings",
        "ticker": "NVDA",
        "name": "NVDA Earnings",
        "impact": "medium",
        "source": "Alpha Vantage",
    }

    result = event_calendar.assign_event_impact(event)

    assert result["impact"] == "high"


def test_filter_relevant_events_keeps_watchlist_earnings_only() -> None:
    events = [
        {
            "date": "2026-05-20",
            "type": "earnings",
            "ticker": "NVDA",
            "name": "NVDA Earnings",
            "impact": "medium",
            "source": "Alpha Vantage",
        },
        {
            "date": "2026-05-20",
            "type": "earnings",
            "ticker": "ZZZZ",
            "name": "ZZZZ Earnings",
            "impact": "medium",
            "source": "Alpha Vantage",
        },
        {
            "date": "2026-05-21",
            "type": "macro",
            "name": "FOMC Minutes",
            "impact": "high",
            "source": "Federal Reserve",
        },
    ]

    filtered = event_calendar.filter_relevant_events(
        events,
        watchlist=["NVDA"],
        start_date=date(2026, 5, 12),
        end_date=date(2026, 6, 12),
    )

    tickers = [event.get("ticker") for event in filtered if event["type"] == "earnings"]
    names = [event["name"] for event in filtered]

    assert tickers == ["NVDA"]
    assert "FOMC Minutes" in names


def test_merge_auto_and_manual_events_manual_wins() -> None:
    auto_events = [
        {
            "date": "2026-05-14",
            "time_et": "08:30",
            "type": "macro",
            "name": "Consumer Price Index",
            "impact": "medium",
            "source": "FMP",
            "note": "auto",
        }
    ]
    manual_events = [
        {
            "date": "2026-05-14",
            "time_et": "08:30",
            "type": "macro",
            "name": "Consumer Price Index",
            "impact": "high",
            "source": "manual",
            "note": "manual override",
            "manual": True,
        }
    ]

    merged = event_calendar.merge_auto_and_manual_events(auto_events, manual_events)

    assert len(merged) == 1
    assert merged[0]["source"] == "manual"
    assert merged[0]["note"] == "manual override"
    assert merged[0]["impact"] == "high"


def test_create_event_risk_flags() -> None:
    events = [
        {
            "date": "2026-05-12",
            "time_et": "08:30",
            "type": "macro",
            "name": "Consumer Price Index",
            "impact": "high",
            "source": "BLS",
        },
        {
            "date": "2026-05-15",
            "type": "earnings",
            "ticker": "NVDA",
            "name": "NVDA Earnings",
            "impact": "high",
            "source": "Alpha Vantage",
        },
        {
            "date": "2026-05-13",
            "type": "earnings",
            "ticker": "AMD",
            "name": "AMD Earnings",
            "impact": "medium",
            "source": "Alpha Vantage",
        },
    ]

    flags = event_calendar.create_event_risk_flags(
        events,
        current_date=date(2026, 5, 12),
        earnings_window_days=7,
    )

    assert flags["macro_high_today"] is True
    assert flags["macro_high_next_24h"] is True
    assert "AMD" in flags["earnings_tomorrow"]

    earnings_tickers = {item["ticker"] for item in flags["earnings_within_7d"]}
    assert earnings_tickers == {"AMD", "NVDA"}

    enriched = flags["events_enriched"]
    nvda = next(event for event in enriched if event.get("ticker") == "NVDA")
    assert nvda["earnings_within_7d"] is True
    assert nvda["risk_flag"] == "earnings_within_7d"


def test_load_watchlist(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "config" / "watchlist.yaml",
        {
            "market_core": ["SPY", "QQQ"],
            "watchlist": ["nvda", "AMD", "NVDA"],
        },
    )

    result = event_calendar.load_watchlist(tmp_path)

    assert result == ["AMD", "NVDA"]


def test_load_manual_events(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "config" / "events_manual.yaml",
        {
            "manual_events": [
                {
                    "date": "2026-05-14",
                    "time_et": "08:30",
                    "type": "macro",
                    "name": "CPI 세부 항목 확인",
                    "impact": "high",
                    "note": "core/shelter 확인",
                }
            ]
        },
    )

    events = event_calendar.load_manual_events(tmp_path)

    assert len(events) == 1
    assert events[0]["source"] == "manual"
    assert events[0]["manual"] is True
    assert events[0]["impact"] == "high"


# 추가 케이스 1: H-4 tickers 복수 필드 처리
def test_load_manual_events_multiple_tickers_uses_first_and_logs_note(
    tmp_path: Path,
) -> None:
    write_yaml(
        tmp_path / "config" / "events_manual.yaml",
        {
            "manual_events": [
                {
                    "date": "2026-05-14",
                    "time_et": "after_close",
                    "type": "company",
                    "tickers": ["NVDA", "AMD", "AVGO"],
                    "name": "반도체 수동 이벤트",
                    "impact": "medium",
                    "note": "복수 티커 중 첫 번째만 사용",
                }
            ]
        },
    )

    events = event_calendar.load_manual_events(tmp_path)

    assert len(events) == 1
    assert events[0]["ticker"] == "NVDA"
    assert events[0]["time_et"] == "after_close"

    assert (
        "events_manual.yaml: 반도체 수동 이벤트 has multiple tickers; only first used."
        in event_calendar.MANUAL_EVENT_DATA_QUALITY_NOTES
    )


# 추가 케이스 2: M-1 fed type 이벤트가 macro_high_today에 반영되는지
def test_fed_type_event_sets_macro_high_today() -> None:
    events = [
        {
            "date": "2026-05-12",
            "time_et": "14:00",
            "type": "fed",
            "name": "FOMC Rate Decision",
            "impact": "high",
            "source": "Federal Reserve",
        }
    ]

    flags = event_calendar.create_event_risk_flags(
        events,
        current_date=date(2026, 5, 12),
        earnings_window_days=7,
    )

    assert flags["macro_high_today"] is True
    assert flags["macro_high_next_24h"] is True
    assert flags["fomc_today"] is True

    enriched = flags["events_enriched"]
    assert "macro_high_today" in enriched[0]["event_flags"]


# 추가 케이스 3: M-3 after_close / before_open 시간 정렬
def test_sort_events_before_open_and_after_close_order() -> None:
    events = [
        {
            "date": "2026-05-12",
            "time_et": "after_close",
            "type": "earnings",
            "ticker": "NVDA",
            "name": "NVDA Earnings",
            "impact": "high",
            "source": "manual",
        },
        {
            "date": "2026-05-12",
            "time_et": "08:30",
            "type": "macro",
            "name": "Consumer Price Index",
            "impact": "high",
            "source": "BLS",
        },
        {
            "date": "2026-05-12",
            "time_et": "before_open",
            "type": "earnings",
            "ticker": "AMD",
            "name": "AMD Earnings",
            "impact": "medium",
            "source": "manual",
        },
        {
            "date": "2026-05-12",
            "time_et": "manual",
            "type": "manual",
            "name": "Manual Review",
            "impact": "low",
            "source": "manual",
        },
    ]

    sorted_events = event_calendar.sort_events(events)

    assert sorted_events[0]["time_et"] == "before_open"
    assert sorted_events[1]["time_et"] == "08:30"
    assert sorted_events[2]["time_et"] == "after_close"
    assert sorted_events[3]["time_et"] == "manual"


def test_run_event_calendar_with_mock_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_yaml(
        tmp_path / "config" / "watchlist.yaml",
        {
            "watchlist": ["NVDA", "AMD"],
        },
    )
    write_yaml(
        tmp_path / "config" / "settings.yaml",
        {
            "events": {
                "lookahead_days": 30,
                "earnings_risk_window_days": 7,
            }
        },
    )
    write_yaml(
        tmp_path / "config" / "events_manual.yaml",
        {
            "manual_events": [
                {
                    "date": "2026-05-12",
                    "time_et": "08:30",
                    "type": "macro",
                    "name": "수동 CPI 세부 항목 확인",
                    "impact": "high",
                    "note": "manual test",
                }
            ]
        },
    )

    class DummyResult:
        def __init__(self, events, notes=None, status=None):
            self.events = events
            self.data_quality_notes = notes or []
            self.source_status = status or {}

    def fake_fetch_alpha(*args, **kwargs):
        return DummyResult(
            [
                {
                    "date": "2026-05-15",
                    "type": "earnings",
                    "ticker": "NVDA",
                    "name": "NVDA Earnings",
                    "impact": "medium",
                    "source": "Alpha Vantage",
                },
                {
                    "date": "2026-05-15",
                    "type": "earnings",
                    "ticker": "ZZZZ",
                    "name": "ZZZZ Earnings",
                    "impact": "medium",
                    "source": "Alpha Vantage",
                },
            ],
            status={"alpha_vantage_earnings": "ok"},
        )

    def fake_fetch_fmp(*args, **kwargs):
        return DummyResult(
            [
                {
                    "date": "2026-05-12",
                    "time_et": "08:30",
                    "type": "macro",
                    "name": "Consumer Price Index",
                    "impact": "high",
                    "source": "FMP",
                }
            ],
            status={"fmp_economic_calendar": "ok"},
        )

    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "test-alpha")
    monkeypatch.setenv("FMP_API_KEY", "test-fmp")
    monkeypatch.setattr(event_calendar, "fetch_alpha_vantage_earnings", fake_fetch_alpha)
    monkeypatch.setattr(event_calendar, "fetch_fmp_economic_calendar", fake_fetch_fmp)

    result = event_calendar.run_event_calendar(
        project_root=tmp_path,
        current_date=date(2026, 5, 12),
    )

    auto_path = Path(result["events_auto_path"])
    merged_path = Path(result["events_merged_path"])

    assert auto_path.exists()
    assert merged_path.exists()

    auto_payload = json.loads(auto_path.read_text(encoding="utf-8"))
    merged_payload = json.loads(merged_path.read_text(encoding="utf-8"))

    auto_tickers = {
        event.get("ticker")
        for event in auto_payload["events"]
        if event.get("type") == "earnings"
    }

    assert auto_tickers == {"NVDA"}
    assert auto_payload["risk_flags"]["macro_high_today"] is True

    merged_names = {event["name"] for event in merged_payload["events"]}
    assert "수동 CPI 세부 항목 확인" in merged_names
    assert merged_payload["risk_flags"]["manual_event_high"] is True


def test_load_watchlist_categorized_dict_structure(tmp_path: Path) -> None:
    write_yaml(
        tmp_path / "config" / "watchlist.yaml",
        {
            "watchlist": {
                "mega_cap_tech": ["MSFT", "AAPL", "GOOGL"],
                "semiconductors": ["NVDA", "AMD", "AVGO"],
                "high_beta_growth": ["PLTR", "COIN"],
                "space_and_speculative": ["RKLB", "ASTS"],
            }
        },
    )

    result = event_calendar.load_watchlist(tmp_path)

    assert result == [
        "AAPL",
        "AMD",
        "ASTS",
        "AVGO",
        "COIN",
        "GOOGL",
        "MSFT",
        "NVDA",
        "PLTR",
        "RKLB",
    ]