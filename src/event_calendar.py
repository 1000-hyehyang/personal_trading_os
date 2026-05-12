# src/event_calendar.py
"""
Event calendar orchestration for Personal Trading OS MVP.

Responsibilities:
- Load watchlist.yaml
- Load events_manual.yaml
- Collect automatic events
- Filter earnings to watchlist
- Merge auto + manual events
- Assign high/medium/low impact
- Create event risk flags
- Save output/events_auto.json
- Save output/events_merged.json

Usage:
    python src/event_calendar.py

From main.py later:
    from event_calendar import run_event_calendar
    result = run_event_calendar()
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from dateutil import parser as date_parser
from dotenv import load_dotenv

try:
    from event_sources import (
        SourceFetchResult,
        fetch_alpha_vantage_earnings,
        fetch_bls_calendar,
        fetch_fmp_economic_calendar,
        fetch_fomc_calendar,
        normalize_event,
    )
except ImportError:
    from src.event_sources import (  # type: ignore
        SourceFetchResult,
        fetch_alpha_vantage_earnings,
        fetch_bls_calendar,
        fetch_fmp_economic_calendar,
        fetch_fomc_calendar,
        normalize_event,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EASTERN_TZ = ZoneInfo("America/New_York")

# FIX: M-1
MACRO_LIKE_TYPES = {"macro", "fed"}

# FIX: M-3
TIME_SORT_OVERRIDE = {
    "before_open": "00:00",
    "after_close": "99:00",
    "manual": "99:30",
}

# FIX: H-4
MANUAL_EVENT_DATA_QUALITY_NOTES: list[str] = []

HIGH_IMPACT_KEYWORDS = [
    "cpi",
    "consumer price index",
    "ppi",
    "producer price index",
    "employment situation",
    "nonfarm payroll",
    "non-farm payroll",
    "payrolls",
    "fomc rate decision",
    "fomc decision",
    "fomc minutes",
    "pce price index",
    "personal consumption expenditures",
    "gdp",
    "gross domestic product",
]

MEDIUM_IMPACT_KEYWORDS = [
    "jolts",
    "job openings",
    "retail sales",
    "ism",
    "consumer confidence",
    "fed speaker",
    "treasury auction",
    "productivity and costs",
    "jobless claims",
    "durable goods",
    "housing starts",
    "existing home sales",
    "new home sales",
]

MEGA_CAP_WATCHLIST = {
    "NVDA",
    "MSFT",
    "AAPL",
    "AMZN",
    "META",
    "GOOGL",
    "GOOG",
    "TSLA",
    "AVGO",
}


def now_et() -> datetime:
    return datetime.now(EASTERN_TZ)


def today_et() -> date:
    return now_et().date()


def ensure_project_dirs(project_root: Path = PROJECT_ROOT) -> None:
    (project_root / "output").mkdir(parents=True, exist_ok=True)
    (project_root / "cache").mkdir(parents=True, exist_ok=True)


def read_yaml_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        return loaded if loaded is not None else default
    except Exception:
        return default


def load_settings(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    path = project_root / "config" / "settings.yaml"
    data = read_yaml_file(path, default={})
    return data if isinstance(data, dict) else {}


def load_watchlist(project_root: Path = PROJECT_ROOT) -> list[str]:
    """
    Load config/watchlist.yaml and return trading watchlist tickers.

    Supports both structures:

    1) Simple list:
        watchlist:
          - NVDA
          - AMD

    2) Categorized dict:
        watchlist:
          mega_cap_tech:
            - MSFT
            - AAPL
          semiconductors:
            - NVDA
            - AMD
    """
    path = project_root / "config" / "watchlist.yaml"
    data = read_yaml_file(path, default={})

    if not isinstance(data, dict):
        return []

    raw_watchlist = data.get("watchlist", [])

    tickers: list[str] = []

    if isinstance(raw_watchlist, list):
        for item in raw_watchlist:
            ticker = str(item).strip().upper()
            if ticker:
                tickers.append(ticker)

    elif isinstance(raw_watchlist, dict):
        # FIX: support categorized watchlist.yaml structure
        for _category, category_items in raw_watchlist.items():
            if not isinstance(category_items, list):
                continue

            for item in category_items:
                ticker = str(item).strip().upper()
                if ticker:
                    tickers.append(ticker)

    else:
        return []

    return sorted(set(tickers))


def load_manual_events(project_root: Path = PROJECT_ROOT) -> list[dict[str, Any]]:
    """
    Load config/events_manual.yaml and normalize manual_events.

    Supports:
    - ticker: "NVDA"
    - tickers: ["NVDA", "AMD"]

    For multiple tickers, only the first is used to preserve the existing
    single-ticker event schema.
    """
    # FIX: H-4
    MANUAL_EVENT_DATA_QUALITY_NOTES.clear()

    path = project_root / "config" / "events_manual.yaml"
    data = read_yaml_file(path, default={})

    if not isinstance(data, dict):
        return []

    raw_events = data.get("manual_events", [])
    if not isinstance(raw_events, list):
        return []

    events: list[dict[str, Any]] = []

    for raw in raw_events:
        if not isinstance(raw, dict):
            continue

        name = str(raw.get("name") or "").strip()

        # FIX: H-4
        ticker_value = raw.get("ticker")
        if not ticker_value:
            tickers_list = raw.get("tickers") or []
            if isinstance(tickers_list, list) and tickers_list:
                ticker_value = tickers_list[0]
                if len(tickers_list) > 1:
                    MANUAL_EVENT_DATA_QUALITY_NOTES.append(
                        f"events_manual.yaml: {name} has multiple tickers; only first used."
                    )

        event = normalize_event(
            event_type=str(raw.get("type") or "manual"),
            name=name,
            event_date=raw.get("date"),
            time_et=raw.get("time_et"),
            ticker=ticker_value,
            impact=raw.get("impact"),
            source="manual",
            note=raw.get("note"),
            raw=raw,
        )
        if not event:
            continue

        event["manual"] = True
        events.append(assign_event_impact(event))

    return events


def get_event_lookahead_days(settings: dict[str, Any]) -> int:
    try:
        return int(settings.get("events", {}).get("lookahead_days", 30))
    except Exception:
        return 30


def get_earnings_risk_window_days(settings: dict[str, Any]) -> int:
    try:
        return int(settings.get("events", {}).get("earnings_risk_window_days", 7))
    except Exception:
        return 7


def parse_event_date(event: dict[str, Any]) -> date | None:
    try:
        return date_parser.parse(str(event.get("date"))).date()
    except Exception:
        return None


def assign_event_impact(event: dict[str, Any]) -> dict[str, Any]:
    """
    Assign impact high/medium/low based on explicit impact plus keyword rules.
    """
    copied = dict(event)
    explicit = str(copied.get("impact") or "").lower().strip()

    if explicit in {"high", "medium", "low"}:
        base_impact = explicit
    else:
        base_impact = "low"

    name = str(copied.get("name") or "").lower()
    event_type = str(copied.get("type") or "").lower()
    ticker = str(copied.get("ticker") or "").upper().strip()

    if any(keyword in name for keyword in HIGH_IMPACT_KEYWORDS):
        copied["impact"] = "high"
        return copied

    if event_type == "earnings" and ticker in MEGA_CAP_WATCHLIST:
        copied["impact"] = "high"
        return copied

    if any(keyword in name for keyword in MEDIUM_IMPACT_KEYWORDS):
        copied["impact"] = "medium"
        return copied

    if event_type == "earnings":
        copied["impact"] = "medium"
        return copied

    copied["impact"] = base_impact if base_impact in {"high", "medium", "low"} else "low"
    return copied


# FIX: M-3
def _time_sort_key(value: Any) -> str:
    s = str(value or "").strip()
    return TIME_SORT_OVERRIDE.get(s.lower(), s or "99:59")


def sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(event: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            str(event.get("date") or ""),
            _time_sort_key(event.get("time_et")),
            str(event.get("type") or ""),
            str(event.get("ticker") or event.get("name") or ""),
        )

    return sorted(events, key=key)


def filter_relevant_events(
    events: list[dict[str, Any]],
    *,
    watchlist: list[str],
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """
    Filter:
    - earnings: watchlist only
    - macro/manual/fed: date range only
    """
    watchlist_set = {ticker.upper() for ticker in watchlist}
    filtered: list[dict[str, Any]] = []

    for event in events:
        event_date = parse_event_date(event)
        if not event_date:
            continue

        if event_date < start_date or event_date > end_date:
            continue

        event_type = str(event.get("type") or "").lower()
        ticker = str(event.get("ticker") or "").upper().strip()

        if event_type == "earnings":
            if ticker not in watchlist_set:
                continue

        filtered.append(assign_event_impact(event))

    return sort_events(filtered)


def dedupe_key(event: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(event.get("date") or "").strip(),
        str(event.get("type") or "").strip().lower(),
        str(event.get("ticker") or "").strip().upper(),
        str(event.get("name") or "").strip().lower(),
    )


def merge_auto_and_manual_events(
    auto_events: list[dict[str, Any]],
    manual_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Merge events with manual override priority.

    If same date/type/ticker/name exists, manual version wins.
    """
    merged_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for event in auto_events:
        merged_by_key[dedupe_key(event)] = assign_event_impact(event)

    for event in manual_events:
        merged_by_key[dedupe_key(event)] = assign_event_impact(event)

    return sort_events(list(merged_by_key.values()))


