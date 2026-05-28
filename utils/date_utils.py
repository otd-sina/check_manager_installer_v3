from __future__ import annotations

from datetime import date as gregorian_date

import jdatetime


JALALI_DATE_FORMAT = '%Y/%m/%d'
GREGORIAN_DATE_FORMAT = '%Y-%m-%d'


def jalali_to_gregorian(value: str | jdatetime.date) -> gregorian_date:
    jalali_value = _coerce_jalali(value)
    return jalali_value.togregorian()


def gregorian_to_jalali(value: str | gregorian_date) -> jdatetime.date:
    gregorian_value = _coerce_gregorian(value)
    return jdatetime.date.fromgregorian(date=gregorian_value)


def today_jalali() -> jdatetime.date:
    return jdatetime.date.today()


def normalize_jalali_date_text(value: str) -> str:
    text = value.strip()
    if not text:
        return ''

    if '/' in text:
        parts = text.split('/')
        if len(parts) != 3:
            raise ValueError('Date must be in YYYY/MM/DD format.')
        year, month, day = map(int, parts)
        return jdatetime.date(year, month, day).strftime(JALALI_DATE_FORMAT)

    if '-' in text:
        parts = text.split('-')
        if len(parts) != 3:
            raise ValueError('Date must be in YYYY/MM/DD format.')
        year, month, day = map(int, parts)
        if year >= 1700:
            gregorian_value = gregorian_date(year, month, day)
            return gregorian_to_jalali(gregorian_value).strftime(JALALI_DATE_FORMAT)
        return jdatetime.date(year, month, day).strftime(JALALI_DATE_FORMAT)

    raise ValueError('Date must be in YYYY/MM/DD format.')


def is_valid_jalali_date_text(value: str) -> bool:
    try:
        normalized = normalize_jalali_date_text(value)
    except ValueError:
        return False
    return bool(normalized)


def _coerce_jalali(value: str | jdatetime.date) -> jdatetime.date:
    if isinstance(value, jdatetime.date):
        return value

    normalized = normalize_jalali_date_text(value)
    year, month, day = map(int, normalized.split('/'))
    return jdatetime.date(year, month, day)


def _coerce_gregorian(value: str | gregorian_date) -> gregorian_date:
    if isinstance(value, gregorian_date):
        return value

    year, month, day = map(int, value.split('-'))
    return gregorian_date(year, month, day)
