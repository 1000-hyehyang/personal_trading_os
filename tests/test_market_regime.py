import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from market_regime import determine_market_regime, load_events_merged


def test_mild_risk_on_with_caution_overlay_from_events_today():
    indicators = {
        "SPY": {
            "close": 510,
            "dma_20": 500,
            "dma_50": 490,
            "return_5d": 1.0,
        },
        "QQQ": {
            "close": 450,
            "dma_20": 440,
            "dma_50": 430,
            "return_5d": 2.0,
        },
        "IWM": {
            "close": 210,
            "dma_20": 205,
            "dma_50": 200,
            "return_5d": 0.5,
        },
        "SMH": {
            "close": 250,
            "dma_20": 245,
            "dma_50": 240,
            "return_5d": 3.0,
        },
        "HYG": {
            "close": 80,
            "dma_20": 79,
            "return_5d": 0.2,
        },
        "TLT": {
            "close": 94,
            "dma_20": 95,
            "return_5d": -0.5,
        },
        "^VIX": {
            "close": 14,
            "dma_20": 15,
            "change_pct": -2.0,
        },
    }

    events = {
        "date": "2026-05-12",
        "events_today": [
            {
                "type": "macro",
                "name": "Consumer Price Index",
                "impact": "high",
                "risk_flag": "macro_high_today",
            }
        ],
    }

    result = determine_market_regime(
        indicators,
        events,
        as_of_date="2026-05-12",
    )

    assert result["mode"] == "Risk-On"
    assert result["score"] >= 5
    assert result["event_overlay"] == "Caution"
    assert "SPY가 20일선 위" in result["positive_reasons"]
    assert "QQQ가 SPY보다 5일 상대강도 우위" in result["positive_reasons"]


def test_defensive_when_major_indexes_break_50dma_and_vix_spikes():
    indicators = {
        "SPY": {
            "close": 480,
            "dma_20": 500,
            "dma_50": 495,
            "return_5d": -2.0,
        },
        "QQQ": {
            "close": 420,
            "dma_20": 440,
            "dma_50": 435,
            "return_5d": -3.0,
        },
        "IWM": {
            "close": 190,
            "dma_20": 200,
            "dma_50": 205,
            "return_5d": -5.0,
        },
        "SMH": {
            "close": 220,
            "dma_20": 240,
            "dma_50": 245,
            "return_5d": -4.0,
        },
        "HYG": {
            "close": 76,
            "dma_20": 79,
            "return_5d": -1.0,
        },
        "TLT": {
            "close": 91,
            "dma_20": 95,
            "return_5d": -2.0,
        },
        "^VIX": {
            "close": 24,
            "dma_20": 18,
            "change_pct": 8.0,
        },
    }

    result = determine_market_regime(indicators, events={}, as_of_date="2026-05-12")

    assert result["mode"] in {"Caution", "Defensive"}
    assert result["score"] <= -4
    assert any("SPY가 50일선 아래" in x for x in result["negative_reasons"])
    assert any("QQQ가 50일선 아래" in x for x in result["negative_reasons"])
    assert any("VIX가 전일 대비 5% 이상 상승" in x for x in result["negative_reasons"])
    assert any("VIX가 20일선 위" in x for x in result["negative_reasons"])


def test_dataframe_input_with_ticker_column():
    df = pd.DataFrame(
        [
            {
                "ticker": "SPY",
                "close": 510,
                "dma_20": 500,
                "dma_50": 490,
                "return_5d": 1.0,
            },
            {
                "ticker": "QQQ",
                "close": 450,
                "dma_20": 440,
                "dma_50": 430,
                "return_5d": 2.0,
            },
            {
                "ticker": "IWM",
                "close": 210,
                "dma_20": 205,
                "dma_50": 200,
                "return_5d": 0.5,
            },
            {
                "ticker": "SMH",
                "close": 250,
                "dma_20": 245,
                "dma_50": 240,
                "return_5d": 3.0,
            },
            {
                "ticker": "HYG",
                "close": 80,
                "dma_20": 79,
                "return_5d": 0.2,
            },
            {
                "ticker": "TLT",
                "close": 96,
                "dma_20": 95,
                "return_5d": 0.5,
            },
            {
                "ticker": "^VIX",
                "close": 14,
                "dma_20": 15,
                "change_pct": -1.0,
            },
        ]
    )

    result = determine_market_regime(df, events={}, as_of_date="2026-05-12")

    assert isinstance(result, dict)
    assert result["mode"] in {
        "Risk-On",
        "Mild Risk-On",
        "Neutral",
        "Caution",
        "Defensive",
    }
    assert result["score"] >= 5
    assert result["event_overlay"] is None


def test_missing_data_does_not_fail_entire_module():
    indicators = {
        "SPY": {
            "close": 510,
            "dma_20": 500,
            # dma_50 intentionally missing
        },
        "^VIX": {
            "close": 14,
            # dma_20 and change_pct intentionally missing
        },
    }

    result = determine_market_regime(indicators, events=None, as_of_date="2026-05-12")

    assert isinstance(result, dict)
    assert "mode" in result
    assert "score" in result
    assert isinstance(result["data_quality_notes"], list)
    assert len(result["data_quality_notes"]) > 0
    assert any("QQQ" in note for note in result["data_quality_notes"])


def test_event_overlay_from_flags_dict():
    indicators = {
        "SPY": {"close": 510, "dma_20": 500, "dma_50": 490, "return_5d": 1.0},
        "QQQ": {"close": 450, "dma_20": 440, "dma_50": 430, "return_5d": 2.0},
        "IWM": {"close": 210, "dma_20": 205, "dma_50": 200, "return_5d": 0.5},
        "SMH": {"close": 250, "dma_20": 245, "dma_50": 240, "return_5d": 3.0},
        "HYG": {"close": 80, "dma_20": 79, "return_5d": 0.2},
        "TLT": {"close": 96, "dma_20": 95, "return_5d": 0.5},
        "^VIX": {"close": 14, "dma_20": 15, "change_pct": -1.0},
    }

    events = {
        "date": "2026-05-12",
        "risk_flags": {
            "macro_high_today": True,
        },
    }

    result = determine_market_regime(indicators, events, as_of_date="2026-05-12")

    assert result["event_overlay"] == "Caution"


def test_load_events_merged_missing_file_does_not_crash(tmp_path):
    missing_path = tmp_path / "events_merged.json"

    data = load_events_merged(missing_path)

    assert isinstance(data, dict)
    assert "_data_quality_notes" in data
    assert "not found" in data["_data_quality_notes"][0]


def test_load_events_merged_valid_json(tmp_path):
    events_path = tmp_path / "events_merged.json"
    payload = {
        "date": "2026-05-12",
        "event_flags": ["macro_high_today"],
    }

    events_path.write_text(json.dumps(payload), encoding="utf-8")

    data = load_events_merged(events_path)

    assert data["date"] == "2026-05-12"
    assert data["event_flags"] == ["macro_high_today"]