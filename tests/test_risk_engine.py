from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from risk_engine import REQUIRED_DO_NOT_DO, load_rules_config, run_risk_engine


RULES_CONFIG = {
    "global_do_not_do": REQUIRED_DO_NOT_DO,
    "risk_modes": {
        "risk_on": {"position_multiplier": 1.0},
        "mild_risk_on": {"position_multiplier": 0.8},
        "neutral": {"position_multiplier": 0.6},
        "caution": {"position_multiplier": 0.4},
        "defensive": {"position_multiplier": 0.2},
    },
}


def test_do_not_do_list_always_contains_required_7_rules():
    result = run_risk_engine(
        market_regime={"mode": "Risk-On"},
        watchlist_ranker_result=[],
        events_merged={},
        rules_config=RULES_CONFIG,
        manual_news_notes="",
    )

    for rule in REQUIRED_DO_NOT_DO:
        assert rule in result["do_not_do_list"]

    assert len(result["do_not_do_list"]) >= 7


def test_caution_mode_generates_warning_and_uses_position_multiplier():
    result = run_risk_engine(
        market_regime={"mode": "Caution"},
        watchlist_ranker_result=[
            {"ticker": "NVDA", "grade": "A", "score": 8},
        ],
        events_merged={},
        rules_config=RULES_CONFIG,
        manual_news_notes="",
    )

    joined = " ".join(result["risk_warnings"])
    assert "Caution/Defensive" in joined
    assert result["risk_context"]["position_multiplier"] == 0.4


def test_defensive_mode_sets_no_trade_flag_and_no_trade_bias_when_combined_with_vix_spike():
    result = run_risk_engine(
        market_regime={
            "mode": "Defensive",
            "vix_change_pct": 7.0,
        },
        watchlist_ranker_result=[
            {"ticker": "MSFT", "grade": "A", "score": 8},
        ],
        events_merged={},
        rules_config=RULES_CONFIG,
        manual_news_notes="",
    )

    assert "Defensive mode" in result["no_trade_flags"]
    assert "VIX spike or sharp VIX rise" in result["no_trade_flags"]
    assert result["no_trade_bias"] is True


def test_high_impact_macro_event_generates_warning_and_no_trade_flag():
    events_merged = {
        "events_today": [
            {
                "type": "macro",
                "name": "Consumer Price Index",
                "impact": "high",
                "risk_flag": "macro_high_today",
            }
        ]
    }

    result = run_risk_engine(
        market_regime={"mode": "Neutral"},
        watchlist_ranker_result=[
            {"ticker": "AAPL", "grade": "B", "score": 5},
        ],
        events_merged=events_merged,
        rules_config=RULES_CONFIG,
        manual_news_notes="",
    )

    assert "High-impact macro event today" in result["no_trade_flags"]
    assert any("High-impact macro event today" in warning for warning in result["risk_warnings"])


def test_d_grade_ticker_gets_specific_risk():
    result = run_risk_engine(
        market_regime={"mode": "Risk-On"},
        watchlist_ranker_result=[
            {
                "ticker": "TSLA",
                "grade": "D",
                "score": -1,
                "negative_reasons": ["50일선 아래", "거래량 동반 하락"],
            }
        ],
        events_merged={},
        rules_config=RULES_CONFIG,
        manual_news_notes="",
    )

    assert "TSLA" in result["ticker_specific_risks"]
    joined = " ".join(result["ticker_specific_risks"]["TSLA"])
    assert "D급 종목" in joined
    assert "50일선 아래" in joined
    assert any("D급 종목" in warning for warning in result["risk_warnings"])


def test_vix_rising_flags_high_beta_ticker_position_expansion_risk():
    result = run_risk_engine(
        market_regime={
            "mode": "Neutral",
            "vix_change_pct": 2.5,
        },
        watchlist_ranker_result=[
            {"ticker": "COIN", "grade": "B", "score": 5},
            {"ticker": "MSFT", "grade": "A", "score": 8},
        ],
        events_merged={},
        rules_config=RULES_CONFIG,
        manual_news_notes="",
    )

    assert "COIN" in result["ticker_specific_risks"]
    assert any("고베타 종목" in risk for risk in result["ticker_specific_risks"]["COIN"])
    assert "MSFT" not in result["ticker_specific_risks"]


