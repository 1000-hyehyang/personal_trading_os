# src/main.py
"""
Personal Trading OS MVP - main orchestrator

Windows / Python 3.12 기준

역할:
- argparse로 --session post_close 받기
- config 로드
- 가격 데이터 수집
- 지표 계산
- 이벤트/어닝 자동 수집
- 수동 이벤트/뉴스 메모 병합
- 시장 모드 판정
- 관심종목 A/B/C/D 랭킹
- 셋업 후보 분류
- 리스크 엔진 실행
- Daily Packet 생성
- GPT/Claude 프롬프트 생성
- Telegram 전송
- 각 단계 실패 시 전체 프로그램을 바로 종료하지 않고 data_quality_notes와 로그에 기록
- 심각한 실패일 때만 exit code 1

주의:
- OpenAI API / Claude API 호출 없음
- TradingView scraping 없음
- 자동매매 없음
"""

from __future__ import annotations

import argparse
import csv
import importlib
import inspect
import json
import logging
import math
import os
import re
import sys
import traceback
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore


# ============================================================
# Constants
# ============================================================

DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_FILES = {
    "daily_packet_md": "daily_packet.md",
    "daily_packet_json": "daily_packet.json",
    "prompt_for_gpt": "prompt_for_gpt.txt",
    "prompt_for_claude": "prompt_for_claude.txt",
    "telegram_summary": "telegram_summary.txt",
    "events_auto": "events_auto.json",
    "events_merged": "events_merged.json",
}

REQUIRED_DO_NOT_DO = [
    "장초반 첫 5~15분 갭상승 종목 무근거 추격 금지",
    "D급 종목 물타기 금지",
    "손절가 없는 진입 금지",
    "VIX 상승 중 고베타 종목 포지션 확대 금지",
    "CPI/FOMC/대형 실적 전후 과대 진입 금지",
    "시장 모드 Caution/Defensive에서 신규 공격 매매 금지",
    "뉴스 하나만 보고 차트·섹터 확인 없이 진입 금지",
]

HIGH_IMPACT_KEYWORDS = [
    "CPI",
    "PPI",
    "Employment",
    "Nonfarm",
    "Payroll",
    "FOMC",
    "Minutes",
    "PCE",
    "GDP",
    "Rate Decision",
]

DEFAULT_SETTINGS = {
    "session": {
        "default": "post_close",
        "timezone_market": "America/New_York",
        "timezone_user": "Asia/Seoul",
    },
    "data": {
        "provider": "yfinance",
        "lookback_period": "1y",
        "interval": "1d",
    },
    "events": {
        "earnings_provider": "alpha_vantage",
        "economic_provider": "fmp_bls_fed",
        "lookahead_days": 30,
        "earnings_risk_window_days": 7,
    },
    "output": {
        "max_priority_tickers": 7,
        "max_risk_tickers": 7,
        "language": "ko",
    },
    "telegram": {
        "send_summary": True,
        "send_daily_packet": True,
        "send_gpt_prompt": True,
        "send_claude_prompt": True,
    },
}


# ============================================================
# Data models
# ============================================================

@dataclass
class PipelineState:
    project_root: Path
    session: str
    generated_at: str
    run_date: str
    config: dict[str, Any] = field(default_factory=dict)
    prices: Any = None
    indicators: dict[str, Any] = field(default_factory=dict)
    events_auto: dict[str, Any] = field(default_factory=dict)
    events_merged: dict[str, Any] = field(default_factory=dict)
    market_regime: dict[str, Any] = field(default_factory=dict)
    rankings: list[dict[str, Any]] = field(default_factory=list)
    setups: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)
    manual_news_notes: str = ""
    data_quality_notes: list[str] = field(default_factory=list)
    step_results: dict[str, str] = field(default_factory=dict)
    serious_failures: list[str] = field(default_factory=list)

    def add_note(self, message: str) -> None:
        logging.warning(message)
        self.data_quality_notes.append(message)

    def mark_ok(self, step: str) -> None:
        self.step_results[step] = "OK"
        logging.info("%s: OK", step)

    def mark_warn(self, step: str, message: str) -> None:
        self.step_results[step] = f"WARN: {message}"
        self.add_note(f"[{step}] {message}")

    def mark_fail(self, step: str, message: str, serious: bool = False) -> None:
        self.step_results[step] = f"FAIL: {message}"
        self.add_note(f"[{step}] {message}")
        if serious:
            self.serious_failures.append(f"[{step}] {message}")


# ============================================================
# Path / logging helpers
# ============================================================

def ensure_project_dirs(project_root: Path) -> None:
    for folder in ["config", "data", "output", "cache", "logs", "src"]:
        (project_root / folder).mkdir(parents=True, exist_ok=True)


def setup_logging(project_root: Path, session: str) -> None:
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_name = "post_close.log" if session == "post_close" else f"{session}.log"
    log_path = logs_dir / log_name

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )


def json_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    try:
        if pd is not None and isinstance(obj, pd.Timestamp):
            return obj.isoformat()
    except Exception:
        pass
    try:
        if pd is not None and pd.isna(obj):
            return None
    except Exception:
        pass
    return str(obj)


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        if pd is not None and pd.isna(value):
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def normalize_ticker(ticker: Any) -> str:
    return str(ticker or "").strip().upper()


# ============================================================
# Dynamic module helpers
# ============================================================

def import_optional_module(module_name: str) -> Any | None:
    try:
        return importlib.import_module(module_name)
    except Exception as exc:
        logging.info("Optional module not available: %s (%s)", module_name, exc)
        return None


def get_first_callable(module: Any | None, names: list[str]) -> Callable[..., Any] | None:
    if module is None:
        return None
    for name in names:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    return None


def smart_call(fn: Callable[..., Any], **kwargs: Any) -> Any:
    """
    기존 모듈 함수들의 인자 이름이 조금씩 달라도 최대한 맞춰 호출한다.

    예:
    - indicators -> indicators_by_ticker
    - rankings -> watchlist_rankings
    - rankings -> watchlist_ranker_result
    - events -> events_merged
    """
    signature = inspect.signature(fn)
    params = signature.parameters

    alias_map = {
        "indicators_by_ticker": [
            "indicators",
            "indicator_by_ticker",
            "indicators_by_symbol",
        ],
        "prices_by_ticker": [
            "prices",
            "price_data",
            "prices_by_symbol",
        ],
        "price_data_by_ticker": [
            "prices",
            "price_data",
            "prices_by_ticker",
        ],
        "watchlist_rankings": [
            "rankings",
            "watchlist_ranking",
            "watchlist_ranker_result",
        ],
        "watchlist_ranker_result": [
            "rankings",
            "watchlist_ranking",
            "watchlist_rankings",
        ],
        "events_merged": [
            "events_merged",
            "events",
            "merged_events",
        ],
        "ticker_event_flags": [
            "ticker_event_flags",
            "event_flags",
            "event_flags_by_ticker",
        ],
        "event_flags_by_ticker": [
            "ticker_event_flags",
            "event_flags",
        ],
        "market_mode": [
            "market_regime",
        ],
    }

    accepts_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
    )

    if accepts_kwargs:
        enriched = dict(kwargs)
        for target, sources in alias_map.items():
            if target not in enriched:
                for source in sources:
                    if source in kwargs:
                        enriched[target] = kwargs[source]
                        break
        return fn(**enriched)

    filtered = {key: value for key, value in kwargs.items() if key in params}

    for target, sources in alias_map.items():
        if target in params and target not in filtered:
            for source in sources:
                if source in kwargs:
                    filtered[target] = kwargs[source]
                    break

    required_missing = [
        name
        for name, param in params.items()
        if param.default is inspect.Parameter.empty
        and param.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        and name not in filtered
    ]

    if not required_missing:
        return fn(**filtered)

    if len(params) == 1:
        payload_candidates = [
            "packet_payload",
            "payload",
            "state",
            "config",
            "events",
            "events_merged",
            "rankings",
            "watchlist_rankings",
            "prices",
            "indicators",
            "indicators_by_ticker",
        ]
        for candidate in payload_candidates:
            if candidate in kwargs:
                return fn(kwargs[candidate])
        return fn(filtered if filtered else kwargs)

    return fn(**filtered)


# ============================================================
# Config loading
# ============================================================
def force_rebuild_ticker_universe(state: PipelineState) -> None:
    """
    config_loader.py가 all_tickers를 일부만 반환하거나 watchlist 구조를 축약해도,
    config/watchlist.yaml 원본을 직접 읽어 시장/섹터/관심종목 ticker universe를 복구한다.
    """
    raw_watchlist_path = state.project_root / "config" / "watchlist.yaml"

    raw_watchlist_config: dict[str, Any] = {}

    try:
        loaded = read_yaml_file(raw_watchlist_path, {})
        if isinstance(loaded, dict):
            raw_watchlist_config = loaded
    except Exception as exc:
        state.add_note(f"[config_load] watchlist.yaml 원본 재로드 실패: {exc}")

    if raw_watchlist_config:
        state.config["watchlist"] = raw_watchlist_config

    rebuilt_tickers: set[str] = set()

    rebuilt_tickers.update(
        extract_all_tickers(state.config.get("watchlist", {}))
    )

    existing_all_tickers = state.config.get("all_tickers") or []
    if isinstance(existing_all_tickers, list):
        rebuilt_tickers.update(normalize_ticker(t) for t in existing_all_tickers)

    for required in [
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "SMH",
        "XLK",
        "TLT",
        "HYG",
        "UUP",
        "^VIX",
        "^TNX",
    ]:
        rebuilt_tickers.add(required)

    state.config["all_tickers"] = sorted(
        {ticker for ticker in rebuilt_tickers if ticker}
    )

    if len(state.config["all_tickers"]) <= 4:
        state.add_note(
            "[config_load] 전체 데이터 ticker universe가 4개 이하입니다. "
            "config/watchlist.yaml에 market_core, volatility, rates_credit, sectors, watchlist 섹션이 있는지 확인하세요."
        )


def read_yaml_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    if yaml is None:
        raise RuntimeError("pyyaml is not installed")
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    return default if loaded is None else loaded


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def fallback_load_config(project_root: Path) -> dict[str, Any]:
    config_dir = project_root / "config"
    data_dir = project_root / "data"

    watchlist_config = read_yaml_file(config_dir / "watchlist.yaml", {})
    settings_config = read_yaml_file(config_dir / "settings.yaml", {})
    rules_config = read_yaml_file(config_dir / "rules.yaml", {})
    setups_config = read_yaml_file(config_dir / "setups.yaml", {})
    manual_events_config = read_yaml_file(config_dir / "events_manual.yaml", {})

    settings = deep_merge(DEFAULT_SETTINGS, settings_config or {})

    manual_news_path = data_dir / "manual_news_notes.md"
    manual_news_notes = ""
    if manual_news_path.exists():
        manual_news_notes = manual_news_path.read_text(encoding="utf-8")

    all_tickers = extract_all_tickers(watchlist_config)

    return {
        "watchlist": watchlist_config,
        "settings": settings,
        "rules": rules_config,
        "setups": setups_config,
        "manual_events": manual_events_config,
        "manual_news_notes": manual_news_notes,
        "all_tickers": all_tickers,
        "project_root": str(project_root),
    }


