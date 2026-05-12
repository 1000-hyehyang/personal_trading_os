from datetime import date

from src.watchlist_ranker import (
    flatten_events,
    group_rankings_by_grade,
    load_watchlist_from_yaml,
    rank_watchlist,
    score_to_grade,
)


def test_score_to_grade():
    assert score_to_grade(8) == "A"
    assert score_to_grade(7) == "A"
    assert score_to_grade(6) == "B"
    assert score_to_grade(4) == "B"
    assert score_to_grade(3) == "C"
    assert score_to_grade(1) == "C"
    assert score_to_grade(0) == "D"
    assert score_to_grade(-3) == "D"


def test_a_grade_full_positive_signals_without_events():
    indicators = {
        "NVDA": {
            "close": 100,
            "prev_close": 99,
            "dma20": 95,
            "dma50": 90,
            "dma200": 80,
            "volume": 1_200_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 102,
            "low_20d": 70,
            "rs_5d_vs_spy": 0.03,
            "rs_5d_vs_qqq": 0.01,
            "sector_strong": True,
        }
    }

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        market_regime={"mode": "Risk-On"},
        events=[],
        watchlist=["NVDA"],
        today=date(2026, 5, 12),
    )

    nvda = result[0]

    assert nvda["ticker"] == "NVDA"
    assert nvda["score"] == 11
    assert nvda["grade"] == "A"
    assert "20일선 위" in nvda["positive_reasons"]
    assert "50일선 위" in nvda["positive_reasons"]
    assert "200일선 위" in nvda["positive_reasons"]
    assert "20일선이 50일선 위" in nvda["positive_reasons"]
    assert "거래량 20일 평균 이상" in nvda["positive_reasons"]
    assert "20일 고점 근처" in nvda["positive_reasons"]
    assert "SPY 대비 5일 상대강도 우위" in nvda["positive_reasons"]
    assert "QQQ 대비 5일 상대강도 우위" in nvda["positive_reasons"]
    assert "관련 섹터 ETF 강세" in nvda["positive_reasons"]
    assert nvda["negative_reasons"] == []
    assert nvda["event_flags"] == []


def test_b_grade_with_mixed_signals():
    indicators = {
        "MSFT": {
            "close": 100,
            "prev_close": 101,
            "dma20": 98,
            "dma50": 95,
            "dma200": 105,
            "volume": 1_100_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 110,
            "low_20d": 80,
            "rs_5d_vs_spy": 0.02,
            "rs_5d_vs_qqq": -0.01,
        }
    }

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=[],
        watchlist=["MSFT"],
        today=date(2026, 5, 12),
    )

    msft = result[0]

    # +2 above 20DMA
    # +2 above 50DMA
    # -2 below 200DMA
    # +1 20DMA above 50DMA
    # +1 volume above 20d average
    # +1 SPY RS positive
    # total = 5 => B
    assert msft["score"] == 5
    assert msft["grade"] == "B"
    assert "200일선 아래" in msft["negative_reasons"]
    assert "거래량 20일 평균 이상" in msft["positive_reasons"]
    assert "거래량 동반 하락" not in msft["negative_reasons"]


def test_earnings_within_7_days_penalty():
    indicators = {
        "AMD": {
            "close": 100,
            "prev_close": 99,
            "dma20": 95,
            "dma50": 90,
            "dma200": 80,
            "volume": 1_200_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 102,
            "low_20d": 70,
            "rs_5d_vs_spy": 0.03,
        }
    }
    events = [
        {
            "type": "earnings",
            "ticker": "AMD",
            "date": "2026-05-17",
            "risk_flag": "earnings_within_7d",
        }
    ]

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=events,
        watchlist=["AMD"],
        today=date(2026, 5, 12),
    )

    amd = result[0]

    # Base:
    # +2 20DMA
    # +2 50DMA
    # +1 200DMA
    # +1 20DMA above 50DMA
    # +1 volume
    # +1 near high
    # +1 SPY RS
    # -1 earnings within 7d
    # total = 8
    assert amd["score"] == 8
    assert amd["grade"] == "A"
    assert "어닝 7일 이내" in amd["negative_reasons"]
    assert "earnings_within_7d" in amd["event_flags"]


