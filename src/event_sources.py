# src/event_sources.py
"""
External event source collectors for Personal Trading OS MVP.

Responsibilities:
- Alpha Vantage EARNINGS_CALENDAR
- FMP Economic Calendar
- BLS Schedule of Selected Releases fallback
- Federal Reserve FOMC calendar fallback
- Event normalization

Design goals:
- Never crash the whole program on API failure.
- Return normalized events plus data_quality_notes.
- Avoid storing or logging API keys.
"""

from __future__ import annotations

import csv
import io
import json  # FIX: H-1
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


EASTERN_TZ = ZoneInfo("America/New_York")

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"

FMP_STABLE_ECONOMIC_CALENDAR_URL = (
    "https://financialmodelingprep.com/stable/economic-calendar"
)
FMP_V3_ECONOMIC_CALENDAR_URL = (
    "https://financialmodelingprep.com/api/v3/economic_calendar"
)

BLS_CURRENT_YEAR_SCHEDULE_URL = (
    "https://www.bls.gov/schedule/news_release/current_year.asp"
)

FED_FOMC_CALENDAR_URL = (
    "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
)

SPECIAL_TIME_STRINGS = {
    "after_close",
    "before_open",
    "manual",
    "unknown",
    "tbd",
}


@dataclass
class SourceFetchResult:
    events: list[dict[str, Any]]
    data_quality_notes: list[str]
    source_status: dict[str, str]


def today_et() -> date:
    return datetime.now(EASTERN_TZ).date()


def normalize_date(value: Any) -> str | None:
    """Normalize date-like values into YYYY-MM-DD."""
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, datetime):
        return value.date().isoformat()

    text = str(value).strip()
    if not text:
        return None

    try:
        return date_parser.parse(text, fuzzy=True).date().isoformat()
    except Exception:
        return None


def normalize_time_et(value: Any) -> str | None:
    """
    Normalize time into HH:MM where possible.

    Preserves intentional event-time labels:
    - before_open
    - after_close
    - manual
    - unknown
    - tbd
    """
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    lowered = text.lower()

    # FIX: L-3
    if lowered in SPECIAL_TIME_STRINGS:
        return lowered

    if lowered in {"na", "n/a", "none", "-", "--"}:
        return None

    try:
        parsed = date_parser.parse(text, fuzzy=True)
        return parsed.strftime("%H:%M")
    except Exception:
        # FIX: L-3
        return None


def normalize_impact(value: Any) -> str:
    text = str(value or "").strip().lower()

    if text in {"high", "h", "3", "red"}:
        return "high"
    if text in {"medium", "med", "m", "2", "orange"}:
        return "medium"
    if text in {"low", "l", "1", "green"}:
        return "low"

    return "low"