def load_config_step(state: PipelineState) -> None:
    step = "config_load"

    try:
        if load_dotenv is not None:
            load_dotenv(state.project_root / ".env")

        config_loader = import_optional_module("config_loader")
        fn = get_first_callable(
            config_loader,
            [
                "load_all_configs",
                "load_config",
                "load_configs",
                "load_project_config",
            ],
        )

        if fn is not None:
            try:
                loaded = smart_call(
                    fn,
                    project_root=state.project_root,
                    config_dir=state.project_root / "config",
                    data_dir=state.project_root / "data",
                )
                if isinstance(loaded, dict):
                    fallback = fallback_load_config(state.project_root)
                    state.config = deep_merge(fallback, loaded)
                else:
                    state.config = fallback_load_config(state.project_root)
                    state.mark_warn(
                        step,
                        "config_loader 반환값이 dict가 아니어서 fallback config를 사용했습니다.",
                    )
            except Exception as exc:
                logging.exception("config_loader failed")
                state.config = fallback_load_config(state.project_root)
                state.mark_warn(
                    step,
                    f"config_loader 실패로 fallback config를 사용했습니다: {exc}",
                )
        else:
            state.config = fallback_load_config(state.project_root)

        # config_loader가 all_tickers를 일부만 반환해도,
        # watchlist.yaml 전체 구조를 다시 읽어 시장/섹터/관심종목 ticker를 복구한다.
        rebuilt_tickers = set(state.config.get("all_tickers") or [])
        rebuilt_tickers.update(extract_all_tickers(state.config.get("watchlist", {})))

        for required in ["SPY", "QQQ", "IWM", "DIA", "SMH", "XLK", "TLT", "HYG", "UUP", "^VIX", "^TNX"]:
            rebuilt_tickers.add(required)

        state.config["all_tickers"] = sorted(
            {normalize_ticker(t) for t in rebuilt_tickers if normalize_ticker(t)}
        )

        force_rebuild_ticker_universe(state)


        state.manual_news_notes = str(state.config.get("manual_news_notes", ""))
        if not extract_watchlist_tickers(state.config):
            state.mark_warn(step, "watchlist가 비어 있습니다. config/watchlist.yaml을 확인하세요.")
        else:
            state.mark_ok(step)

    except Exception as exc:
        logging.exception("Config load serious failure")
        state.config = {
            "watchlist": {},
            "settings": DEFAULT_SETTINGS,
            "rules": {},
            "setups": {},
            "manual_events": {},
            "manual_news_notes": "",
            "all_tickers": [],
            "project_root": str(state.project_root),
        }
        state.mark_fail(step, f"config 로드 실패: {exc}", serious=True)


def collect_tickers_recursive(value: Any) -> list[str]:
    """
    YAML 값이 list/dict 중첩 구조여도 ticker 문자열을 모두 수집한다.

    예:
    watchlist:
      mega_cap_tech:
        - MSFT
        - AAPL
      semiconductors:
        - NVDA

    sectors:
      broad_technology:
        - XLK
    """
    tickers: list[str] = []

    if value is None:
        return tickers

    if isinstance(value, str):
        ticker = normalize_ticker(value)
        if ticker:
            tickers.append(ticker)
        return tickers

    if isinstance(value, list):
        for item in value:
            tickers.extend(collect_tickers_recursive(item))
        return tickers

    if isinstance(value, dict):
        for nested_value in value.values():
            tickers.extend(collect_tickers_recursive(nested_value))
        return tickers

    return tickers


def extract_watchlist_tickers(config: dict[str, Any]) -> list[str]:
    """
    관심종목 watchlist만 추출한다.
    단순 list 구조와 nested category 구조를 모두 지원한다.
    """
    if not isinstance(config, dict):
        return []

    watchlist_config = config.get("watchlist", config)

    if isinstance(watchlist_config, dict) and "watchlist" in watchlist_config:
        raw_watchlist = watchlist_config.get("watchlist", [])
    elif isinstance(watchlist_config, dict):
        raw_watchlist = watchlist_config
    elif isinstance(watchlist_config, list):
        raw_watchlist = watchlist_config
    else:
        raw_watchlist = []

    tickers = collect_tickers_recursive(raw_watchlist)

    # ticker_metadata 같은 dict key/metadata 값이 섞이지 않게 watchlist 섹션만 대상으로 함
    return sorted({ticker for ticker in tickers if ticker})


def extract_all_tickers(watchlist_config: dict[str, Any]) -> list[str]:
    """
    가격 수집 universe 전체를 추출한다.
    market_core, volatility, rates_credit, sectors, watchlist만 대상으로 삼고,
    ticker_metadata의 sector/theme 같은 문자열은 ticker로 오인하지 않는다.
    """
    tickers: set[str] = set()

    if isinstance(watchlist_config, dict):
        for section in ["market_core", "volatility", "rates_credit", "sectors", "watchlist"]:
            tickers.update(collect_tickers_recursive(watchlist_config.get(section, [])))

    elif isinstance(watchlist_config, list):
        tickers.update(collect_tickers_recursive(watchlist_config))

    for ticker in ["SPY", "QQQ", "IWM", "DIA", "SMH", "XLK", "TLT", "HYG", "UUP", "^VIX", "^TNX"]:
        tickers.add(ticker)

    return sorted({normalize_ticker(t) for t in tickers if normalize_ticker(t)})


def get_settings(state: PipelineState) -> dict[str, Any]:
    return state.config.get("settings", DEFAULT_SETTINGS)


# ============================================================
# Price data
# ============================================================

def collect_prices_step(state: PipelineState) -> None:
    step = "price_collection"
    settings = get_settings(state)
    tickers = state.config.get("all_tickers") or extract_all_tickers(state.config.get("watchlist", {}))

    if not tickers:
        state.mark_warn(step, "수집할 ticker가 없습니다.")
        state.prices = {}
        return

    try:
        fetch_prices = import_optional_module("fetch_prices")
        fn = get_first_callable(
            fetch_prices,
            [
                "fetch_price_data",
                "fetch_prices",
                "collect_prices",
                "download_prices",
                "get_price_data",
            ],
        )

        if fn is not None:
            try:
                raw_prices = smart_call(
                    fn,
                    tickers=tickers,
                    symbols=tickers,
                    config=state.config,
                    settings=settings,
                    project_root=state.project_root,
                    cache_dir=state.project_root / "cache",
                    lookback_period=settings.get("data", {}).get("lookback_period", "1y"),
                    interval=settings.get("data", {}).get("interval", "1d"),
                )

                state.prices = normalize_price_payload(raw_prices)

                if not state.prices:
                    state.mark_warn(
                        step,
                        "fetch_prices 모듈은 실행됐지만 정규화 가능한 가격 데이터가 없습니다. fallback yfinance를 시도합니다.",
                    )
                    state.prices = fallback_fetch_prices(
                        tickers=tickers,
                        lookback_period=settings.get("data", {}).get("lookback_period", "1y"),
                        interval=settings.get("data", {}).get("interval", "1d"),
                        cache_path=state.project_root / "cache" / "prices_cache.json",
                    )
                    state.prices = normalize_price_payload(state.prices)

                if state.prices:
                    state.mark_ok(step)
                else:
                    state.mark_warn(step, "가격 데이터가 비어 있습니다.")

                return
            except Exception as exc:
                logging.exception("fetch_prices module failed")
                state.mark_warn(
                    step,
                    f"fetch_prices 모듈 실패. yfinance fallback을 시도합니다: {exc}",
                )

        state.prices = fallback_fetch_prices(
            tickers=tickers,
            lookback_period=settings.get("data", {}).get("lookback_period", "1y"),
            interval=settings.get("data", {}).get("interval", "1d"),
            cache_path=state.project_root / "cache" / "prices_cache.json",
        )

        if not state.prices:
            state.mark_warn(step, "가격 데이터가 비어 있습니다.")
        else:
            state.mark_ok(step)

    except Exception as exc:
        logging.exception("Price collection failed")
        state.prices = {}
        state.mark_warn(step, f"가격 데이터 수집 실패: {exc}")


def fallback_fetch_prices(
    tickers: list[str],
    lookback_period: str,
    interval: str,
    cache_path: Path,
) -> dict[str, list[dict[str, Any]]]:
    """
    yfinance fallback.

    반환 형식:
    {
      "AAPL": [
        {"date": "...", "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}
      ]
    }
    """
    try:
        import yfinance as yf
    except Exception as exc:
        logging.warning("yfinance is not available: %s", exc)
        return read_price_cache(cache_path)

    result: dict[str, list[dict[str, Any]]] = {}

    for ticker in tickers:
        try:
            df = yf.download(
                ticker,
                period=lookback_period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=False,
            )

            if df is None or df.empty:
                logging.warning("No yfinance data for %s", ticker)
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [str(col[0]).lower() for col in df.columns]
            else:
                df.columns = [str(col).lower().replace(" ", "_") for col in df.columns]

            rows: list[dict[str, Any]] = []
            for idx, row in df.iterrows():
                rows.append(
                    {
                        "date": pd.Timestamp(idx).date().isoformat() if pd is not None else str(idx),
                        "open": safe_float(row.get("open")),
                        "high": safe_float(row.get("high")),
                        "low": safe_float(row.get("low")),
                        "close": safe_float(row.get("close")),
                        "adj_close": safe_float(row.get("adj_close")),
                        "volume": safe_float(row.get("volume")),
                    }
                )
            result[ticker] = rows

        except Exception as exc:
            logging.warning("Failed to download %s: %s", ticker, exc)

    if result:
        write_json(cache_path, result)
        return result

    return read_price_cache(cache_path)


def read_price_cache(cache_path: Path) -> dict[str, list[dict[str, Any]]]:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ============================================================
# Indicators
# ============================================================

def calculate_indicators_step(state: PipelineState) -> None:
    step = "indicator_calculation"

    try:
        indicators_module = import_optional_module("indicators")
        fn = get_first_callable(
            indicators_module,
            [
                "calculate_indicators",
                "build_indicators",
                "compute_indicators",
                "calculate_all_indicators",
            ],
        )

        if fn is not None:
            try:
                output = smart_call(
                    fn,
                    prices=state.prices,
                    price_data=state.prices,
                    prices_by_ticker=state.prices,
                    config=state.config,
                    settings=get_settings(state),
                    tickers=state.config.get("all_tickers", []),
                )

                module_indicators = normalize_indicators(output)

                if module_indicators:
                    state.indicators = module_indicators
                    state.mark_ok(step)
                    return

                state.mark_warn(
                    step,
                    "indicators 모듈 결과가 비어 있어 fallback 지표 계산을 사용합니다.",
                )
            except Exception as exc:
                logging.exception("indicators module failed")
                state.mark_warn(
                    step,
                    f"indicators 모듈 실패. fallback 지표 계산을 사용합니다: {exc}",
                )

        state.prices = normalize_price_payload(state.prices)
        state.indicators = fallback_calculate_indicators(state.prices)
        if not state.indicators:
            state.mark_warn(step, "계산된 지표가 없습니다.")
        else:
            state.mark_ok(step)

    except Exception as exc:
        logging.exception("Indicator calculation failed")
        state.indicators = {}
        state.mark_warn(step, f"지표 계산 실패: {exc}")