def test_earnings_within_7d_event_flag_adds_ticker_specific_risk():
    result = run_risk_engine(
        market_regime={"mode": "Risk-On"},
        watchlist_ranker_result=[
            {
                "ticker": "NVDA",
                "grade": "A",
                "score": 9,
                "event_flags": ["earnings_within_7d"],
            }
        ],
        events_merged={},
        rules_config=RULES_CONFIG,
        manual_news_notes="",
    )

    assert "NVDA" in result["ticker_specific_risks"]
    assert any("어닝 7일 이내" in risk for risk in result["ticker_specific_risks"]["NVDA"])


def test_events_merged_ticker_event_adds_ticker_specific_risk():
    events_merged = {
        "earnings_watchlist_7d": [
            {
                "type": "earnings",
                "ticker": "AMD",
                "name": "AMD Earnings",
                "impact": "high",
                "risk_flag": "earnings_within_7d",
            }
        ]
    }

    result = run_risk_engine(
        market_regime={"mode": "Risk-On"},
        watchlist_ranker_result=[
            {"ticker": "AMD", "grade": "A", "score": 8},
        ],
        events_merged=events_merged,
        rules_config=RULES_CONFIG,
        manual_news_notes="",
    )

    assert "AMD" in result["ticker_specific_risks"]
    assert any("earnings_within_7d" in risk for risk in result["ticker_specific_risks"]["AMD"])


def test_manual_news_notes_add_warning_and_ticker_specific_risk():
    result = run_risk_engine(
        market_regime={"mode": "Risk-On"},
        watchlist_ranker_result=[
            {"ticker": "NVDA", "grade": "A", "score": 8},
            {"ticker": "MSFT", "grade": "A", "score": 8},
        ],
        events_merged={},
        rules_config=RULES_CONFIG,
        manual_news_notes="- NVDA: TradingView 뉴스에서 실적 관련 변동성 확대 가능성 확인",
    )

    assert result["risk_context"]["manual_news_notes_present"] is True
    assert any("manual_news_notes.md" in warning for warning in result["risk_warnings"])
    assert "NVDA" in result["ticker_specific_risks"]
    assert "MSFT" not in result["ticker_specific_risks"]


def test_majority_cd_grade_sets_no_trade_flag():
    result = run_risk_engine(
        market_regime={"mode": "Neutral"},
        watchlist_ranker_result=[
            {"ticker": "A", "grade": "A", "score": 8},
            {"ticker": "B", "grade": "C", "score": 2},
            {"ticker": "C", "grade": "D", "score": 0},
            {"ticker": "D", "grade": "D", "score": -1},
        ],
        events_merged={},
        rules_config=RULES_CONFIG,
        manual_news_notes="",
    )

    assert "Majority of watchlist is C/D grade" in result["no_trade_flags"]


def test_load_rules_config_supports_dict_global_do_not_do_and_extracts_text(tmp_path):
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        """
global_do_not_do:
  - id: no_gap_chase
    text: "장초반 첫 5~15분 갭상승 종목 무근거 추격 금지"
    severity: high
  - id: no_dca_d_grade
    text: "D급 종목 물타기 금지"
    severity: high

risk_modes:
  Risk-On:
    position_multiplier: 1.0
  Mild Risk-On:
    position_multiplier: 0.8
  Neutral:
    position_multiplier: 0.6
  Caution:
    position_multiplier: 0.4
  Defensive:
    position_multiplier: 0.2
""",
        encoding="utf-8",
    )

    rules = load_rules_config(rules_path)
    result = run_risk_engine(
        market_regime={"mode": "Risk-On"},
        watchlist_ranker_result=[],
        events_merged={},
        rules_config=rules,
        manual_news_notes="",
    )

    assert any("장초반 첫 5~15분" in item for item in result["do_not_do_list"])
    assert all(not item.startswith("{") for item in result["do_not_do_list"])


def test_load_rules_config_supports_display_mode_keys_for_caution_multiplier(tmp_path):
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(
        """
global_do_not_do:
  - id: no_gap_chase
    text: "장초반 첫 5~15분 갭상승 종목 무근거 추격 금지"
    severity: high

risk_modes:
  Risk-On:
    position_multiplier: 1.0
  Mild Risk-On:
    position_multiplier: 0.8
  Neutral:
    position_multiplier: 0.6
  Caution:
    position_multiplier: 0.4
  Defensive:
    position_multiplier: 0.2
""",
        encoding="utf-8",
    )

    rules = load_rules_config(rules_path)
    result = run_risk_engine(
        market_regime={"mode": "Caution"},
        watchlist_ranker_result=[],
        events_merged={},
        rules_config=rules,
        manual_news_notes="",
    )

    assert result["risk_context"]["position_multiplier"] == 0.4