def normalize_event(
    *,
    event_type: str,
    name: str,
    event_date: Any,
    source: str,
    time_et: Any = None,
    ticker: str | None = None,
    impact: str | None = None,
    note: str | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Convert any source event into a stable project schema.
    Returns None if required fields cannot be normalized.
    """
    normalized_date = normalize_date(event_date)
    normalized_name = str(name or "").strip()

    if not normalized_date or not normalized_name:
        return None

    event: dict[str, Any] = {
        "date": normalized_date,
        "time_et": normalize_time_et(time_et),
        "type": event_type,
        "name": normalized_name,
        "impact": normalize_impact(impact),
        "source": source,
    }

    if ticker:
        event["ticker"] = str(ticker).upper().strip()

    if note:
        event["note"] = str(note).strip()

    if raw:
        event["raw"] = {
            str(k): v
            for k, v in raw.items()
            if k
            in {
                "symbol",
                "ticker",
                "reportDate",
                "fiscalDateEnding",
                "estimate",
                "currency",
                "country",
                "event",
                "name",
                "date",
                "time",
                "impact",
            }
        }

    return event


def _safe_get_text(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 20,
    headers: dict[str, str] | None = None,
) -> tuple[str | None, str | None]:
    try:
        response = requests.get(
            url,
            params=params,
            timeout=timeout,
            headers=headers or {"User-Agent": "PersonalTradingOS/1.0"},
        )
        response.raise_for_status()
        return response.text, None
    except Exception as exc:
        return None, f"GET failed for {url}: {exc.__class__.__name__}: {exc}"


def _safe_get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 20,
) -> tuple[Any | None, str | None]:
    text, err = _safe_get_text(url, params=params, timeout=timeout)
    if err:
        return None, err

    if text is None:
        return None, f"JSON fetch returned no text for {url}"

    try:
        # FIX: H-1
        return json.loads(text), None
    except Exception as exc:
        return None, f"JSON parse failed for {url}: {exc.__class__.__name__}: {exc}"


def fetch_alpha_vantage_earnings(
    api_key: str | None,
    *,
    horizon: str = "3month",
    timeout: int = 20,
) -> SourceFetchResult:
    """
    Fetch Alpha Vantage EARNINGS_CALENDAR CSV.

    Alpha Vantage returns CSV with fields commonly like:
    symbol,name,reportDate,fiscalDateEnding,estimate,currency
    """
    notes: list[str] = []
    status: dict[str, str] = {"alpha_vantage_earnings": "not_started"}

    if not api_key:
        notes.append("Alpha Vantage skipped: ALPHAVANTAGE_API_KEY is empty.")
        status["alpha_vantage_earnings"] = "skipped_missing_api_key"
        return SourceFetchResult([], notes, status)

    params = {
        "function": "EARNINGS_CALENDAR",
        "horizon": horizon,
        "apikey": api_key,
    }

    text, err = _safe_get_text(ALPHA_VANTAGE_URL, params=params, timeout=timeout)
    if err:
        notes.append(f"Alpha Vantage earnings fetch failed: {err}")
        status["alpha_vantage_earnings"] = "failed_http"
        return SourceFetchResult([], notes, status)

    # FIX: H-2
    if text is None:
        notes.append("Alpha Vantage earnings fetch returned no response text.")
        status["alpha_vantage_earnings"] = "failed_no_response_text"
        return SourceFetchResult([], notes, status)

    stripped = text.strip()

    if not stripped:
        notes.append("Alpha Vantage earnings response was empty.")
        status["alpha_vantage_earnings"] = "failed_empty_response"
        return SourceFetchResult([], notes, status)

    suspicious_markers = [
        "Error Message",
        "Thank you for using Alpha Vantage",
        "Our standard API rate limit",
        "Invalid API call",
        "\"Information\"",
        "\"Note\"",
    ]
    if any(marker in stripped for marker in suspicious_markers):
        notes.append(
            "Alpha Vantage earnings response looked like an error/rate-limit message."
        )
        status["alpha_vantage_earnings"] = "failed_api_message"
        return SourceFetchResult([], notes, status)

    try:
        reader = csv.DictReader(io.StringIO(stripped))
        rows = list(reader)
    except Exception as exc:
        notes.append(f"Alpha Vantage CSV parse failed: {exc.__class__.__name__}: {exc}")
        status["alpha_vantage_earnings"] = "failed_csv_parse"
        return SourceFetchResult([], notes, status)

    events: list[dict[str, Any]] = []

    for row in rows:
        ticker = (row.get("symbol") or row.get("ticker") or "").strip().upper()
        company_name = (row.get("name") or ticker).strip()
        report_date = row.get("reportDate") or row.get("date")

        event = normalize_event(
            event_type="earnings",
            name=f"{ticker} Earnings" if ticker else f"{company_name} Earnings",
            event_date=report_date,
            source="Alpha Vantage",
            ticker=ticker or None,
            impact="medium",
            note="Alpha Vantage EARNINGS_CALENDAR",
            raw=row,
        )

        if not event:
            continue

        if company_name:
            event["company_name"] = company_name

        if row.get("fiscalDateEnding"):
            event["fiscal_date_ending"] = row.get("fiscalDateEnding")

        if row.get("estimate"):
            event["estimated_eps"] = row.get("estimate")

        if row.get("currency"):
            event["currency"] = row.get("currency")

        event["timing"] = "unknown"
        events.append(event)

    status["alpha_vantage_earnings"] = "ok" if events else "ok_no_events"
    return SourceFetchResult(events, notes, status)


def fetch_fmp_economic_calendar(
    api_key: str | None,
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    timeout: int = 20,
) -> SourceFetchResult:
    """
    Fetch FMP Economic Calendar.

    Uses stable endpoint first, then falls back to legacy api/v3 endpoint.
    """
    notes: list[str] = []
    status: dict[str, str] = {"fmp_economic_calendar": "not_started"}

    if not api_key:
        notes.append("FMP skipped: FMP_API_KEY is empty.")
        status["fmp_economic_calendar"] = "skipped_missing_api_key"
        return SourceFetchResult([], notes, status)

    start = normalize_date(start_date) or today_et().isoformat()
    end = normalize_date(end_date) or (today_et() + timedelta(days=30)).isoformat()

    endpoint_attempts = [
        FMP_STABLE_ECONOMIC_CALENDAR_URL,
        FMP_V3_ECONOMIC_CALENDAR_URL,
    ]

    last_error: str | None = None
    payload: Any | None = None

    for url in endpoint_attempts:
        params = {
            "from": start,
            "to": end,
            "apikey": api_key,
        }
        payload, err = _safe_get_json(url, params=params, timeout=timeout)
        if err:
            last_error = err
            continue

        if isinstance(payload, dict) and (
            payload.get("Error Message")
            or payload.get("error")
            or payload.get("message")
        ):
            last_error = f"FMP API message: {payload}"
            continue

        if isinstance(payload, list):
            break

        last_error = f"Unexpected FMP payload type from {url}: {type(payload).__name__}"

    if not isinstance(payload, list):
        notes.append(f"FMP economic calendar failed: {last_error or 'unknown error'}")
        status["fmp_economic_calendar"] = "failed"
        return SourceFetchResult([], notes, status)

    events: list[dict[str, Any]] = []

    for row in payload:
        if not isinstance(row, dict):
            continue

        country = str(row.get("country") or row.get("Country") or "").strip()
        if country and country.upper() not in {"US", "USA", "UNITED STATES"}:
            continue

        name = (
            row.get("event")
            or row.get("name")
            or row.get("title")
            or row.get("indicator")
            or ""
        )
        raw_date = row.get("date") or row.get("datetime")
        time_value = row.get("time")

        if raw_date and not time_value:
            try:
                parsed_dt = date_parser.parse(str(raw_date))
                time_value = parsed_dt.strftime("%H:%M")
            except Exception:
                time_value = None

        event = normalize_event(
            event_type="macro",
            name=str(name),
            event_date=raw_date,
            time_et=time_value,
            impact=row.get("impact") or row.get("importance"),
            source="FMP",
            note="FMP Economic Calendar",
            raw=row,
        )
        if event:
            events.append(event)

    status["fmp_economic_calendar"] = "ok" if events else "ok_no_events"
    return SourceFetchResult(events, notes, status)


def fetch_bls_calendar(
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    timeout: int = 20,
) -> SourceFetchResult:
    """
    Fetch BLS Schedule of Selected Releases.

    This is a fallback source for CPI, PPI, Employment Situation,
    JOLTS and related official BLS release dates.
    """
    notes: list[str] = []
    status: dict[str, str] = {"bls_calendar": "not_started"}

    start = date_parser.parse(normalize_date(start_date) or today_et().isoformat()).date()
    end = date_parser.parse(
        normalize_date(end_date) or (today_et() + timedelta(days=30)).isoformat()
    ).date()

    text, err = _safe_get_text(BLS_CURRENT_YEAR_SCHEDULE_URL, timeout=timeout)
    if err:
        notes.append(f"BLS calendar fetch failed: {err}")
        status["bls_calendar"] = "failed_http"
        return SourceFetchResult([], notes, status)

    # FIX: H-2
    if text is None:
        notes.append("BLS calendar fetch returned no response text.")
        status["bls_calendar"] = "failed_no_response_text"
        return SourceFetchResult([], notes, status)

    try:
        soup = BeautifulSoup(text, "lxml")
    except Exception:
        soup = BeautifulSoup(text, "html.parser")

    events: list[dict[str, Any]] = []

    for row in soup.find_all("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue

        joined = " | ".join(cells)

        parsed_date: date | None = None
        parsed_time: str | None = None
        release_name: str | None = None

        for cell in cells:
            try:
                candidate = date_parser.parse(cell, fuzzy=True).date()
                if candidate.year >= 2020:
                    parsed_date = candidate
                    break
            except Exception:
                continue

        if not parsed_date:
            continue

        for cell in cells:
            if re.search(r"\b\d{1,2}:\d{2}\s*(AM|PM)\b", cell, flags=re.I):
                parsed_time = normalize_time_et(cell)
                break

        possible_names = []
        for cell in cells:
            if cell == parsed_time:
                continue
            try:
                date_parser.parse(cell, fuzzy=True).date()
                continue
            except Exception:
                pass
            if len(cell) > 3:
                possible_names.append(cell)

        if possible_names:
            release_name = max(possible_names, key=len)

        if not release_name:
            release_name = joined

        if not (start <= parsed_date <= end):
            continue

        event = normalize_event(
            event_type="macro",
            name=release_name,
            event_date=parsed_date,
            time_et=parsed_time,
            impact="medium",
            source="BLS",
            note="BLS Schedule of Selected Releases fallback",
        )
        if event:
            events.append(event)

    status["bls_calendar"] = "ok" if events else "ok_no_events"
    if not events:
        notes.append("BLS calendar returned no events in the requested date range.")

    return SourceFetchResult(events, notes, status)


def _parse_fomc_meeting_dates_from_text(text: str) -> list[date]:
    """
    Parse FOMC meeting end dates from Federal Reserve calendar text.

    Handles common patterns like:
    - January 27-28, 2026
    - March 17-18, 2026
    - June 16-17, 2026
    """
    meeting_end_dates: list[date] = []

    pattern = re.compile(
        r"\b("
        r"January|February|March|April|May|June|July|August|September|October|November|December"
        r")\s+(\d{1,2})(?:\s*-\s*(\d{1,2}))?,\s*(20\d{2})\b",
        flags=re.I,
    )

    for match in pattern.finditer(text):
        month_name, first_day, second_day, year = match.groups()
        day = int(second_day or first_day)

        try:
            parsed = date_parser.parse(f"{month_name} {day}, {year}").date()
        except Exception:
            continue

        context_start = max(0, match.start() - 120)
        context_end = min(len(text), match.end() + 120)
        context = text[context_start:context_end].lower()

        if "fomc" in context or "federal open market committee" in context:
            meeting_end_dates.append(parsed)

    return sorted(set(meeting_end_dates))


def fetch_fomc_calendar(
    *,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    timeout: int = 20,
) -> SourceFetchResult:
    """
    Fetch Federal Reserve FOMC calendar.

    Emits:
    - FOMC Rate Decision event on meeting end date at 14:00 ET.
    - FOMC Minutes event roughly 21 days after meeting end date.
    """
    notes: list[str] = []
    status: dict[str, str] = {"fed_fomc_calendar": "not_started"}

    start = date_parser.parse(normalize_date(start_date) or today_et().isoformat()).date()
    end = date_parser.parse(
        normalize_date(end_date) or (today_et() + timedelta(days=30)).isoformat()
    ).date()

    text, err = _safe_get_text(FED_FOMC_CALENDAR_URL, timeout=timeout)
    if err:
        notes.append(f"Fed FOMC calendar fetch failed: {err}")
        status["fed_fomc_calendar"] = "failed_http"
        return SourceFetchResult([], notes, status)

    if text is None:
        notes.append("Fed FOMC calendar fetch returned no response text.")
        status["fed_fomc_calendar"] = "failed_no_response_text"
        return SourceFetchResult([], notes, status)

    soup = BeautifulSoup(text, "html.parser")
    plain_text = soup.get_text(" ", strip=True)

    meeting_end_dates = _parse_fomc_meeting_dates_from_text(plain_text)
    events: list[dict[str, Any]] = []

    for meeting_end_date in meeting_end_dates:
        if start <= meeting_end_date <= end:
            event = normalize_event(
                event_type="macro",
                name="FOMC Rate Decision",
                event_date=meeting_end_date,
                time_et="14:00",
                impact="high",
                source="Federal Reserve",
                note="Federal Reserve FOMC calendar fallback",
            )
            if event:
                events.append(event)

        minutes_date = meeting_end_date + timedelta(days=21)
        if start <= minutes_date <= end:
            event = normalize_event(
                event_type="macro",
                name="FOMC Minutes",
                event_date=minutes_date,
                time_et="14:00",
                impact="high",
                source="Federal Reserve",
                note=(
                    "Estimated from Fed statement that minutes are generally released "
                    "three weeks after the decision."
                ),
            )
            if event:
                events.append(event)

    status["fed_fomc_calendar"] = "ok" if events else "ok_no_events"
    if not events:
        notes.append("Fed FOMC calendar returned no events in the requested date range.")

    return SourceFetchResult(events, notes, status)