def normalize_indicators(output: Any) -> dict[str, Any]:
    if output is None:
        return {}

    if isinstance(output, dict):
        return output

    if pd is not None and isinstance(output, pd.DataFrame):
        result: dict[str, Any] = {}
        for _, row in output.iterrows():
            ticker = normalize_ticker(row.get("ticker") or row.get("symbol"))
            if not ticker:
                continue
            result[ticker] = row.to_dict()
        return result

    return {}


def normalize_price_payload(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """
    fetch_prices.py가 반환하는 여러 형태를 fallback 지표 계산이 쓸 수 있는 형태로 정규화한다.

    목표 형식:
    {
      "AAPL": [
        {"date": "...", "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}
      ]
    }
    """
    if payload is None:
        return {}

    if isinstance(payload, dict):
        for nested_key in ["prices", "price_data", "prices_by_ticker", "data"]:
            nested = payload.get(nested_key)
            if nested is not None and nested is not payload:
                normalized_nested = normalize_price_payload(nested)
                if normalized_nested:
                    return normalized_nested

        result: dict[str, list[dict[str, Any]]] = {}
        for ticker, value in payload.items():
            ticker_norm = normalize_ticker(ticker)
            if not ticker_norm:
                continue

            rows = normalize_single_price_value(value, ticker=ticker_norm)
            if rows:
                result[ticker_norm] = rows

        return result

    if pd is not None and isinstance(payload, pd.DataFrame):
        return normalize_price_dataframe_payload(payload)

    return {}


def normalize_single_price_value(value: Any, ticker: str) -> list[dict[str, Any]]:
    if value is None:
        return []

    if isinstance(value, list):
        rows = []
        for item in value:
            if isinstance(item, dict):
                row = normalize_price_row(item)
                if row.get("close") is not None:
                    rows.append(row)
        return rows

    if pd is not None and isinstance(value, pd.DataFrame):
        return dataframe_to_price_rows(value)

    if isinstance(value, dict):
        # 이미 {"rows": [...]} 또는 {"history": [...]} 형태인 경우
        for key in ["rows", "history", "prices", "data"]:
            if key in value:
                return normalize_single_price_value(value[key], ticker=ticker)

        # 단일 row dict인 경우
        row = normalize_price_row(value)
        return [row] if row.get("close") is not None else []

    return []


def normalize_price_dataframe_payload(df: Any) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}

    if pd is None or df is None or df.empty:
        return result

    # yfinance.download(tickers=[...]) MultiIndex 대응
    if isinstance(df.columns, pd.MultiIndex):
        level0 = [str(x) for x in df.columns.get_level_values(0)]
        level1 = [str(x) for x in df.columns.get_level_values(1)]

        price_words = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}

        # 보통 yfinance group_by 기본값: level0=Price, level1=Ticker
        if any(x in price_words for x in level0):
            tickers = sorted({normalize_ticker(x) for x in level1 if normalize_ticker(x)})
            for ticker in tickers:
                try:
                    sub = df.xs(ticker, axis=1, level=1)
                    rows = dataframe_to_price_rows(sub)
                    if rows:
                        result[ticker] = rows
                except Exception:
                    continue
        else:
            # 반대 형태: level0=Ticker, level1=Price
            tickers = sorted({normalize_ticker(x) for x in level0 if normalize_ticker(x)})
            for ticker in tickers:
                try:
                    sub = df.xs(ticker, axis=1, level=0)
                    rows = dataframe_to_price_rows(sub)
                    if rows:
                        result[ticker] = rows
                except Exception:
                    continue

        return result

    columns_lower = {str(c).lower(): c for c in df.columns}

    if "ticker" in columns_lower or "symbol" in columns_lower:
        ticker_col = columns_lower.get("ticker") or columns_lower.get("symbol")
        for ticker, sub in df.groupby(ticker_col):
            ticker_norm = normalize_ticker(ticker)
            rows = dataframe_to_price_rows(sub.drop(columns=[ticker_col], errors="ignore"))
            if ticker_norm and rows:
                result[ticker_norm] = rows

    return result


def dataframe_to_price_rows(df: Any) -> list[dict[str, Any]]:
    if pd is None or df is None or df.empty:
        return []

    temp = df.copy()
    temp.columns = [str(c).lower().replace(" ", "_") for c in temp.columns]

    rows = []
    for idx, row in temp.iterrows():
        item = {
            "date": extract_row_date(idx, row),
            "open": safe_float(row.get("open")),
            "high": safe_float(row.get("high")),
            "low": safe_float(row.get("low")),
            "close": safe_float(row.get("close")),
            "adj_close": safe_float(row.get("adj_close")),
            "volume": safe_float(row.get("volume")),
        }
        if item["close"] is not None:
            rows.append(item)

    return rows


def normalize_price_row(row: dict[str, Any]) -> dict[str, Any]:
    lower = {str(k).lower().replace(" ", "_"): v for k, v in row.items()}

    return {
        "date": str(
            lower.get("date")
            or lower.get("datetime")
            or lower.get("timestamp")
            or ""
        ),
        "open": safe_float(lower.get("open")),
        "high": safe_float(lower.get("high")),
        "low": safe_float(lower.get("low")),
        "close": safe_float(lower.get("close")),
        "adj_close": safe_float(lower.get("adj_close")),
        "volume": safe_float(lower.get("volume")),
    }


def extract_row_date(idx: Any, row: Any) -> str:
    for key in ["date", "datetime", "timestamp"]:
        try:
            value = row.get(key)
            if value is not None and str(value) != "nan":
                if pd is not None:
                    return pd.Timestamp(value).date().isoformat()
                return str(value)
        except Exception:
            pass

    try:
        if pd is not None:
            return pd.Timestamp(idx).date().isoformat()
    except Exception:
        pass

    return str(idx)


def fallback_calculate_indicators(prices: Any) -> dict[str, Any]:
    prices = normalize_price_payload(prices)

    if not isinstance(prices, dict):
        return {}

    result: dict[str, Any] = {}

    closes_by_ticker: dict[str, list[float]] = {}
    for ticker, rows in prices.items():
        clean_rows = rows if isinstance(rows, list) else []
        closes = [
            safe_float(row.get("close"))
            for row in clean_rows
            if isinstance(row, dict) and safe_float(row.get("close")) is not None
        ]
        closes_by_ticker[ticker] = [float(x) for x in closes if x is not None]

    spy_closes = closes_by_ticker.get("SPY", [])
    qqq_closes = closes_by_ticker.get("QQQ", [])

    for ticker, rows in prices.items():
        if not isinstance(rows, list) or not rows:
            continue

        valid_rows = [row for row in rows if isinstance(row, dict) and safe_float(row.get("close")) is not None]
        if not valid_rows:
            continue

        closes = [float(safe_float(row.get("close"), 0) or 0) for row in valid_rows]
        volumes = [float(safe_float(row.get("volume"), 0) or 0) for row in valid_rows]

        close = closes[-1]
        prev_close = closes[-2] if len(closes) >= 2 else None
        change_pct = ((close / prev_close) - 1) * 100 if prev_close and prev_close > 0 else None

        dma20 = mean_last(closes, 20)
        dma50 = mean_last(closes, 50)
        dma200 = mean_last(closes, 200)
        vol20 = mean_last(volumes, 20)

        high20 = max(closes[-20:]) if len(closes) >= 1 else close
        low20 = min(closes[-20:]) if len(closes) >= 1 else close

        return_5d = pct_return(closes, 5)
        spy_rs_5d = compare_return(return_5d, pct_return(spy_closes, 5))
        qqq_rs_5d = compare_return(return_5d, pct_return(qqq_closes, 5))

        above_20 = close > dma20 if dma20 else None
        above_50 = close > dma50 if dma50 else None
        above_200 = close > dma200 if dma200 else None

        result[ticker] = {
            "ticker": ticker,
            "date": valid_rows[-1].get("date"),
            "close": close,
            "prev_close": prev_close,
            "change_pct": change_pct,
            # Canonical MA keys used by market_regime / packet_builder
            "20DMA": dma20,
            "50DMA": dma50,
            "200DMA": dma200,
            # Legacy aliases kept for backward-compat with existing tests
            "dma20": dma20,
            "dma50": dma50,
            "dma200": dma200,
            "volume": volumes[-1] if volumes else None,
            "volume_20d_avg": vol20,
            # Canonical boolean keys (indicators.py style)
            "close_above_20dma": above_20,
            "close_above_50dma": above_50,
            "close_above_200dma": above_200,
            # Legacy boolean aliases
            "above_20dma": above_20,
            "above_50dma": above_50,
            "above_200dma": above_200,
            "dma20_above_dma50": dma20 > dma50 if dma20 and dma50 else None,
            "volume_above_20d_avg": volumes[-1] > vol20 if volumes and vol20 else None,
            "near_20d_high": close >= high20 * 0.97 if high20 else None,
            "near_20d_low": close <= low20 * 1.03 if low20 else None,
            # Canonical return key (indicators.py style)
            "5D_return": return_5d,
            # Legacy alias
            "return_5d": return_5d,
            "relative_strength_vs_spy_5d": spy_rs_5d,
            "relative_strength_vs_qqq_5d": qqq_rs_5d,
        }

    return result


def mean_last(values: list[float], window: int) -> float | None:
    if not values:
        return None
    subset = values[-window:]
    if not subset:
        return None
    return sum(subset) / len(subset)


def pct_return(values: list[float], days: int) -> float | None:
    if len(values) <= days:
        return None
    start = values[-days - 1]
    end = values[-1]
    if start == 0:
        return None
    return ((end / start) - 1) * 100


def compare_return(value: float | None, benchmark: float | None) -> float | None:
    if value is None or benchmark is None:
        return None
    return value - benchmark


# ============================================================
# Events
# ============================================================
def sanitize_event_list(events: Any) -> list[dict[str, Any]]:
    if not events:
        return []

    if isinstance(events, dict):
        return extract_event_items(events)

    result: list[dict[str, Any]] = []

    if isinstance(events, list):
        for item in events:
            if isinstance(item, dict):
                result.append(dict(item))
            elif isinstance(item, str) and item.strip():
                result.append(
                    {
                        "type": "note",
                        "name": item.strip(),
                        "impact": "low",
                        "source": "manual_or_fallback",
                    }
                )

    return result