def test_earnings_today_or_tomorrow_penalty_is_not_double_counted():
    indicators = {
        "TSLA": {
            "close": 100,
            "prev_close": 99,
            "dma20": 95,
            "dma50": 90,
            "dma200": 80,
            "volume": 1_200_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 102,
            "low_20d": 70,
            "rs_5d_vs_qqq": 0.04,
        }
    }
    events = [
        {
            "type": "earnings",
            "ticker": "TSLA",
            "date": "2026-05-12",
        }
    ]

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=events,
        watchlist=["TSLA"],
        today=date(2026, 5, 12),
    )

    tsla = result[0]

    # Base positive score = 9
    # Earnings immediate penalty = -2
    # Total = 7. No additional -1 is stacked.
    assert tsla["score"] == 7
    assert tsla["grade"] == "A"
    assert "어닝 당일/익일" in tsla["negative_reasons"]
    assert "earnings_today" in tsla["event_flags"]


def test_d_grade_below_50dma_and_200dma_with_earnings_tomorrow():
    indicators = {
        "COIN": {
            "close": 80,
            "prev_close": 82,
            "dma20": 85,
            "dma50": 90,
            "dma200": 100,
            "volume": 800_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 110,
            "low_20d": 78,
            "rs_5d_vs_spy": -0.03,
            "rs_5d_vs_qqq": -0.04,
        }
    }
    events = [
        {
            "type": "earnings",
            "ticker": "COIN",
            "date": "2026-05-13",
        }
    ]

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=events,
        watchlist=["COIN"],
        today=date(2026, 5, 12),
    )

    coin = result[0]

    # -2 below 50DMA
    # -2 below 200DMA
    # -1 volume decline with price decline
    # -1 near 20d low
    # -2 earnings tomorrow
    assert coin["score"] == -8
    assert coin["grade"] == "D"
    assert "50일선 아래" in coin["negative_reasons"]
    assert "200일선 아래" in coin["negative_reasons"]
    assert "거래량 동반 하락" in coin["negative_reasons"]
    assert "20일 저점 근처" in coin["negative_reasons"]
    assert "어닝 당일/익일" in coin["negative_reasons"]


def test_data_shortage_caps_grade_to_c():
    indicators = {
        "PLTR": {
            "close": 100,
            "dma20": 95,
            "dma50": 90,
            # Missing dma200
            # Missing volume / volume average
            # Missing high_20d
            # Missing low_20d
            "rs_5d_vs_spy": 0.03,
        }
    }

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=[],
        watchlist=["PLTR"],
        today=date(2026, 5, 12),
    )

    pltr = result[0]

    assert pltr["grade"] == "C"
    assert "데이터 부족으로 등급을 C로 제한" in pltr["data_quality_notes"]
    assert "200DMA 판단 데이터 부족" in pltr["data_quality_notes"]
    assert "거래량 20일 평균 판단 데이터 부족" in pltr["data_quality_notes"]


def test_boolean_indicator_keys_are_supported():
    indicators = {
        "META": {
            "close_above_20dma": True,
            "close_above_50dma": True,
            "close_above_200dma": True,
            "volume_above_20d_avg": True,
            "near_20d_high": True,
            "near_20d_low": False,
            "rs_5d_vs_spy_positive": True,
            "rs_5d_vs_qqq_positive": True,
            "sector_etf_strong": True,
            "dma20": 100,
            "dma50": 95,
        }
    }

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=[],
        watchlist=["META"],
        today=date(2026, 5, 12),
    )

    meta = result[0]

    assert meta["score"] == 11
    assert meta["grade"] == "A"


