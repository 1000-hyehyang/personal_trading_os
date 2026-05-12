from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from setup_matcher import match_setups


SETUPS_CONFIG = {
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


def test_breakout_candidate_matches_required_and_preferred_signals():
    rankings = [
        {
            "ticker": "NVDA",
            "grade": "A",
            "score": 9,
            "signals": {
                "close_above_20dma": True,
                "close_above_50dma": True,
                "near_20d_high": True,
                "volume_above_20d_avg": True,
                "sector_strong": True,
                "relative_strength_vs_qqq_positive": True,
            },
        }
    ]

    result = match_setups(
        watchlist_rankings=rankings,
        market_regime={"mode": "Risk-On"},
        setups_config=SETUPS_CONFIG,
    )

    assert len(result["breakout"]) == 1
    assert result["breakout"][0]["ticker"] == "NVDA"
    assert "close_above_20dma" in result["breakout"][0]["matched_required"]
    assert "sector_strong" in result["breakout"][0]["matched_preferred"]
    assert result["pullback"] == []
    assert result["avoid"] == []


def test_pullback_candidate_matches_when_near_20dma_and_not_overheated():
    rankings = [
        {
            "ticker": "MSFT",
            "grade": "B",
            "score": 5,
            "signals": {
                "close_above_50dma": True,
                "price_near_20dma": True,
                "rsi_not_overheated": True,
                "sector_not_weak": True,
            },
        }
    ]

    result = match_setups(
        watchlist_rankings=rankings,
        market_regime={"mode": "Neutral"},
        setups_config=SETUPS_CONFIG,
    )

    assert result["breakout"] == []
    assert len(result["pullback"]) == 1
    assert result["pullback"][0]["ticker"] == "MSFT"
    assert "price_near_20dma" in result["pullback"][0]["matched_required"]
    assert result["avoid"] == []


def test_avoid_candidate_matches_required_any_close_below_50dma():
    rankings = [
        {
            "ticker": "TSLA",
            "grade": "D",
            "score": -1,
            "signals": {
                "close_below_50dma": True,
                "close_below_200dma": False,
            },
            "negative_reasons": ["50일선 아래"],
        }
    ]

    result = match_setups(
        watchlist_rankings=rankings,
        market_regime={"mode": "Risk-On"},
        setups_config=SETUPS_CONFIG,
    )

    assert result["breakout"] == []
    assert result["pullback"] == []
    assert len(result["avoid"]) == 1
    assert result["avoid"][0]["ticker"] == "TSLA"
    assert "close_below_50dma" in result["avoid"][0]["matched_required_any"]


def test_major_event_high_impact_forces_avoid_candidate():
    rankings = [
        {
            "ticker": "AAPL",
            "grade": "A",
            "score": 8,
            "signals": {
                "close_above_20dma": True,
                "close_above_50dma": True,
                "near_20d_high": True,
                "volume_above_20d_avg": True,
            },
            "event_flags": ["earnings_today"],
        }
    ]

    result = match_setups(
        watchlist_rankings=rankings,
        market_regime={"mode": "Risk-On"},
        setups_config=SETUPS_CONFIG,
    )

    assert result["breakout"] == []
    assert len(result["avoid"]) == 1
    assert result["avoid"][0]["ticker"] == "AAPL"
    assert "major_event_high_impact" in result["avoid"][0]["matched_required_any"]


def test_defensive_mode_blocks_breakout_and_pullback_candidates_and_adds_avoid_reason():
    rankings = [
        {
            "ticker": "NVDA",
            "grade": "A",
            "score": 9,
            "signals": {
                "close_above_20dma": True,
                "close_above_50dma": True,
                "near_20d_high": True,
                "volume_above_20d_avg": True,
                "sector_strong": True,
            },
        },
        {
            "ticker": "MSFT",
            "grade": "B",
            "score": 5,
            "signals": {
                "close_above_50dma": True,
                "price_near_20dma": True,
                "rsi_not_overheated": True,
            },
        },
    ]

    result = match_setups(
        watchlist_rankings=rankings,
        market_regime={"mode": "Defensive"},
        setups_config=SETUPS_CONFIG,
    )

    assert result["breakout"] == []
    assert result["pullback"] == []
    assert len(result["avoid"]) == 2
    assert {item["ticker"] for item in result["avoid"]} == {"NVDA", "MSFT"}
    assert any(
        "Defensive mode — no active setup" in item["reasons"]
        for item in result["avoid"]
    )


def test_matcher_can_infer_signals_from_numeric_fields():
    rankings = [
        {
            "ticker": "AVGO",
            "grade": "A",
            "score": 8,
            "close": 100,
            "dma20": 95,
            "dma50": 90,
            "high_20d": 101,
            "volume": 120,
            "avg_volume_20d": 100,
        }
    ]

    result = match_setups(
        watchlist_rankings=rankings,
        market_regime={"mode": "Mild Risk-On"},
        setups_config=SETUPS_CONFIG,
    )

    assert len(result["breakout"]) == 1
    assert result["breakout"][0]["ticker"] == "AVGO"


def test_reject_if_blocks_breakout_when_earnings_today_flag_exists():
    rankings = [
        {
            "ticker": "NVDA",
            "grade": "A",
            "score": 9,
            "signals": {
                "close_above_20dma": True,
                "close_above_50dma": True,
                "near_20d_high": True,
                "volume_above_20d_avg": True,
                "sector_strong": True,
            },
            "event_flags": ["earnings_today"],
        }
    ]

    result = match_setups(
        watchlist_rankings=rankings,
        market_regime={"mode": "Risk-On"},
        setups_config=SETUPS_CONFIG,
    )

    assert result["breakout"] == []
    assert len(result["avoid"]) == 1
    assert result["avoid"][0]["ticker"] == "NVDA"


def test_reject_if_blocks_breakout_when_vix_spike_exists():
    rankings = [
        {
            "ticker": "AMD",
            "grade": "A",
            "score": 8,
            "signals": {
                "close_above_20dma": True,
                "close_above_50dma": True,
                "near_20d_high": True,
                "volume_above_20d_avg": True,
            },
        }
    ]

    result = match_setups(
        watchlist_rankings=rankings,
        market_regime={"mode": "Risk-On", "vix_change_pct": 5.5},
        setups_config=SETUPS_CONFIG,
    )

    assert result["breakout"] == []
    assert result["avoid"] == []


def test_caution_mode_blocks_breakout_candidate_and_adds_avoid_reason():
    rankings = [
        {
            "ticker": "AVGO",
            "grade": "A",
            "score": 8,
            "signals": {
                "close_above_20dma": True,
                "close_above_50dma": True,
                "near_20d_high": True,
                "volume_above_20d_avg": True,
            },
        }
    ]

    result = match_setups(
        watchlist_rankings=rankings,
        market_regime={"mode": "Caution"},
        setups_config=SETUPS_CONFIG,
    )

    assert result["breakout"] == []
    assert len(result["avoid"]) == 1
    assert result["avoid"][0]["ticker"] == "AVGO"
    assert "Caution mode — breakout blocked" in result["avoid"][0]["reasons"]


def test_no_high_impact_event_today_signal_allows_custom_required_rule():
    custom_config = {
        "setups": {
            "breakout": {
                "description": "고영향 이벤트 없는 돌파 후보",
                "required": [
                    "close_above_20dma",
                    "close_above_50dma",
                    "near_20d_high",
                    "volume_above_20d_avg",
                    "no_high_impact_event_today",
                ],
                "reject_if": [
                    "high_impact_macro_today",
                ],
            },
            "pullback": SETUPS_CONFIG["setups"]["pullback"],
            "avoid": SETUPS_CONFIG["setups"]["avoid"],
        }
    }

    rankings = [
        {
            "ticker": "MSFT",
            "grade": "A",
            "score": 8,
            "signals": {
                "close_above_20dma": True,
                "close_above_50dma": True,
                "near_20d_high": True,
                "volume_above_20d_avg": True,
            },
            "event_flags": [],
        }
    ]

    result = match_setups(
        watchlist_rankings=rankings,
        market_regime={"mode": "Risk-On"},
        setups_config=custom_config,
    )

    assert len(result["breakout"]) == 1
    assert result["breakout"][0]["ticker"] == "MSFT"