def _event_is_high_macro_today(event: dict[str, Any], current_date: date) -> bool:
    event_date = parse_event_date(event)

    # FIX: M-1
    return (
        event_date == current_date
        and str(event.get("type") or "").lower() in MACRO_LIKE_TYPES
        and str(event.get("impact") or "").lower() == "high"
    )


def _event_is_high_macro_next_24h(event: dict[str, Any], current_date: date) -> bool:
    event_date = parse_event_date(event)

    # FIX: M-1
    return (
        event_date is not None
        and current_date <= event_date <= current_date + timedelta(days=1)
        and str(event.get("type") or "").lower() in MACRO_LIKE_TYPES
        and str(event.get("impact") or "").lower() == "high"
    )


def create_event_risk_flags(
    events: list[dict[str, Any]],
    *,
    current_date: date | None = None,
    earnings_window_days: int = 7,
) -> dict[str, Any]:
    """
    Create portfolio-level and ticker-level event flags.
    Also mutates returned event copies with risk_flag/event_flags where useful.
    """
    current_date = current_date or today_et()

    flags: dict[str, Any] = {
        "macro_high_today": False,
        "macro_high_next_24h": False,
        "fomc_today": False,
        "fomc_minutes_today": False,
        "earnings_today": [],
        "earnings_tomorrow": [],
        "earnings_within_7d": [],
        "manual_event_high": False,
    }

    enriched_events: list[dict[str, Any]] = []

    for original in events:
        event = dict(original)
        event_flags: list[str] = []

        event_date = parse_event_date(event)
        event_type = str(event.get("type") or "").lower()
        name = str(event.get("name") or "").lower()
        impact = str(event.get("impact") or "").lower()
        ticker = str(event.get("ticker") or "").upper().strip()

        if _event_is_high_macro_today(event, current_date):
            flags["macro_high_today"] = True
            event_flags.append("macro_high_today")

        if _event_is_high_macro_next_24h(event, current_date):
            flags["macro_high_next_24h"] = True
            event_flags.append("macro_high_next_24h")

        if event_date == current_date and "fomc" in name and "minutes" not in name:
            flags["fomc_today"] = True
            event_flags.append("fomc_today")

        if event_date == current_date and "fomc minutes" in name:
            flags["fomc_minutes_today"] = True
            event_flags.append("fomc_minutes_today")

        if (
            event.get("manual") is True
            and event_date == current_date
            and impact == "high"
        ):
            flags["manual_event_high"] = True
            event_flags.append("manual_event_high")

        if event_type == "earnings" and ticker and event_date:
            delta_days = (event_date - current_date).days

            if delta_days == 0:
                flags["earnings_today"].append(ticker)
                event_flags.append("earnings_today")

            if delta_days == 1:
                flags["earnings_tomorrow"].append(ticker)
                event_flags.append("earnings_tomorrow")

            if 0 <= delta_days <= earnings_window_days:
                item = {
                    "ticker": ticker,
                    "date": event["date"],
                    "days_until": delta_days,
                    "impact": event.get("impact", "medium"),
                    "source": event.get("source", "unknown"),
                }
                flags["earnings_within_7d"].append(item)
                event_flags.append("earnings_within_7d")
                event["earnings_within_7d"] = True
                event["days_until_earnings"] = delta_days
                event["risk_flag"] = "earnings_within_7d"

        if event_flags:
            event["event_flags"] = sorted(set(event_flags))

        enriched_events.append(event)

    flags["earnings_today"] = sorted(set(flags["earnings_today"]))
    flags["earnings_tomorrow"] = sorted(set(flags["earnings_tomorrow"]))

    unique_earnings: dict[str, dict[str, Any]] = {}
    for item in flags["earnings_within_7d"]:
        unique_earnings[item["ticker"]] = item

    flags["earnings_within_7d"] = sorted(
        unique_earnings.values(),
        key=lambda x: (x["days_until"], x["ticker"]),
    )

    flags["events_enriched"] = sort_events(enriched_events)
    return flags