def extract_event_items(payload: Any) -> list[dict[str, Any]]:
    if not payload:
        return []

    if isinstance(payload, list):
        return sanitize_event_list(payload)

    if not isinstance(payload, dict):
        return []

    result: list[dict[str, Any]] = []

    for key in [
        "events",
        "auto_events",
        "economic_events",
        "earnings",
        "events_today",
        "events_next_24h",
        "earnings_watchlist_7d",
        "manual_events",
    ]:
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    result.append(dict(item))
                elif isinstance(item, str) and item.strip():
                    result.append(
                        {
                            "type": "note",
                            "name": item.strip(),
                            "impact": "low",
                            "source": key,
                        }
                    )

    return result


def collect_events_step(state: PipelineState) -> None:
    step = "event_collection"

    try:
        event_calendar = import_optional_module("event_calendar")

        auto_events = None
        collect_fn = get_first_callable(
            event_calendar,
            [
                "collect_auto_events",
                "build_auto_events",
                "fetch_auto_events",
                "get_auto_events",
            ],
        )

        if collect_fn is not None:
            try:
                auto_events = smart_call(
                    collect_fn,
                    config=state.config,
                    settings=get_settings(state),
                    watchlist=extract_watchlist_tickers(state.config),
                    project_root=state.project_root,
                    cache_dir=state.project_root / "cache",
                    output_dir=state.project_root / "output",
                )
            except Exception as exc:
                logging.exception("event_calendar auto collection failed")
                state.mark_warn(
                    step,
                    f"event_calendar 자동 이벤트 수집 실패. fallback을 사용합니다: {exc}",
                )

        if auto_events is None:
            auto_events = fallback_collect_auto_events(state)

        state.events_auto = normalize_events_payload(auto_events)

        manual_events = load_manual_events(state)
        manual_news_notes = state.manual_news_notes

        auto_event_items = extract_event_items(state.events_auto)
        manual_events = sanitize_event_list(manual_events)

        merge_fn = get_first_callable(
            event_calendar,
            [
                "merge_auto_and_manual_events",
                "merge_events",
                "build_merged_events",
            ],
        )

        merged = None
        if merge_fn is not None:
            try:
                merged = smart_call(
                    merge_fn,
                    auto_events=auto_event_items,
                    events_auto=auto_event_items,
                    manual_events=manual_events,
                    manual_news_notes=manual_news_notes,
                    config=state.config,
                    settings=get_settings(state),
                )
            except Exception as exc:
                logging.exception("event merge module failed")
                state.mark_warn(
                    step,
                    f"event_calendar 병합 실패. fallback 병합을 사용합니다: {exc}",
                )

        if merged is None:
            merged = fallback_merge_events(state.events_auto, manual_events, manual_news_notes)

        state.events_merged = normalize_events_payload(merged)
        add_event_risk_flags(state)

        output_dir = state.project_root / "output"
        write_json(output_dir / OUTPUT_FILES["events_auto"], state.events_auto)
        write_json(output_dir / OUTPUT_FILES["events_merged"], state.events_merged)

        state.mark_ok(step)

    except Exception as exc:
        logging.exception("Event collection failed")
        state.events_auto = fallback_collect_auto_events(state)
        state.events_merged = fallback_merge_events(state.events_auto, load_manual_events(state), state.manual_news_notes)
        write_json(state.project_root / "output" / OUTPUT_FILES["events_auto"], state.events_auto)
        write_json(state.project_root / "output" / OUTPUT_FILES["events_merged"], state.events_merged)
        state.mark_warn(step, f"이벤트 수집/병합 실패: {exc}")


def normalize_events_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload

    if isinstance(payload, list):
        return {
            "events": payload,
            "events_today": [],
            "events_next_24h": [],
            "earnings_watchlist_7d": [],
            "manual_events": [],
            "risk_flags": [],
        }

    return {
        "events": [],
        "events_today": [],
        "events_next_24h": [],
        "earnings_watchlist_7d": [],
        "manual_events": [],
        "risk_flags": [],
    }


def fallback_collect_auto_events(state: PipelineState) -> dict[str, Any]:
    """
    최소 fallback:
    - API 키가 없거나 event_sources 모듈이 실패해도 빈 이벤트 구조를 생성
    - events_auto.json은 항상 생성
    """
    settings = get_settings(state)
    lookahead_days = int(settings.get("events", {}).get("lookahead_days", 30))
    today = date.today()
    return {
        "generated_at": state.generated_at,
        "date": today.isoformat(),
        "lookahead_days": lookahead_days,
        "events": [],
        "events_today": [],
        "events_next_24h": [],
        "earnings_watchlist_7d": [],
        "risk_flags": [],
        "data_quality_notes": [
            "자동 이벤트 fallback 사용: event_calendar/event_sources 또는 API 응답을 확인하세요."
        ],
    }


def load_manual_events(state: PipelineState) -> list[dict[str, Any]]:
    manual_config = state.config.get("manual_events", {})
    if isinstance(manual_config, dict):
        events = manual_config.get("manual_events", [])
    elif isinstance(manual_config, list):
        events = manual_config
    else:
        events = []

    normalized = []
    for item in events:
        if isinstance(item, dict):
            normalized.append(dict(item))
    return normalized


def fallback_merge_events(
    auto_events: dict[str, Any],
    manual_events: list[dict[str, Any]],
    manual_news_notes: str,
) -> dict[str, Any]:
    today = date.today().isoformat()

    auto_list = list(auto_events.get("events", []))
    merged_list = auto_list + manual_events

    events_today = []
    events_next_24h = []
    earnings_7d = []

    for event in merged_list:
        event_date = str(event.get("date") or event.get("reportDate") or "")
        event_type = str(event.get("type") or "").lower()
        risk_flag = str(event.get("risk_flag") or "")

        if event_date == today:
            events_today.append(event)

        if is_within_days(event_date, 1):
            events_next_24h.append(event)

        if event_type == "earnings" or "earnings" in risk_flag:
            if is_within_days(event_date, 7):
                earnings_7d.append(event)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "date": today,
        "events": merged_list,
        "events_today": events_today,
        "events_next_24h": events_next_24h,
        "earnings_watchlist_7d": earnings_7d,
        "manual_events": manual_events,
        "manual_news_notes": manual_news_notes,
        "risk_flags": [],
    }


def is_within_days(date_str: str, days: int) -> bool:
    try:
        event_date = datetime.fromisoformat(str(date_str)[:10]).date()
        today = date.today()
        return today <= event_date <= today + timedelta(days=days)
    except Exception:
        return False


def add_event_risk_flags(state: PipelineState) -> None:
    events = state.events_merged.get("events", [])
    today = date.today()

    risk_flags: list[str] = []
    ticker_flags: dict[str, list[str]] = {}

    for event in events:
        if not isinstance(event, dict):
            continue

        event_name = str(event.get("name") or event.get("event") or event.get("title") or "")
        event_type = str(event.get("type") or "").lower()
        impact = str(event.get("impact") or "").lower()
        ticker = normalize_ticker(event.get("ticker") or event.get("symbol"))
        event_date_raw = str(event.get("date") or event.get("reportDate") or "")[:10]

        try:
            event_date = datetime.fromisoformat(event_date_raw).date()
        except Exception:
            event_date = None

        high_impact = impact == "high" or any(keyword.lower() in event_name.lower() for keyword in HIGH_IMPACT_KEYWORDS)

        if event_date == today and high_impact:
            risk_flags.append("macro_high_today")

        if event_date is not None and today <= event_date <= today + timedelta(days=1) and high_impact:
            risk_flags.append("macro_high_next_24h")

        if event_date == today and "fomc" in event_name.lower():
            risk_flags.append("fomc_today")

        if event_date == today and "minutes" in event_name.lower():
            risk_flags.append("fomc_minutes_today")

        if ticker:
            if event_type == "earnings" or "earnings" in event_name.lower():
                ticker_flags.setdefault(ticker, [])
                if event_date == today:
                    ticker_flags[ticker].append("earnings_today")
                    risk_flags.append("earnings_today")
                elif event_date == today + timedelta(days=1):
                    ticker_flags[ticker].append("earnings_tomorrow")
                    risk_flags.append("earnings_tomorrow")
                elif event_date is not None and today <= event_date <= today + timedelta(days=7):
                    ticker_flags[ticker].append("earnings_within_7d")
                    risk_flags.append("earnings_within_7d")

            if high_impact:
                ticker_flags.setdefault(ticker, []).append("major_event_high_impact")

    manual_events = state.events_merged.get("manual_events", [])
    for event in manual_events:
        if isinstance(event, dict) and str(event.get("impact", "")).lower() == "high":
            risk_flags.append("manual_event_high")

    state.events_merged["risk_flags"] = sorted(set(risk_flags))
    state.events_merged["ticker_event_flags"] = {
        ticker: sorted(set(flags)) for ticker, flags in ticker_flags.items()
    }


# ============================================================
# Market regime
# ============================================================

def determine_market_regime_step(state: PipelineState) -> None:
    step = "market_regime"

    try:
        market_regime = import_optional_module("market_regime")
        fn = get_first_callable(
            market_regime,
            [
                "determine_market_regime",
                "calculate_market_regime",
                "classify_market_regime",
                "get_market_regime",
            ],
        )

        if fn is not None:
            try:
                result = smart_call(
                    fn,
                    indicators=state.indicators,
                    price_data=state.prices,
                    prices=state.prices,
                    events=state.events_merged,
                    event_flags=state.events_merged.get("risk_flags", []),
                    config=state.config,
                    settings=get_settings(state),
                )
                if isinstance(result, dict):
                    state.market_regime = result
                else:
                    state.market_regime = {"mode": str(result), "score": None, "summary": str(result)}
                state.mark_ok(step)
                return
            except Exception as exc:
                logging.exception("market_regime module failed")
                state.mark_warn(step, f"market_regime 모듈 실패. fallback 판정을 사용합니다: {exc}")

        state.market_regime = fallback_determine_market_regime(state.indicators, state.events_merged)
        state.mark_ok(step)

    except Exception as exc:
        logging.exception("Market regime failed")
        state.market_regime = fallback_determine_market_regime(state.indicators, state.events_merged)
        state.mark_warn(step, f"시장 모드 판정 실패: {exc}")


