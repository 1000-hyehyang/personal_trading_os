from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def project_path(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def ensure_project_dirs() -> None:
    for folder in ["config", "data", "output", "cache", "logs", "src", "tests", "docs"]:
        project_path(folder).mkdir(parents=True, exist_ok=True)


def load_yaml_file(relative_path: str, default: Any | None = None) -> Any:
    path = project_path(relative_path)

    if not path.exists():
        return default if default is not None else {}

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        return default if default is not None else {}

    return data


def load_text_file(relative_path: str, default: str = "") -> str:
    path = project_path(relative_path)

    if not path.exists():
        return default

    return path.read_text(encoding="utf-8")


def load_environment() -> dict[str, str]:
    env_path = project_path(".env")
    if env_path.exists():
        load_dotenv(env_path)

    return {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", ""),
        "ALPHAVANTAGE_API_KEY": os.getenv("ALPHAVANTAGE_API_KEY", ""),
        "FMP_API_KEY": os.getenv("FMP_API_KEY", ""),
        "DATA_PROVIDER": os.getenv("DATA_PROVIDER", "yfinance"),
        "EVENT_PROVIDER": os.getenv("EVENT_PROVIDER", "alpha_vantage_fmp_bls_fed"),
        "MOCK_MODE": os.getenv("MOCK_MODE", "true"),
    }


def load_all_config() -> dict[str, Any]:
    ensure_project_dirs()

    return {
        "watchlist": load_yaml_file("config/watchlist.yaml", default={}),
        "settings": load_yaml_file("config/settings.yaml", default={}),
        "rules": load_yaml_file("config/rules.yaml", default={}),
        "setups": load_yaml_file("config/setups.yaml", default={}),
        "events_manual": load_yaml_file("config/events_manual.yaml", default={"manual_events": []}),
        "manual_news_notes": load_text_file("data/manual_news_notes.md", default=""),
        "env": load_environment(),
    }


def get_all_tickers(watchlist_config: dict[str, Any]) -> list[str]:
    tickers: list[str] = []

    for key in ["market_core", "volatility", "rates_credit", "sectors", "watchlist"]:
        values = watchlist_config.get(key, [])
        if isinstance(values, list):
            tickers.extend(str(v).strip() for v in values if str(v).strip())

    seen = set()
    unique_tickers = []
    for ticker in tickers:
        if ticker not in seen:
            unique_tickers.append(ticker)
            seen.add(ticker)

    return unique_tickers