def _combine_fetch_results(
    results: list[SourceFetchResult],
) -> tuple[list[dict[str, Any]], list[str], dict[str, str]]:
    events: list[dict[str, Any]] = []
    notes: list[str] = []
    status: dict[str, str] = {}

    for result in results:
        events.extend(result.events)
        notes.extend(result.data_quality_notes)
        status.update(result.source_status)

    return events, notes, status


def collect_auto_events(
    *,
    project_root: Path = PROJECT_ROOT,
    watchlist: list[str] | None = None,
    current_date: date | None = None,
    lookahead_days: int | None = None,
) -> dict[str, Any]:
    """
    Collect automatic earnings and macro events.

    FMP logic:
    - If FMP_API_KEY exists and succeeds, use FMP macro events.
    - If FMP_API_KEY is missing or FMP fails/no events, use BLS + Fed fallback.
    - FMP status and notes are always retained.
    """
    ensure_project_dirs(project_root)

    load_dotenv(project_root / ".env")

    settings = load_settings(project_root)
    resolved_watchlist = watchlist or load_watchlist(project_root)
    current_date = current_date or today_et()
    lookahead_days = lookahead_days or get_event_lookahead_days(settings)
    end_date = current_date + timedelta(days=lookahead_days)

    alpha_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
    fmp_key = os.getenv("FMP_API_KEY", "").strip()

    data_quality_notes: list[str] = []
    source_status: dict[str, str] = {}

    earnings_result = fetch_alpha_vantage_earnings(alpha_key, horizon="3month")

    fmp_result = fetch_fmp_economic_calendar(
        fmp_key,
        start_date=current_date,
        end_date=end_date,
    )

    use_fallback = (
        not fmp_key
        or fmp_result.source_status.get("fmp_economic_calendar")
        not in {"ok", "ok_no_events"}
        or len(fmp_result.events) == 0
    )

    fallback_results: list[SourceFetchResult] = []

    if use_fallback:
        if fmp_key:
            data_quality_notes.append(
                "FMP unavailable or empty; using BLS and Fed FOMC fallback."
            )
        else:
            data_quality_notes.append(
                "FMP_API_KEY empty; using BLS and Fed FOMC fallback."
            )

        fallback_results = [
            fetch_bls_calendar(start_date=current_date, end_date=end_date),
            fetch_fomc_calendar(start_date=current_date, end_date=end_date),
        ]

    combined_results = [earnings_result]

    # FIX: H-3
    if not use_fallback:
        combined_results.append(fmp_result)
    else:
        combined_results.extend(fallback_results)

    raw_events, notes, status = _combine_fetch_results(combined_results)
    data_quality_notes.extend(notes)
    source_status.update(status)

    # FIX: H-3
    data_quality_notes.extend(fmp_result.data_quality_notes)
    source_status.update(fmp_result.source_status)

    filtered_events = filter_relevant_events(
        raw_events,
        watchlist=resolved_watchlist,
        start_date=current_date,
        end_date=end_date,
    )

    earnings_window_days = get_earnings_risk_window_days(settings)
    risk_flags = create_event_risk_flags(
        filtered_events,
        current_date=current_date,
        earnings_window_days=earnings_window_days,
    )
    enriched_events = risk_flags.pop("events_enriched")

    return {
        "generated_at": now_et().isoformat(),
        "as_of_date": current_date.isoformat(),
        "lookahead_days": lookahead_days,
        "watchlist": resolved_watchlist,
        "events": enriched_events,
        "risk_flags": risk_flags,
        "data_quality_notes": sorted(set(data_quality_notes)),
        "source_status": source_status,
    }