def test_group_rankings_by_grade():
    rankings = [
        {"ticker": "NVDA", "grade": "A", "score": 8},
        {"ticker": "MSFT", "grade": "B", "score": 5},
        {"ticker": "TSLA", "grade": "D", "score": -2},
    ]

    grouped = group_rankings_by_grade(rankings)

    assert grouped["A"][0]["ticker"] == "NVDA"
    assert grouped["B"][0]["ticker"] == "MSFT"
    assert grouped["C"] == []
    assert grouped["D"][0]["ticker"] == "TSLA"


def test_flatten_events_accepts_nested_event_payload():
    payload = {
        "events_today": [
            {"type": "macro", "name": "CPI", "impact": "high"},
        ],
        "earnings_watchlist_7d": [
            {"type": "earnings", "ticker": "NVDA", "date": "2026-05-17"},
        ],
        "manual_events": [
            {"type": "company", "ticker": "TSLA", "name": "Manual check"},
        ],
    }

    events = flatten_events(payload)

    assert len(events) == 3
    assert any(event.get("ticker") == "NVDA" for event in events)
    assert any(event.get("name") == "CPI" for event in events)


def test_load_watchlist_from_yaml_dict_format(tmp_path):
    watchlist_file = tmp_path / "watchlist.yaml"
    watchlist_file.write_text(
        """
market_core:
  - SPY
  - QQQ
watchlist:
  - nvda
  - AMD
  - msft
""",
        encoding="utf-8",
    )

    watchlist = load_watchlist_from_yaml(watchlist_file)

    assert watchlist == ["NVDA", "AMD", "MSFT"]


def test_load_watchlist_from_yaml_plain_list_format(tmp_path):
    watchlist_file = tmp_path / "watchlist.yaml"
    watchlist_file.write_text(
        """
- nvda
- amd
- tsla
""",
        encoding="utf-8",
    )

    watchlist = load_watchlist_from_yaml(watchlist_file)

    assert watchlist == ["NVDA", "AMD", "TSLA"]


def test_rankings_are_sorted_by_grade_then_score_then_ticker():
    indicators = {
        "TSLA": {
            "close": 80,
            "prev_close": 82,
            "dma20": 85,
            "dma50": 90,
            "dma200": 100,
            "volume": 800_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 110,
            "low_20d": 78,
            "rs_5d_vs_spy": -0.01,
            "rs_5d_vs_qqq": -0.01,
        },
        "NVDA": {
            "close": 100,
            "prev_close": 99,
            "dma20": 95,
            "dma50": 90,
            "dma200": 80,
            "volume": 1_200_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 102,
            "low_20d": 70,
            "rs_5d_vs_spy": 0.02,
            "rs_5d_vs_qqq": 0.01,
        },
        "MSFT": {
            "close": 100,
            "prev_close": 99,
            "dma20": 95,
            "dma50": 90,
            "dma200": 80,
            "volume": 900_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 120,
            "low_20d": 80,
            "rs_5d_vs_spy": -0.01,
            "rs_5d_vs_qqq": -0.01,
        },
    }

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=[],
        watchlist=["TSLA", "NVDA", "MSFT"],
        today=date(2026, 5, 12),
    )

    assert [item["ticker"] for item in result] == ["NVDA", "MSFT", "TSLA"]


def test_spy_and_qqq_rs_both_positive_gives_plus_two():
    indicators = {
        "NVDA": {
            "close": 100,
            "prev_close": 99,
            "dma20": 110,
            "dma50": 120,
            "dma200": 130,
            "volume": 900_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 130,
            "low_20d": 70,
            "rs_5d_vs_spy": 0.02,
            "rs_5d_vs_qqq": 0.03,
        }
    }

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=[],
        watchlist=["NVDA"],
        today=date(2026, 5, 12),
    )

    nvda = result[0]

    assert "SPY 대비 5일 상대강도 우위" in nvda["positive_reasons"]
    assert "QQQ 대비 5일 상대강도 우위" in nvda["positive_reasons"]

    # -2 below 50DMA
    # -2 below 200DMA
    # +2 SPY/QQQ RS
    # total = -2
    assert nvda["score"] == -2


