"""Holiday service for Jalali calendar widgets.

This module fetches official Iranian holidays with automatic fallback between
multiple APIs. Results are normalized to ``{month_number: {day, ...}}`` and
cached in memory so each Jalali year is fetched only once per process.
"""

from __future__ import annotations

from logging import getLogger
from threading import Lock
from typing import Any

import requests

from utils.date_utils import normalize_jalali_date_text


logger = getLogger(__name__)

PRIMARY_API_URL = "https://api.persian-calendar.ir/api/v1/calendar/{year}/holidays"
FALLBACK_API_URL = "https://pnldev.com/api/calender?year={year}"
REQUEST_TIMEOUT_SECONDS = 8

HolidayMap = dict[int, set[int]]


_cache: dict[int, HolidayMap] = {}
_cache_lock = Lock()


def get_iran_holidays_for_year(year: int, *, force_refresh: bool = False) -> HolidayMap:
    """Return official holidays for a Jalali year as ``{month: {day, ...}}``.

    The primary API is always attempted first. If it fails, the fallback API is
    used. Any request/parsing problem returns an empty mapping instead of
    raising, and successful or empty results are cached per year.
    """

    if year < 1200 or year > 1700:
        logger.warning("Ignoring invalid Jalali year for holiday lookup: %s", year)
        return {}

    if not force_refresh:
        cached_holidays = _read_cache(year)
        if cached_holidays is not None:
            return cached_holidays

    holidays = _fetch_holidays_from_apis(year)
    _write_cache(year, holidays)
    return holidays


def _fetch_holidays_from_apis(year: int) -> HolidayMap:
    """Fetch one year of official holidays, falling back safely on failure."""

    primary_holidays = _fetch_from_endpoint(
        PRIMARY_API_URL.format(year=year),
        year,
        assume_holiday_if_missing=True,
        source_name="primary",
    )
    if primary_holidays is not None:
        return primary_holidays

    fallback_holidays = _fetch_from_endpoint(
        FALLBACK_API_URL.format(year=year),
        year,
        assume_holiday_if_missing=False,
        source_name="fallback",
    )
    if fallback_holidays is not None:
        return fallback_holidays

    return {}


def _fetch_from_endpoint(
    url: str,
    year: int,
    *,
    assume_holiday_if_missing: bool,
    source_name: str,
) -> HolidayMap | None:
    """Fetch and normalize holidays from one endpoint.

    Returns ``None`` only when the endpoint fails outright so callers can try a
    fallback. An empty mapping means the endpoint responded successfully but had
    no official holidays.
    """

    payload = _fetch_json_payload(url)
    if payload is None:
        return None

    holidays: HolidayMap = {}
    for record in _iter_holiday_records(payload):
        parsed = _parse_holiday_record(
            record,
            year,
            assume_holiday_if_missing=assume_holiday_if_missing,
        )
        if parsed is None:
            continue

        month, day = parsed
        holidays.setdefault(month, set()).add(day)

    if not holidays:
        logger.warning("%s holiday API returned no official holidays for year %s.", source_name, year)

    return holidays


def _fetch_json_payload(url: str) -> Any | None:
    """Fetch one JSON payload from API; return ``None`` on request/parsing error."""

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.warning("Holiday API request failed for %s: %s", url, exc)
        return None
    except ValueError as exc:
        logger.warning("Holiday API JSON parse failed for %s: %s", url, exc)
        return None


def _iter_holiday_records(payload: Any) -> list[dict[str, Any]]:
    """Extract possible holiday record dictionaries from unknown API shapes."""

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    if _looks_like_holiday_record(payload):
        return [payload]

    candidate_keys = (
        "data",
        "holidays",
        "result",
        "items",
        "days",
        "records",
        "response",
    )
    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _iter_holiday_records(value)
            if nested:
                return nested

    for value in payload.values():
        if isinstance(value, (dict, list)):
            nested_records = _iter_holiday_records(value)
            if nested_records:
                return nested_records

    return []