def build_events_merged_payload(
    *,
    auto_payload: dict[str, Any],
    manual_events: list[dict[str, Any]],
    current_date: date | None = None,
    earnings_window_days: int = 7,
) -> dict[str, Any]:
    current_date = current_date or today_et()

    auto_events = auto_payload.get("events", [])
    if not isinstance(auto_events, list):
        auto_events = []

    merged_events = merge_auto_and_manual_events(auto_events, manual_events)

    risk_flags = create_event_risk_flags(
        merged_events,
        current_date=current_date,
        earnings_window_days=earnings_window_days,
    )
    enriched_events = risk_flags.pop("events_enriched")

    data_quality_notes = list(auto_payload.get("data_quality_notes", []))

    # FIX: H-4
    data_quality_notes.extend(MANUAL_EVENT_DATA_QUALITY_NOTES)

    if not manual_events:
        data_quality_notes.append("No manual events loaded from config/events_manual.yaml.")

    return {
        "generated_at": now_et().isoformat(),
        "as_of_date": auto_payload.get("as_of_date", current_date.isoformat()),
        "lookahead_days": auto_payload.get("lookahead_days"),
        "watchlist": auto_payload.get("watchlist", []),
        "events": enriched_events,
        "risk_flags": risk_flags,
        "data_quality_notes": sorted(set(data_quality_notes)),
        "source_status": auto_payload.get("source_status", {}),
    }


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)