def test_spy_only_rs_positive_gives_plus_one():
    indicators = {
        "AMD": {
            "close": 100,
            "prev_close": 99,
            "dma20": 110,
            "dma50": 120,
            "dma200": 130,
            "volume": 900_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 130,
            "low_20d": 70,
            "rs_5d_vs_spy": 0.02,
            "rs_5d_vs_qqq": -0.01,
        }
    }

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=[],
        watchlist=["AMD"],
        today=date(2026, 5, 12),
    )

    amd = result[0]

    assert "SPY 대비 5일 상대강도 우위" in amd["positive_reasons"]
    assert "QQQ 대비 5일 상대강도 우위" not in amd["positive_reasons"]

    # -2 below 50DMA
    # -2 below 200DMA
    # +1 SPY RS
    # total = -3
    assert amd["score"] == -3


def test_20dma_above_50dma_gives_plus_one():
    indicators = {
        "AVGO": {
            "close": 100,
            "prev_close": 99,
            "dma20": 95,
            "dma50": 90,
            "dma200": 120,
            "volume": 900_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 130,
            "low_20d": 70,
            "rs_5d_vs_spy": -0.01,
            "rs_5d_vs_qqq": -0.01,
        }
    }

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=[],
        watchlist=["AVGO"],
        today=date(2026, 5, 12),
    )

    avgo = result[0]

    assert "20일선이 50일선 위" in avgo["positive_reasons"]

    # +2 above 20DMA
    # +2 above 50DMA
    # -2 below 200DMA
    # +1 20DMA above 50DMA
    # total = 3
    assert avgo["score"] == 3


def test_volume_decline_with_price_decline_gives_minus_one():
    indicators = {
        "AAPL": {
            "close": 98,
            "prev_close": 100,
            "dma20": 110,
            "dma50": 120,
            "dma200": 130,
            "volume": 800_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 130,
            "low_20d": 70,
            "rs_5d_vs_spy": -0.01,
            "rs_5d_vs_qqq": -0.01,
        }
    }

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=[],
        watchlist=["AAPL"],
        today=date(2026, 5, 12),
    )

    aapl = result[0]

    assert "거래량 동반 하락" in aapl["negative_reasons"]

    # -2 below 50DMA
    # -2 below 200DMA
    # -1 volume decline with price decline
    # total = -5
    assert aapl["score"] == -5


def test_near_20d_low_gives_minus_one():
    indicators = {
        "AMZN": {
            "close": 101,
            "prev_close": 102,
            "dma20": 110,
            "dma50": 120,
            "dma200": 130,
            "volume": 1_200_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 130,
            "low_20d": 100,
            "rs_5d_vs_spy": -0.01,
            "rs_5d_vs_qqq": -0.01,
        }
    }

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=[],
        watchlist=["AMZN"],
        today=date(2026, 5, 12),
    )

    amzn = result[0]

    assert "20일 저점 근처" in amzn["negative_reasons"]

    # -2 below 50DMA
    # -2 below 200DMA
    # +1 volume
    # -1 near low
    # total = -4
    assert amzn["score"] == -4


def test_single_dma_missing_caps_grade_at_c():
    indicators = {
        "NFLX": {
            "close": 100,
            "prev_close": 99,
            "dma20": 95,
            "dma50": 90,
            # Missing dma200 only
            "volume": 1_200_000,
            "volume_20d_avg": 1_000_000,
            "high_20d": 102,
            "low_20d": 70,
            "rs_5d_vs_spy": 0.02,
            "rs_5d_vs_qqq": 0.03,
            "sector_strong": True,
        }
    }

    result = rank_watchlist(
        indicators_by_ticker=indicators,
        events=[],
        watchlist=["NFLX"],
        today=date(2026, 5, 12),
    )

    nflx = result[0]

    assert nflx["score"] >= 7
    assert nflx["grade"] == "C"
    assert "200DMA 판단 데이터 부족" in nflx["data_quality_notes"]
    assert "데이터 부족으로 등급을 C로 제한" in nflx["data_quality_notes"]