def fallback_determine_market_regime(
    indicators: dict[str, Any],
    events_merged: dict[str, Any],
) -> dict[str, Any]:
    score = 0
    positive: list[str] = []
    negative: list[str] = []

    spy = indicators.get("SPY", {})
    qqq = indicators.get("QQQ", {})
    iwm = indicators.get("IWM", {})
    smh = indicators.get("SMH", {})
    hyg = indicators.get("HYG", {})
    tlt = indicators.get("TLT", {})
    vix = indicators.get("^VIX", {})

    def add_positive(condition: bool, reason: str) -> None:
        nonlocal score
        if condition:
            score += 1
            positive.append(reason)

    def add_negative(condition: bool, reason: str) -> None:
        nonlocal score
        if condition:
            score -= 1
            negative.append(reason)

    add_positive(bool(spy.get("above_20dma")), "SPY가 20일선 위")
    add_positive(bool(qqq.get("above_20dma")), "QQQ가 20일선 위")
    add_positive(bool(spy.get("above_50dma")), "SPY가 50일선 위")
    add_positive(bool(qqq.get("above_50dma")), "QQQ가 50일선 위")
    add_positive(
        safe_float(qqq.get("relative_strength_vs_spy_5d"), 0) > 0,
        "QQQ가 SPY 대비 5일 상대강도 우위",
    )
    add_positive(
        compare_indicator_returns(smh, qqq) > 0,
        "SMH가 QQQ 대비 5일 상대강도 우위",
    )
    add_positive(safe_float(vix.get("change_pct"), 0) < 0, "VIX 전일 대비 하락")
    add_positive(bool(hyg.get("above_20dma")), "HYG가 20일선 위")

    add_negative(spy.get("above_50dma") is False, "SPY가 50일선 아래")
    add_negative(qqq.get("above_50dma") is False, "QQQ가 50일선 아래")
    add_negative(compare_indicator_returns(iwm, spy) < 0, "IWM이 SPY 대비 5일 상대강도 약세")
    add_negative(safe_float(vix.get("change_pct"), 0) >= 5, "VIX 전일 대비 5% 이상 상승")
    add_negative(vix.get("above_20dma") is True, "VIX가 20일선 위")
    add_negative(
        tlt.get("change_pct") is not None
        and qqq.get("change_pct") is not None
        and safe_float(tlt.get("change_pct"), 0) < 0
        and safe_float(qqq.get("change_pct"), 0) < 0,
        "TLT 약세와 QQQ 약세 동시 발생",
    )

    if score >= 5:
        mode = "Risk-On"
    elif score >= 2:
        mode = "Mild Risk-On"
    elif score >= -1:
        mode = "Neutral"
    elif score >= -4:
        mode = "Caution"
    else:
        mode = "Defensive"

    risk_flags = events_merged.get("risk_flags", [])
    event_overlay = "None"
    overlay_reasons: list[str] = []

    overlay_flag_set = {
        "macro_high_today",
        "macro_high_next_24h",
        "fomc_today",
        "fomc_minutes_today",
        "manual_event_high",
    }

    if any(flag in overlay_flag_set for flag in risk_flags):
        event_overlay = "Caution"
        overlay_reasons.append("고영향 이벤트 리스크 존재")

    if safe_float(vix.get("change_pct"), 0) >= 5:
        event_overlay = "Defensive Bias"
        overlay_reasons.append("VIX 급등")

    return {
        "mode": mode,
        "score": score,
        "event_overlay": event_overlay,
        "summary": f"{mode} / score {score}",
        "positive_evidence": positive,
        "negative_evidence": negative,
        "overlay_reasons": overlay_reasons,
    }


def compare_indicator_returns(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_return = safe_float(left.get("return_5d"), 0) or 0
    right_return = safe_float(right.get("return_5d"), 0) or 0
    return left_return - right_return


# ============================================================
# Watchlist ranking
# ============================================================
def build_events_for_ranker(events_payload: Any) -> list[dict[str, Any]]:
    """
    watchlist_ranker.py에 넘길 이벤트를 list[dict] 형태로 정리한다.

    watchlist_ranker는 보통:
        for event in events:
            event.get(...)
    형태를 기대하므로 events에는 dict 전체가 아니라 event dict 리스트만 넘겨야 한다.
    """
    if not events_payload:
        return []

    raw_items: list[Any] = []

    if isinstance(events_payload, list):
        raw_items.extend(events_payload)

    elif isinstance(events_payload, dict):
        for key in [
            "events",
            "auto_events",
            "economic_events",
            "earnings",
            "events_today",
            "events_next_24h",
            "earnings_watchlist_7d",
            "manual_events",
        ]:
            value = events_payload.get(key)
            if isinstance(value, list):
                raw_items.extend(value)

    result: list[dict[str, Any]] = []

    for item in raw_items:
        if isinstance(item, dict):
            result.append(dict(item))
        elif isinstance(item, str) and item.strip():
            result.append(
                {
                    "type": "note",
                    "name": item.strip(),
                    "impact": "low",
                    "source": "main_sanitized_string_event",
                }
            )

    # 중복 제거
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()

    for event in result:
        key = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)

    return deduped


def rank_watchlist_step(state: PipelineState) -> None:
    step = "watchlist_ranking"

    try:
        watchlist_ranker = import_optional_module("watchlist_ranker")
        fn = get_first_callable(
            watchlist_ranker,
            [
                "rank_watchlist",
                "build_watchlist_ranking",
                "rank_tickers",
                "calculate_watchlist_ranking",
            ],
        )

        watchlist = extract_watchlist_tickers(state.config)

        if fn is not None:
            try:
                events_for_ranker = build_events_for_ranker(state.events_merged)
                result = smart_call(
                    fn,
                    watchlist=watchlist,
                    tickers=watchlist,
                    indicators=state.indicators,
                    indicators_by_ticker=state.indicators,
                    price_data=state.prices,
                    prices=state.prices,
                    prices_by_ticker=state.prices,
                    market_regime=state.market_regime,

                    # 중요:
                    # rank_watchlist()의 events 인자에는 dict 전체가 아니라 list[dict]만 넘긴다.
                    events=events_for_ranker,

                    # 다른 모듈/시그니처 호환용으로는 전체 merged dict도 같이 제공한다.
                    events_merged=state.events_merged,
                    merged_events=state.events_merged,

                    event_flags=state.events_merged.get("ticker_event_flags", {}),
                    ticker_event_flags=state.events_merged.get("ticker_event_flags", {}),
                    config=state.config,
                    settings=get_settings(state),
                )
                state.rankings = normalize_rankings(result)
                state.mark_ok(step)
                return
            except Exception as exc:
                logging.exception("watchlist_ranker module failed")
                state.mark_warn(
                    step,
                    f"watchlist_ranker 모듈 실패. fallback 랭킹을 사용합니다: {exc}",
                )

        state.rankings = fallback_rank_watchlist(watchlist, state.indicators, state.events_merged)
        if not state.rankings:
            state.mark_warn(step, "관심종목 랭킹 결과가 비어 있습니다.")
        else:
            state.mark_ok(step)

    except Exception as exc:
        logging.exception("Watchlist ranking failed")
        state.rankings = []
        state.mark_warn(step, f"관심종목 랭킹 실패: {exc}")


def normalize_rankings(result: Any) -> list[dict[str, Any]]:
    if result is None:
        return []

    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]

    if isinstance(result, dict):
        for key in ["rankings", "watchlist_ranking", "items", "results"]:
            value = result.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        # grade별 dict일 경우 flatten
        flattened: list[dict[str, Any]] = []
        for grade, items in result.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        entry = dict(item)
                        entry.setdefault("grade", str(grade).upper())
                        flattened.append(entry)
                    else:
                        flattened.append({"ticker": normalize_ticker(item), "grade": str(grade).upper()})
        if flattened:
            return flattened

    if pd is not None and isinstance(result, pd.DataFrame):
        return [row.to_dict() for _, row in result.iterrows()]

    return []


def fallback_rank_watchlist(
    watchlist: list[str],
    indicators: dict[str, Any],
    events_merged: dict[str, Any],
) -> list[dict[str, Any]]:
    ticker_flags = events_merged.get("ticker_event_flags", {})
    vix = indicators.get("^VIX", {})
    vix_rising = safe_float(vix.get("change_pct"), 0) > 0

    rankings: list[dict[str, Any]] = []

    for ticker in watchlist:
        item = indicators.get(ticker, {})
        if not item:
            rankings.append(
                {
                    "ticker": ticker,
                    "grade": "D",
                    "score": 0,
                    "positive_reasons": [],
                    "negative_reasons": ["가격/지표 데이터 없음"],
                    "event_flags": ticker_flags.get(ticker, []),
                }
            )
            continue

        score = 0
        positive: list[str] = []
        negative: list[str] = []

        def pos(points: int, condition: bool, reason: str) -> None:
            nonlocal score
            if condition:
                score += points
                positive.append(reason)

        def neg(points: int, condition: bool, reason: str) -> None:
            nonlocal score
            if condition:
                score -= points
                negative.append(reason)

        pos(2, bool(item.get("above_20dma")), "종가가 20일선 위")
        pos(2, bool(item.get("above_50dma")), "종가가 50일선 위")
        pos(1, bool(item.get("above_200dma")), "종가가 200일선 위")
        pos(1, bool(item.get("dma20_above_dma50")), "20일선이 50일선 위")
        pos(1, bool(item.get("volume_above_20d_avg")), "거래량이 20일 평균보다 큼")
        pos(1, bool(item.get("near_20d_high")), "최근 20일 고점 근처")
        pos(
            1,
            safe_float(item.get("relative_strength_vs_spy_5d"), 0) > 0,
            "SPY 대비 최근 5일 상대강도 우위",
        )
        pos(
            1,
            safe_float(item.get("relative_strength_vs_qqq_5d"), 0) > 0,
            "QQQ 대비 최근 5일 상대강도 우위",
        )

        neg(2, item.get("above_50dma") is False, "종가가 50일선 아래")
        neg(2, item.get("above_200dma") is False, "종가가 200일선 아래")
        neg(
            1,
            bool(item.get("near_20d_low")),
            "최근 20일 저점 근처",
        )

        if vix_rising and ticker in {"TSLA", "COIN", "PLTR", "RBLX", "RKLB", "ASTS", "SNOW", "MDB", "NET"}:
            neg(1, True, "VIX 상승 중 고베타 종목")

        event_flags = ticker_flags.get(ticker, [])

        if "earnings_within_7d" in event_flags:
            neg(1, True, "주요 이벤트/어닝 7일 이내")

        if "earnings_today" in event_flags or "earnings_tomorrow" in event_flags:
            neg(2, True, "어닝 당일 또는 익일")

        if score >= 7:
            grade = "A"
        elif score >= 4:
            grade = "B"
        elif score >= 1:
            grade = "C"
        else:
            grade = "D"

        rankings.append(
            {
                "ticker": ticker,
                "grade": grade,
                "score": score,
                "close": item.get("close"),
                "change_pct": item.get("change_pct"),
                "positive_reasons": positive,
                "negative_reasons": negative,
                "event_flags": event_flags,
            }
        )

    rankings.sort(key=lambda x: (x.get("grade", "Z"), -int(x.get("score", 0)), x.get("ticker", "")))
    return rankings


# ============================================================
# Setup matcher
# ============================================================

def classify_setups_step(state: PipelineState) -> None:
    step = "setup_matching"

    try:
        setup_matcher = import_optional_module("setup_matcher")
        fn = get_first_callable(
            setup_matcher,
            [
                "classify_setups",
                "match_setups",
                "build_setup_candidates",
                "find_setup_candidates",
            ],
        )

        if fn is not None:
            try:
                result = smart_call(
                    fn,
                    rankings=state.rankings,
                    watchlist_ranking=state.rankings,
                    watchlist_rankings=state.rankings,
                    indicators=state.indicators,
                    indicators_by_ticker=state.indicators,
                    market_regime=state.market_regime,
                    events=state.events_merged,
                    events_merged=state.events_merged,
                    config=state.config,
                    settings=get_settings(state),
                )
                state.setups = normalize_setups(result)
                state.mark_ok(step)
                return
            except Exception as exc:
                logging.exception("setup_matcher module failed")
                state.mark_warn(
                    step,
                    f"setup_matcher 모듈 실패. fallback 셋업 분류를 사용합니다: {exc}",
                )

        state.setups = fallback_classify_setups(state.rankings, state.indicators, state.market_regime)
        state.mark_ok(step)

    except Exception as exc:
        logging.exception("Setup matching failed")
        state.setups = {"breakout": [], "pullback": [], "avoid": []}
        state.mark_warn(step, f"셋업 후보 분류 실패: {exc}")