def save_events_auto_json(
    payload: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
) -> Path:
    path = project_root / "output" / "events_auto.json"
    save_json(path, payload)
    return path


def save_events_merged_json(
    payload: dict[str, Any],
    *,
    project_root: Path = PROJECT_ROOT,
) -> Path:
    path = project_root / "output" / "events_merged.json"
    save_json(path, payload)
    return path


def run_event_calendar(
    *,
    project_root: Path = PROJECT_ROOT,
    current_date: date | None = None,
) -> dict[str, Any]:
    """
    Main entry point for src/main.py.

    Returns:
        {
          "events_auto_path": "...",
          "events_merged_path": "...",
          "events_auto": {...},
          "events_merged": {...}
        }
    """
    ensure_project_dirs(project_root)

    settings = load_settings(project_root)
    earnings_window_days = get_earnings_risk_window_days(settings)

    auto_payload = collect_auto_events(
        project_root=project_root,
        current_date=current_date,
    )
    auto_path = save_events_auto_json(auto_payload, project_root=project_root)

    manual_events = load_manual_events(project_root)
    merged_payload = build_events_merged_payload(
        auto_payload=auto_payload,
        manual_events=manual_events,
        current_date=current_date,
        earnings_window_days=earnings_window_days,
    )
    merged_path = save_events_merged_json(merged_payload, project_root=project_root)

    return {
        "events_auto_path": str(auto_path),
        "events_merged_path": str(merged_path),
        "events_auto": auto_payload,
        "events_merged": merged_payload,
    }


def main() -> int:
    result = run_event_calendar()
    merged = result["events_merged"]

    print("Event calendar completed.")
    print(f"events_auto:   {result['events_auto_path']}")
    print(f"events_merged: {result['events_merged_path']}")
    print(f"events_count:  {len(merged.get('events', []))}")
    print(f"risk_flags:    {json.dumps(merged.get('risk_flags', {}), ensure_ascii=False)}")

    notes = merged.get("data_quality_notes", [])
    if notes:
        print("data_quality_notes:")
        for note in notes:
            print(f"- {note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())