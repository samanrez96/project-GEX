"""Shared Jalali (Solar Hijri / Shamsi) date formatting utilities.

Converts Python date/datetime objects to Persian Jalali strings at the
presentation layer. DB storage and API contracts remain Gregorian.

Output format: ۱۴۰۵/۰۲/۱۹  (Persian digits, zero-padded month and day)
"""

import datetime
import re

import jdatetime
from django.utils import timezone


_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')

# Persian (۰–۹) and Arabic-Indic (٠–٩) digits → ASCII, for parsing user input.
_INPUT_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _to_persian(s):
    return str(s).translate(_DIGITS)


def _gregorian_to_jalali(gy, gm, gd):
    """Pure-Python Gregorian → Jalali converter. No external dependencies.

    Verified: 2025-03-21 → (1404, 1, 1).
    """
    year  = gy - 1600
    month = gm - 1
    day   = gd - 1

    g_day_no = (
        365 * year
        + (year + 3) // 4
        - (year + 99) // 100
        + (year + 399) // 400
    )
    for i in range(month):
        g_day_no += [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][i]
    if month > 1 and (
        (year % 4 == 0 and year % 100 != 0) or (year + 1600) % 400 == 0
    ):
        g_day_no += 1
    g_day_no += day

    j_day_no = g_day_no - 79

    j_np      = j_day_no // 12053
    j_day_no %= 12053

    jy        = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy      += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    for i in range(11):
        j_mi = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30][i]
        if j_day_no >= j_mi:
            j_day_no -= j_mi
        else:
            return jy, i + 1, j_day_no + 1

    # Esfand (month 12). After subtracting the first 11 months the remainder
    # is the zero-based day, so the day-of-month is remainder + 1.
    # (Previously this returned `j_day_no - 29`, which produced negative days
    #  for every Esfand date — verified against jdatetime over 1990–2040.)
    return jy, 12, j_day_no + 1


def _date_to_jalali_str(d):
    jy, jm, jd = _gregorian_to_jalali(d.year, d.month, d.day)
    return (
        _to_persian(jy)
        + '/'
        + _to_persian(str(jm).zfill(2))
        + '/'
        + _to_persian(str(jd).zfill(2))
    )


def to_jalali_date(value):
    """Return a Jalali date string '۱۴۰۵/۰۲/۱۹', or '—' for None/invalid."""
    if value is None:
        return '—'
    if isinstance(value, datetime.datetime):
        value = timezone.localtime(value).date()
    if isinstance(value, datetime.date):
        return _date_to_jalali_str(value)
    return '—'


def to_jalali_datetime(value):
    """Return a Jalali datetime string '۱۴۰۵/۰۲/۱۹ ۱۴:۳۰', or '—' for None/invalid."""
    if value is None:
        return '—'
    if isinstance(value, datetime.datetime):
        local_dt = timezone.localtime(value)
        date_part = _date_to_jalali_str(local_dt.date())
        h = _to_persian(str(local_dt.hour).zfill(2))
        m = _to_persian(str(local_dt.minute).zfill(2))
        return f'{date_part} {h}:{m}'
    if isinstance(value, datetime.date):
        return _date_to_jalali_str(value)
    return '—'


# ---------------------------------------------------------------------------
# Parsing — Jalali input → Gregorian (for forms, filters, query params)
# ---------------------------------------------------------------------------

def normalize_digits(value):
    """Convert Persian (۰–۹) and Arabic-Indic (٠–٩) digits to ASCII 0–9.

    Returns '' for None. Used to sanitise user-typed dates before parsing.
    """
    if value is None:
        return ''
    return str(value).translate(_INPUT_DIGITS)


def parse_jalali_date(value):
    """Parse a user-entered Jalali date into a Gregorian ``datetime.date``.

    Accepted input:
      • 'YYYY/MM/DD' or 'YYYY-MM-DD'
      • Persian, Arabic-Indic, or ASCII digits  (۱۴۰۵/۰۴/۰۳ == 1405/04/03)
      • a ``date``/``datetime`` (returned/normalised as-is)
      • an ISO Gregorian string ('2026-06-24') — passes through unchanged so
        existing Gregorian query params keep working.

    Returns ``None`` for ``None``/blank. Raises ``ValueError`` with a clear
    Persian message for malformed or out-of-range input.

    The DB always receives a Gregorian date; storage never changes.
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value

    s = normalize_digits(value).strip()
    if not s:
        return None

    parts = re.split(r'[/\-]', s)
    if len(parts) != 3 or not all(parts):
        raise ValueError('فرمت تاریخ نامعتبر است. نمونهٔ درست: ۱۴۰۵/۰۴/۰۳')
    try:
        y, m, d = (int(p) for p in parts)
    except ValueError:
        raise ValueError('تاریخ باید فقط شامل اعداد باشد. نمونه: ۱۴۰۵/۰۴/۰۳')

    # A 4-digit year ≥ 1700 is unambiguously Gregorian (Jalali years are
    # ~1300–1500), so existing Gregorian ISO params still resolve correctly.
    if y >= 1700:
        try:
            return datetime.date(y, m, d)
        except ValueError:
            raise ValueError('تاریخ میلادی نامعتبر است.')

    try:
        return jdatetime.date(y, m, d).togregorian()
    except Exception:
        raise ValueError('تاریخ شمسی نامعتبر است. نمونهٔ درست: ۱۴۰۵/۰۴/۰۳')


def jalali_to_iso(value):
    """Parse Jalali (or Gregorian) input → Gregorian 'YYYY-MM-DD' string.

    Returns ``None`` for ``None``/blank. Convenience wrapper for rewriting
    date query params to Gregorian before they reach a FilterSet / ORM.
    """
    parsed = parse_jalali_date(value)
    return parsed.isoformat() if parsed else None