def _parse_holiday_record(
    record: dict[str, Any],
    target_year: int,
    *,
    assume_holiday_if_missing: bool,
) -> tuple[int, int] | None:
    """Parse one holiday record into ``(month, day)`` if it is official."""

    holiday_flag = _extract_holiday_flag(record)
    if holiday_flag is False:
        return None
    if holiday_flag is None and not assume_holiday_if_missing:
        return None

    parsed_text = _parse_date_text(record, target_year)
    if parsed_text is not None:
        return parsed_text

    return _parse_date_parts(record, target_year)


def _parse_date_text(record: dict[str, Any], target_year: int) -> tuple[int, int] | None:
    """Parse date from text fields such as ``YYYY/MM/DD`` or ``YYYY-MM-DD``."""

    for key in (
        "shamsiDate",
        "jalaliDate",
        "persianDate",
        "solarDate",
        "date",
    ):
        date_text = record.get(key)
        if not isinstance(date_text, str):
            continue
        try:
            normalized = normalize_jalali_date_text(date_text)
            year_text, month_text, day_text = normalized.split("/")
            year = int(year_text)
            month = int(month_text)
            day = int(day_text)
        except (ValueError, TypeError):
            continue

        if year == target_year:
            return month, day
    return None


def _parse_date_parts(record: dict[str, Any], target_year: int) -> tuple[int, int] | None:
    """Parse date from split integer fields or nested Jalali date objects."""

    for year_key, month_key, day_key in (
        ("year", "month", "day"),
        ("jalaliYear", "jalaliMonth", "jalaliDay"),
        ("shamsiYear", "shamsiMonth", "shamsiDay"),
    ):
        year = _coerce_int(record.get(year_key))
        month = _coerce_int(record.get(month_key))
        day = _coerce_int(record.get(day_key))
        if year == target_year and month is not None and day is not None:
            return month, day

    for nested_key in (
        "date",
        "solar",
        "jalali",
        "shamsi",
        "persian",
        "persianDate",
    ):
        nested_date = record.get(nested_key)
        if isinstance(nested_date, dict):
            parsed_nested = _parse_date_parts(nested_date, target_year)
            if parsed_nested is not None:
                return parsed_nested

    month = _coerce_int(record.get("month"))
    day = _coerce_int(record.get("day"))
    if month is not None and day is not None:
        record_year = _find_target_year(record)
        if record_year == target_year:
            return month, day

    return None


def _find_target_year(record: dict[str, Any]) -> int | None:
    """Look for a Jalali year across common top-level and nested fields."""

    for key in ("year", "jalaliYear", "shamsiYear"):
        value = _coerce_int(record.get(key))
        if value is not None:
            return value

    for nested_key in ("date", "solar", "jalali", "shamsi", "persian", "persianDate"):
        nested_value = record.get(nested_key)
        if isinstance(nested_value, dict):
            nested_year = _find_target_year(nested_value)
            if nested_year is not None:
                return nested_year

    return None


def _extract_holiday_flag(record: dict[str, Any]) -> bool | None:
    """Extract explicit holiday flags from supported API key variants."""

    for key in (
        "isHoliday",
        "holiday",
        "is_holiday",
        "officialHoliday",
        "isOfficialHoliday",
    ):
        if key in record:
            return _coerce_bool(record.get(key))
    return None


def _coerce_bool(value: Any) -> bool | None:
    """Best-effort conversion for booleans that may come as strings or numbers."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "y", "on"}:
            return True
        if text in {"false", "0", "no", "n", "off"}:
            return False
    return None


def _coerce_int(value: Any) -> int | None:
    """Best-effort integer conversion that accepts localized digit strings."""

    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _looks_like_holiday_record(payload: dict[str, Any]) -> bool:
    """Return True when a dictionary looks like one holiday/day record."""

    return any(
        key in payload
        for key in (
            "isHoliday",
            "holiday",
            "shamsiDate",
            "jalaliDate",
            "persianDate",
            "solarDate",
            "day",
            "jalaliDay",
            "shamsiDay",
            "solar",
        )
    )


def _read_cache(year: int) -> HolidayMap | None:
    """Read one year of cached holidays."""

    with _cache_lock:
        entry = _cache.get(year)
        if entry is None:
            return None
        return {month: set(days) for month, days in entry.items()}


def _write_cache(year: int, holidays: HolidayMap) -> None:
    """Write one year of holidays into the in-memory cache."""

    with _cache_lock:
        _cache[year] = {month: set(days) for month, days in holidays.items()}