def normalize_setups(result: Any) -> dict[str, list[dict[str, Any]]]:
    default = {"breakout": [], "pullback": [], "avoid": []}

    if isinstance(result, dict):
        normalized = dict(default)
        for key in ["breakout", "pullback", "avoid"]:
            value = result.get(key, [])
            if isinstance(value, list):
                normalized[key] = [
                    item if isinstance(item, dict) else {"ticker": normalize_ticker(item)}
                    for item in value
                ]
        return normalized

    return default


def fallback_classify_setups(
    rankings: list[dict[str, Any]],
    indicators: dict[str, Any],
    market_regime: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    mode = str(market_regime.get("mode", "Neutral"))
    defensive = mode == "Defensive"

    breakout: list[dict[str, Any]] = []
    pullback: list[dict[str, Any]] = []
    avoid: list[dict[str, Any]] = []

    for ranked in rankings:
        ticker = normalize_ticker(ranked.get("ticker"))
        item = indicators.get(ticker, {})
        grade = str(ranked.get("grade", ""))

        if not ticker:
            continue

        event_flags = ranked.get("event_flags", [])

        if (
            item.get("above_20dma") is True
            and item.get("above_50dma") is True
            and item.get("near_20d_high") is True
            and item.get("volume_above_20d_avg") is True
            and not defensive
            and grade in {"A", "B"}
        ):
            breakout.append(
                {
                    "ticker": ticker,
                    "grade": grade,
                    "reason": "20일선/50일선 위, 20일 고점 근처, 거래량 증가",
                    "event_flags": event_flags,
                }
            )

        if (
            item.get("above_50dma") is True
            and is_price_near_dma(item.get("close"), item.get("dma20"))
            and not defensive
            and grade in {"A", "B", "C"}
        ):
            pullback.append(
                {
                    "ticker": ticker,
                    "grade": grade,
                    "reason": "50일선 위, 20일선 근처 눌림 후보",
                    "event_flags": event_flags,
                }
            )

        if (
            item.get("above_50dma") is False
            or item.get("above_200dma") is False
            or item.get("near_20d_low") is True
            or defensive
            or grade == "D"
            or "earnings_today" in event_flags
            or "earnings_tomorrow" in event_flags
        ):
            avoid.append(
                {
                    "ticker": ticker,
                    "grade": grade,
                    "reason": "추세 훼손 또는 이벤트/시장 리스크",
                    "event_flags": event_flags,
                }
            )

    return {
        "breakout": breakout,
        "pullback": pullback,
        "avoid": avoid,
    }


def is_price_near_dma(close: Any, dma: Any, threshold_pct: float = 3.0) -> bool:
    c = safe_float(close)
    d = safe_float(dma)
    if c is None or d is None or d == 0:
        return False
    return abs((c / d - 1) * 100) <= threshold_pct


# ============================================================
# Risk engine
# ============================================================

def run_risk_engine_step(state: PipelineState) -> None:
    step = "risk_engine"

    try:
        risk_engine = import_optional_module("risk_engine")
        fn = get_first_callable(
            risk_engine,
            [
                "run_risk_engine",
                "build_risk_report",
                "evaluate_risks",
                "generate_risk_warnings",
            ],
        )

        if fn is not None:
            try:
                result = smart_call(
                    fn,
                    market_regime=state.market_regime,
                    events=state.events_merged,
                    events_merged=state.events_merged,
                    rankings=state.rankings,
                    watchlist_ranking=state.rankings,
                    watchlist_ranker_result=state.rankings,
                    setups=state.setups,
                    indicators=state.indicators,
                    indicators_by_ticker=state.indicators,
                    config=state.config,
                    rules=state.config.get("rules", {}),
                    settings=get_settings(state),
                    manual_news_notes=state.manual_news_notes,
                )
                state.risk = normalize_risk(result)
                state.mark_ok(step)
                return
            except Exception as exc:
                logging.exception("risk_engine module failed")
                state.mark_warn(
                    step,
                    f"risk_engine 모듈 실패. fallback 리스크 엔진을 사용합니다: {exc}",
                )

        state.risk = fallback_run_risk_engine(state)
        state.mark_ok(step)

    except Exception as exc:
        logging.exception("Risk engine failed")
        state.risk = fallback_run_risk_engine(state)
        state.mark_warn(step, f"리스크 엔진 실패: {exc}")


def normalize_risk(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        risk = dict(result)
    elif isinstance(result, list):
        risk = {"risk_warnings": result}
    else:
        risk = {}

    risk.setdefault("risk_warnings", [])
    risk.setdefault("do_not_do_list", REQUIRED_DO_NOT_DO)
    risk.setdefault("no_trade_flags", [])
    risk.setdefault("ticker_specific_risks", [])
    return risk


def fallback_run_risk_engine(state: PipelineState) -> dict[str, Any]:
    warnings: list[str] = []
    no_trade_flags: list[str] = []
    ticker_specific: list[dict[str, Any]] = []

    mode = str(state.market_regime.get("mode", "Neutral"))
    overlay = str(state.market_regime.get("event_overlay", "None"))
    event_flags = state.events_merged.get("risk_flags", [])

    if mode in {"Caution", "Defensive"}:
        warnings.append(f"시장 모드가 {mode}입니다. 신규 공격 매매를 제한하고 포지션 사이즈를 줄이세요.")

    if overlay in {"Caution", "Defensive Bias"}:
        warnings.append(f"이벤트 오버레이가 {overlay}입니다. 발표 전후 첫 반응 추격을 피하세요.")

    if "macro_high_today" in event_flags or "macro_high_next_24h" in event_flags:
        warnings.append("고영향 매크로 이벤트가 임박했거나 당일입니다. 이벤트 전후 과대 진입을 피하세요.")

    if "fomc_today" in event_flags or "fomc_minutes_today" in event_flags:
        warnings.append("FOMC 관련 이벤트 리스크가 있습니다. 방향성 확인 전 추격을 피하세요.")

    d_grade = [item for item in state.rankings if str(item.get("grade")) == "D"]
    if d_grade:
        warnings.append("D급 종목은 물타기 금지 및 반등 예측 금지 대상입니다.")

    for item in state.rankings:
        ticker = normalize_ticker(item.get("ticker"))
        flags = item.get("event_flags", [])
        grade = item.get("grade")

        risks = []
        if grade == "D":
            risks.append("D급 종목")
        if "earnings_within_7d" in flags:
            risks.append("어닝 7일 이내")
        if "earnings_today" in flags or "earnings_tomorrow" in flags:
            risks.append("어닝 당일/익일")

        if risks:
            ticker_specific.append(
                {
                    "ticker": ticker,
                    "risks": risks,
                    "grade": grade,
                }
            )

    cd_count = len([x for x in state.rankings if str(x.get("grade")) in {"C", "D"}])
    if mode == "Defensive":
        no_trade_flags.append("Defensive 모드")
    if "macro_high_today" in event_flags:
        no_trade_flags.append("High-impact macro event today")
    if state.rankings and cd_count >= max(1, int(len(state.rankings) * 0.6)):
        no_trade_flags.append("관심종목 대부분 C/D급")

    do_not_do = build_do_not_do_list(state.config.get("rules", {}))

    return {
        "risk_warnings": warnings,
        "do_not_do_list": do_not_do,
        "no_trade_flags": no_trade_flags,
        "ticker_specific_risks": ticker_specific,
    }


def build_do_not_do_list(rules: dict[str, Any]) -> list[str]:
    raw = []
    if isinstance(rules, dict):
        raw = rules.get("global_do_not_do", []) or []

    items: list[str] = []
    for entry in raw:
        if isinstance(entry, str):
            items.append(entry)
        elif isinstance(entry, dict):
            text = entry.get("text")
            if text:
                items.append(str(text))

    for item in REQUIRED_DO_NOT_DO:
        if item not in items:
            items.append(item)

    return items


# ============================================================
# Packet / prompt / telegram
# ============================================================

def build_outputs_step(state: PipelineState) -> None:
    step = "output_generation"
    output_dir = state.project_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        packet_payload = build_packet_payload(state)

        packet_builder = import_optional_module("packet_builder")
        build_packet_fn = get_first_callable(
            packet_builder,
            [
                "build_daily_packet",
                "render_daily_packet",
                "create_daily_packet",
            ],
        )

        daily_packet_md = None
        daily_packet_json = packet_payload

        if build_packet_fn is not None:
            try:
                built = smart_call(
                    build_packet_fn,
                    packet_payload=packet_payload,
                    payload=packet_payload,
                    state=state,
                    session=state.session,
                    config=state.config,
                    market_regime=state.market_regime,
                    events=state.events_merged,
                    rankings=state.rankings,
                    setups=state.setups,
                    risk=state.risk,
                    manual_news_notes=state.manual_news_notes,
                    data_quality_notes=state.data_quality_notes,
                )

                if isinstance(built, str):
                    daily_packet_md = built
                elif isinstance(built, dict):
                    daily_packet_md = built.get("markdown") or built.get("daily_packet_md")
                    daily_packet_json = built.get("json") or built.get("payload") or packet_payload
            except Exception as exc:
                logging.exception("packet_builder failed")
                state.mark_warn(
                    step,
                    f"packet_builder 실패. fallback Daily Packet을 사용합니다: {exc}",
                )

        if daily_packet_md is None:
            daily_packet_md = fallback_render_daily_packet(packet_payload)

        write_text(output_dir / OUTPUT_FILES["daily_packet_md"], daily_packet_md)
        write_json(output_dir / OUTPUT_FILES["daily_packet_json"], daily_packet_json)

        prompt_builder = import_optional_module("prompt_builder")

        prompt_gpt, prompt_claude = build_prompts_with_optional_module(
            prompt_builder=prompt_builder,
            packet_payload=packet_payload,
            daily_packet_md=daily_packet_md,
            state=state,
        )

        write_text(output_dir / OUTPUT_FILES["prompt_for_gpt"], prompt_gpt)
        write_text(output_dir / OUTPUT_FILES["prompt_for_claude"], prompt_claude)

        telegram_summary = fallback_render_telegram_summary(packet_payload)
        write_text(output_dir / OUTPUT_FILES["telegram_summary"], telegram_summary)

        state.mark_ok(step)

    except Exception as exc:
        logging.exception("Output generation serious failure")
        state.mark_fail(step, f"필수 산출물 생성 실패: {exc}", serious=True)


def build_packet_payload(state: PipelineState) -> dict[str, Any]:
    return {
        "date": state.run_date,
        "session": state.session,
        "generated_at": state.generated_at,
        "timezone": get_settings(state).get("session", {}),
        "market_regime": state.market_regime,
        "events": state.events_merged,
        "watchlist_ranking": state.rankings,
        "setup_candidates": state.setups,
        "risk": state.risk,
        "manual_news_notes": state.manual_news_notes,
        "data_quality_notes": state.data_quality_notes,
        "step_results": state.step_results,
    }


def _extract_today_news_notes(text: str, target_date: str) -> str:
    """
    Extract only the target_date section from manual_news_notes.md.
    Returns empty string if the section is not found.
    Supports ## YYYY-MM-DD and ### YYYY-MM-DD headers.
    """
    if not text.strip():
        return ""
    lines = text.splitlines()
    header_re = re.compile(r"^(#{2,6})\s+" + re.escape(target_date) + r"\s*$")
    section_re = re.compile(r"^#{2,6}\s+\S+")
    start: int | None = None
    for idx, line in enumerate(lines):
        if header_re.match(line.strip()):
            start = idx + 1
            break
    if start is None:
        return ""
    collected: list[str] = []
    for line in lines[start:]:
        if section_re.match(line.strip()):
            break
        collected.append(line)
    return "\n".join(collected).strip()


def fallback_render_daily_packet(payload: dict[str, Any]) -> str:
    market = payload.get("market_regime", {})
    events = payload.get("events", {})
    rankings = payload.get("watchlist_ranking", [])
    setups = payload.get("setup_candidates", {})
    risk = payload.get("risk", {})

    by_grade = {
        "A": [x for x in rankings if str(x.get("grade")) == "A"],
        "B": [x for x in rankings if str(x.get("grade")) == "B"],
        "C": [x for x in rankings if str(x.get("grade")) == "C"],
        "D": [x for x in rankings if str(x.get("grade")) == "D"],
    }

    lines: list[str] = []
    lines.append("# Personal Trading OS Daily Packet")
    lines.append("")
    lines.append(f"Date: {payload.get('date')}")
    lines.append(f"Session: {payload.get('session')}")
    lines.append(f"Generated At: {payload.get('generated_at')}")
    lines.append("")

    lines.append("## 1. Market Regime")
    lines.append("")
    lines.append(f"- Mode: {market.get('mode', 'Unknown')}")
    lines.append(f"- Score: {market.get('score', 'N/A')}")
    lines.append(f"- Event Overlay: {market.get('event_overlay', 'None')}")
    lines.append(f"- Summary: {market.get('summary', '')}")
    lines.append("")
    lines.append("### Positive Evidence")
    positive = market.get("positive_reasons") or market.get("positive_evidence") or []
    lines.extend(format_bullets(positive))
    lines.append("")
    lines.append("### Negative Evidence")
    negative = market.get("negative_reasons") or market.get("negative_evidence") or []
    lines.extend(format_bullets(negative))
    lines.append("")

    lines.append("## 2. Event Risk")
    lines.append("")
    lines.append("### Today")
    lines.extend(format_event_bullets(events.get("events_today", [])))
    lines.append("")
    lines.append("### Next 24 Hours")
    lines.extend(format_event_bullets(events.get("events_next_24h", [])))
    lines.append("")
    lines.append("### Watchlist Earnings Within 7 Days")
    lines.extend(format_event_bullets(events.get("earnings_watchlist_7d", [])))
    lines.append("")
    lines.append("### Manual Events")
    lines.extend(format_event_bullets(events.get("manual_events", [])))
    lines.append("")

    lines.append("## 3. Watchlist Ranking")
    for grade, title in [
        ("A", "A Grade - Priority Watch"),
        ("B", "B Grade - Secondary Watch"),
        ("C", "C Grade - Wait"),
        ("D", "D Grade - Avoid / Risk"),
    ]:
        lines.append("")
        lines.append(f"### {title}")
        lines.extend(format_ranking_bullets(by_grade[grade]))

    lines.append("")
    lines.append("## 4. Setup Candidates")
    for key, title in [
        ("breakout", "Breakout"),
        ("pullback", "Pullback"),
        ("avoid", "Avoid"),
    ]:
        lines.append("")
        lines.append(f"### {title}")
        lines.extend(format_setup_bullets(setups.get(key, [])))

    lines.append("")
    lines.append("## 5. Risk Warnings")
    lines.extend(format_bullets(risk.get("risk_warnings", [])))
    if risk.get("no_trade_flags"):
        lines.append("")
        lines.append("### No-trade / Observation Bias Flags")
        lines.extend(format_bullets(risk.get("no_trade_flags", [])))

    lines.append("")
    lines.append("## 6. Today's Do-Not-Do List")
    do_not_do = risk.get("do_not_do_list", REQUIRED_DO_NOT_DO)
    if do_not_do:
        for idx, item in enumerate(do_not_do, start=1):
            lines.append(f"{idx}. {item}")
    else:
        lines.append("- 없음")

    lines.append("")
    lines.append("## 7. Manual News Notes")
    raw_notes = str(payload.get("manual_news_notes") or "").strip()
    today_str = str(payload.get("date") or date.today().isoformat())[:10]
    notes = _extract_today_news_notes(raw_notes, today_str)
    if not notes:
        notes = "- 오늘 수동 뉴스 메모 없음"
    lines.append(notes)
    lines.append("")

    lines.append("## 8. Questions for GPT / Claude")
    lines.append("")
    lines.append("1. 오늘 시장 모드와 이벤트 리스크를 감안할 때 공격/방어 어느 쪽에 가까운가?")
    lines.append("2. A/B 등급 중 실제 차트와 뉴스 확인이 필요한 우선순위 종목은 무엇인가?")
    lines.append("3. D급 또는 Avoid 종목에서 피해야 할 행동은 무엇인가?")
    lines.append("")

    lines.append("## 9. Data Quality Notes")
    lines.extend(format_bullets(payload.get("data_quality_notes", [])))
    lines.append("")
    lines.append("### Step Results")
    step_results = payload.get("step_results", {})
    if step_results:
        for key, value in step_results.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- 없음")

    lines.append("")
    lines.append("---")
    lines.append("주의: 이 문서는 자동매매나 매수/매도 추천이 아니라 개인 트레이딩 운영 보조용입니다.")

    return "\n".join(lines)


def format_bullets(items: Any) -> list[str]:
    if not items:
        return ["- 없음"]
    if isinstance(items, str):
        return [f"- {items}"]
    if isinstance(items, list):
        return [f"- {item}" for item in items] or ["- 없음"]
    return [f"- {items}"]


def format_event_bullets(events: Any) -> list[str]:
    if not events:
        return ["- 없음"]

    lines = []
    for event in events:
        if not isinstance(event, dict):
            lines.append(f"- {event}")
            continue

        date_value = event.get("date") or event.get("reportDate") or ""
        time_value = event.get("time_et") or event.get("time") or ""
        ticker = event.get("ticker") or event.get("symbol") or ""
        name = event.get("name") or event.get("event") or event.get("title") or "Unnamed event"
        impact = event.get("impact") or ""
        source = event.get("source") or ""

        prefix = f"{date_value} {time_value}".strip()
        ticker_part = f" [{ticker}]" if ticker else ""
        impact_part = f" impact={impact}" if impact else ""
        source_part = f" source={source}" if source else ""

        lines.append(f"- {prefix}{ticker_part} {name}{impact_part}{source_part}".strip())

    return lines or ["- 없음"]


def format_ranking_bullets(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- 없음"]

    lines = []
    for item in items:
        ticker = item.get("ticker", "")
        score = item.get("score", "N/A")
        reasons = item.get("positive_reasons", [])
        negatives = item.get("negative_reasons", [])
        flags = item.get("event_flags", [])

        detail_parts = []
        if reasons:
            detail_parts.append("긍정: " + ", ".join(map(str, reasons[:3])))
        if negatives:
            detail_parts.append("주의: " + ", ".join(map(str, negatives[:3])))
        if flags:
            detail_parts.append("이벤트: " + ", ".join(map(str, flags)))

        detail = " / ".join(detail_parts)
        lines.append(f"- {ticker}: score={score}" + (f" | {detail}" if detail else ""))

    return lines


def format_setup_bullets(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["- 없음"]

    lines = []
    for item in items:
        ticker = item.get("ticker", "")
        reason = item.get("reason", "")
        grade = item.get("grade", "")
        flags = item.get("event_flags", [])
        flag_text = f" / flags={','.join(flags)}" if flags else ""
        grade_text = f" ({grade})" if grade else ""
        lines.append(f"- {ticker}{grade_text}: {reason}{flag_text}")
    return lines


def build_prompts_with_optional_module(
    prompt_builder: Any | None,
    packet_payload: dict[str, Any],
    daily_packet_md: str,
    state: PipelineState,
) -> tuple[str, str]:
    gpt_prompt = None
    claude_prompt = None

    if prompt_builder is not None:
        build_prompts_fn = get_first_callable(
            prompt_builder,
            ["build_prompts", "create_prompts", "generate_prompts"],
        )
        if build_prompts_fn is not None:
            try:
                result = smart_call(
                    build_prompts_fn,
                    packet_payload=packet_payload,
                    payload=packet_payload,
                    daily_packet=daily_packet_md,
                    daily_packet_md=daily_packet_md,
                    state=state,
                    config=state.config,
                )
                if isinstance(result, dict):
                    gpt_prompt = result.get("gpt") or result.get("prompt_for_gpt")
                    claude_prompt = result.get("claude") or result.get("prompt_for_claude")
                elif isinstance(result, tuple) and len(result) >= 2:
                    gpt_prompt = result[0]
                    claude_prompt = result[1]
            except Exception:
                logging.exception("prompt_builder.build_prompts failed")

        if gpt_prompt is None:
            gpt_fn = get_first_callable(
                prompt_builder,
                ["build_gpt_prompt", "create_gpt_prompt", "generate_gpt_prompt"],
            )
            if gpt_fn is not None:
                try:
                    gpt_prompt = smart_call(
                        gpt_fn,
                        packet_payload=packet_payload,
                        payload=packet_payload,
                        daily_packet=daily_packet_md,
                        daily_packet_md=daily_packet_md,
                        state=state,
                    )
                except Exception:
                    logging.exception("prompt_builder GPT prompt failed")

        if claude_prompt is None:
            claude_fn = get_first_callable(
                prompt_builder,
                ["build_claude_prompt", "create_claude_prompt", "generate_claude_prompt"],
            )
            if claude_fn is not None:
                try:
                    claude_prompt = smart_call(
                        claude_fn,
                        packet_payload=packet_payload,
                        payload=packet_payload,
                        daily_packet=daily_packet_md,
                        daily_packet_md=daily_packet_md,
                        state=state,
                    )
                except Exception:
                    logging.exception("prompt_builder Claude prompt failed")

    if not isinstance(gpt_prompt, str) or not gpt_prompt.strip():
        gpt_prompt = fallback_build_gpt_prompt(daily_packet_md)

    if not isinstance(claude_prompt, str) or not claude_prompt.strip():
        claude_prompt = fallback_build_claude_prompt(daily_packet_md)

    return gpt_prompt, claude_prompt


def fallback_build_gpt_prompt(daily_packet_md: str) -> str:
    return f"""너는 개인 미국 주식 트레이더의 장전/장마감 트레이딩 플랜 보조자다.

아래 Daily Packet만 근거로 오늘의 트레이딩 플랜을 작성하라.

규칙:
- 데이터에 없는 숫자, 가격, 뉴스, 날짜를 만들지 말 것.
- 매수/매도 단정 금지.
- 투자 조언처럼 표현하지 말 것.
- Bull / Neutral / Bear 시나리오로 나눌 것.
- 우선순위 종목과 피해야 할 종목을 구분할 것.
- 오늘 금지 행동을 명확히 표시할 것.
- SAVE/TradingView에서 확인해야 할 뉴스 항목을 따로 표시할 것.
- 추론은 추론이라고 표시할 것.

[Daily Packet]
{daily_packet_md}
"""


def fallback_build_claude_prompt(daily_packet_md: str) -> str:
    return f"""너는 개인 트레이더용 리스크 리뷰어다.

아래 Daily Packet 또는 이를 기반으로 생성된 트레이딩 플랜을 검토할 예정이다.
먼저 Daily Packet 자체를 기준으로 리스크 리뷰 체크리스트를 작성하라.

검토 기준:
1. 과잉확신 표현이 있는가?
2. 데이터에 없는 추정이 섞였는가?
3. 뉴스와 가격 움직임을 단정적으로 연결했는가?
4. 장초반 추격 위험이 있는가?
5. VIX/시장 모드/이벤트 리스크와 충돌하는 아이디어가 있는가?
6. D급 종목 물타기 또는 반등 예측 위험이 있는가?
7. 반대 시나리오는 무엇인가?
8. 보수적 체크리스트는 무엇인가?

주의:
- 매수/매도 추천을 하지 말 것.
- 데이터에 없는 사실을 만들지 말 것.
- 불확실한 항목은 확인 필요로 표시할 것.

[Daily Packet]
{daily_packet_md}
"""


def fallback_render_telegram_summary(packet_payload: dict[str, Any]) -> str:
    market = packet_payload.get("market_regime", {})
    rankings = packet_payload.get("watchlist_ranking", [])
    events = packet_payload.get("events", {})
    risk = packet_payload.get("risk", {})

    a_grade = [x.get("ticker") for x in rankings if str(x.get("grade")) == "A"]
    b_grade = [x.get("ticker") for x in rankings if str(x.get("grade")) == "B"]
    d_grade = [x.get("ticker") for x in rankings if str(x.get("grade")) == "D"]

    lines = [
        "🇺🇸 Personal Trading OS",
        "",
        f"Date: {packet_payload.get('date')}",
        f"Session: {packet_payload.get('session')}",
        "",
        "시장 모드:",
        f"- {market.get('mode', 'Unknown')}",
        f"- Event Overlay: {market.get('event_overlay', 'None')}",
        "",
        "우선 관찰:",
        f"A급: {', '.join(a_grade[:10]) if a_grade else '없음'}",
        f"B급: {', '.join(b_grade[:10]) if b_grade else '없음'}",
        "",
        "주의:",
        f"D급: {', '.join(d_grade[:10]) if d_grade else '없음'}",
        "",
        "이벤트 리스크:",
    ]

    _RISK_FLAG_KO = {
        "macro_high_today": "오늘 고임팩트 매크로 이벤트",
        "macro_high_next_24h": "24시간 내 고임팩트 매크로 이벤트",
        "fomc_today": "FOMC 이벤트 당일",
        "fomc_minutes_today": "FOMC Minutes 이벤트 당일",
        "manual_event_high": "수동 등록 고임팩트 이벤트",
        "earnings_today": "오늘 어닝 발표",
        "earnings_tomorrow": "내일 어닝 발표",
        "earnings_within_7d": "7일 내 어닝 발표",
    }
    risk_flags = events.get("risk_flags", [])
    if risk_flags:
        for flag in risk_flags[:10]:
            label = _RISK_FLAG_KO.get(str(flag), str(flag))
            lines.append(f"- {label}")
    else:
        lines.append("- 없음")

    lines.append("")
    lines.append("오늘 금지:")
    for idx, item in enumerate(risk.get("do_not_do_list", REQUIRED_DO_NOT_DO), start=1):
        lines.append(f"{idx}. {item}")

    lines.append("")
    lines.append("첨부:")
    lines.append("- daily_packet.md")
    lines.append("- prompt_for_gpt.txt")
    lines.append("- prompt_for_claude.txt")

    return "\n".join(lines)


def send_telegram_step(state: PipelineState) -> None:
    step = "telegram_send"

    try:
        settings = get_settings(state)
        telegram_settings = settings.get("telegram", {})
        if not telegram_settings.get("send_summary", True):
            state.mark_ok(step)
            return

        telegram_sender = import_optional_module("telegram_sender")
        fn = get_first_callable(
            telegram_sender,
            [
                "send_telegram_outputs",
                "send_daily_packet",
                "send_outputs",
                "send_telegram_summary",
            ],
        )

        output_dir = state.project_root / "output"
        summary_path = output_dir / OUTPUT_FILES["telegram_summary"]
        daily_packet_path = output_dir / OUTPUT_FILES["daily_packet_md"]
        gpt_prompt_path = output_dir / OUTPUT_FILES["prompt_for_gpt"]
        claude_prompt_path = output_dir / OUTPUT_FILES["prompt_for_claude"]

        if fn is not None:
            try:
                smart_call(
                    fn,
                    output_dir=output_dir,
                    summary_path=summary_path,
                    daily_packet_path=daily_packet_path,
                    gpt_prompt_path=gpt_prompt_path,
                    claude_prompt_path=claude_prompt_path,
                    config=state.config,
                    settings=settings,
                    session=state.session,
                )
                state.mark_ok(step)
                return
            except Exception as exc:
                logging.exception("telegram_sender module failed")
                state.mark_warn(
                    step,
                    f"telegram_sender 모듈 실패. fallback 전송을 시도합니다: {exc}",
                )

        fallback_send_telegram(
            summary_path=summary_path,
            document_paths=[
                daily_packet_path,
                gpt_prompt_path,
                claude_prompt_path,
            ],
            settings=settings,
        )
        state.mark_ok(step)

    except Exception as exc:
        logging.exception("Telegram send failed")
        state.mark_warn(step, f"Telegram 전송 실패: {exc}")


def fallback_send_telegram(
    summary_path: Path,
    document_paths: list[Path],
    settings: dict[str, Any],
) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        logging.info("Telegram token/chat_id missing. Summary file generated only.")
        return

    try:
        import requests
    except Exception as exc:
        logging.warning("requests is not available, skip Telegram send: %s", exc)
        return

    if summary_path.exists():
        text = summary_path.read_text(encoding="utf-8")
        for chunk in split_message(text, limit=3900):
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={
                    "chat_id": chat_id,
                    "text": chunk,
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
            response.raise_for_status()

    telegram_settings = settings.get("telegram", {})

    send_documents = [
        (telegram_settings.get("send_daily_packet", True), document_paths[0]),
        (telegram_settings.get("send_gpt_prompt", True), document_paths[1]),
        (telegram_settings.get("send_claude_prompt", True), document_paths[2]),
    ]

    for enabled, path in send_documents:
        if not enabled or not path.exists():
            continue

        with path.open("rb") as f:
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data={"chat_id": chat_id},
                files={"document": (path.name, f)},
                timeout=60,
            )
            response.raise_for_status()


def split_message(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text

    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


# ============================================================
# Main pipeline
# ============================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Personal Trading OS MVP")
    parser.add_argument(
        "--session",
        default="post_close",
        choices=["post_close", "pre_market"],
        help="Run session type",
    )
    parser.add_argument(
        "--project-root",
        default=str(DEFAULT_PROJECT_ROOT),
        help="Project root path. Default: parent folder of src",
    )
    return parser.parse_args(argv)


def run_pipeline(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root).resolve()
    session = args.session

    ensure_project_dirs(project_root)
    setup_logging(project_root, session)

    generated_at = datetime.now().isoformat(timespec="seconds")
    state = PipelineState(
        project_root=project_root,
        session=session,
        generated_at=generated_at,
        run_date=date.today().isoformat(),
    )

    logging.info("Running Personal Trading OS MVP session=%s", session)

    try:
        load_config_step(state)

        watchlist = extract_watchlist_tickers(state.config)
        all_data_tickers = state.config.get("all_tickers") or []

        logging.info("Watchlist tickers: %s", len(watchlist))
        logging.info("All data tickers: %s", len(all_data_tickers))
        logging.info("Watchlist ticker list: %s", ", ".join(watchlist))
        logging.info("All data ticker list: %s", ", ".join(all_data_tickers))

        collect_prices_step(state)
        calculate_indicators_step(state)
        collect_events_step(state)
        determine_market_regime_step(state)
        rank_watchlist_step(state)
        classify_setups_step(state)
        run_risk_engine_step(state)
        build_outputs_step(state)
        send_telegram_step(state)

        print_generated_files(project_root)

        if state.serious_failures:
            logging.error("Serious failures: %s", state.serious_failures)
            return 1

        return 0

    except Exception as exc:
        logging.error("Unhandled serious failure: %s", exc)
        logging.error(traceback.format_exc())

        try:
            state.mark_fail("unhandled", f"예상치 못한 심각한 실패: {exc}", serious=True)
            write_emergency_outputs(state)
        except Exception:
            logging.error("Emergency output generation failed")
            logging.error(traceback.format_exc())

        return 1


def write_emergency_outputs(state: PipelineState) -> None:
    output_dir = state.project_root / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_packet_payload(state)

    emergency_md = fallback_render_daily_packet(payload)
    write_text(output_dir / OUTPUT_FILES["daily_packet_md"], emergency_md)
    write_json(output_dir / OUTPUT_FILES["daily_packet_json"], payload)
    write_json(output_dir / OUTPUT_FILES["events_auto"], state.events_auto or {})
    write_json(output_dir / OUTPUT_FILES["events_merged"], state.events_merged or {})
    write_text(output_dir / OUTPUT_FILES["prompt_for_gpt"], fallback_build_gpt_prompt(emergency_md))
    write_text(output_dir / OUTPUT_FILES["prompt_for_claude"], fallback_build_claude_prompt(emergency_md))
    write_text(output_dir / OUTPUT_FILES["telegram_summary"], fallback_render_telegram_summary(payload))


def print_generated_files(project_root: Path) -> None:
    output_dir = project_root / "output"
    print("Generated files:")
    for filename in OUTPUT_FILES.values():
        path = output_dir / filename
        if path.exists():
            print(f"- output/{filename}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_pipeline(args)


if __name__ == "__main__":
    raise SystemExit(main())