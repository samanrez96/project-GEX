"""Reusable Jalali date widgets/fields and shared decimal helpers for Django admin.

The admin stores Gregorian values unchanged; these only translate at the
form boundary:

  • display  — a stored Gregorian date/datetime is rendered as a Jalali
               string in a plain text input (Persian digits, YYYY/MM/DD).
  • input    — the submitted Jalali string is parsed back to Gregorian
               before the model is saved.

Attach with ``formfield_overrides`` on a ModelAdmin, e.g.::

    formfield_overrides = {
        models.DateField:     {"form_class": JalaliFormDateField},
        models.DateTimeField: {"form_class": JalaliFormDateTimeField},
    }
"""

import datetime

from django import forms
from django.conf import settings
from django.contrib import admin
from django.db import models as _models
from django.utils import timezone

from common.dates import (
    normalize_digits,
    parse_jalali_date,
    to_jalali_date,
    to_jalali_datetime,
)


class JalaliAdminDatesMixin:
    """Render model date/datetime fields as Jalali in admin readonly views and
    list_display columns.

    Use the ``*_jalali`` method name (instead of the raw field) in
    ``readonly_fields`` / ``list_display``.  DB values are never changed;
    timezone is preserved because ``to_jalali_datetime`` localtimes aware
    datetimes, and ``—`` is returned for empty values.
    """

    @admin.display(description="تاریخ ایجاد", ordering="created_at")
    def created_at_jalali(self, obj):
        return to_jalali_datetime(getattr(obj, "created_at", None))

    @admin.display(description="آخرین ویرایش", ordering="updated_at")
    def updated_at_jalali(self, obj):
        return to_jalali_datetime(getattr(obj, "updated_at", None))

    @admin.display(description="تاریخ بسته شدن", ordering="closed_at")
    def closed_at_jalali(self, obj):
        return to_jalali_datetime(getattr(obj, "closed_at", None))

    @admin.display(description="تاریخ درآمد", ordering="income_date")
    def income_date_jalali(self, obj):
        return to_jalali_datetime(getattr(obj, "income_date", None))

    @admin.display(description="تاریخ تراکنش", ordering="transaction_date")
    def transaction_date_jalali(self, obj):
        return to_jalali_datetime(getattr(obj, "transaction_date", None))

    @admin.display(description="تاریخ عمل", ordering="surgery_date")
    def surgery_date_jalali(self, obj):
        return to_jalali_datetime(getattr(obj, "surgery_date", None))

    @admin.display(description="تاریخ شروع", ordering="start_date")
    def start_date_jalali(self, obj):
        return to_jalali_date(getattr(obj, "start_date", None))

    @admin.display(description="تاریخ پایان", ordering="end_date")
    def end_date_jalali(self, obj):
        return to_jalali_date(getattr(obj, "end_date", None))

    @admin.display(description="تاریخ حرکت", ordering="movement_date")
    def movement_date_jalali(self, obj):
        return to_jalali_datetime(getattr(obj, "movement_date", None))

    @admin.display(description="تاریخ آخرین قیمت", ordering="last_price_date")
    def last_price_date_jalali(self, obj):
        return to_jalali_date(getattr(obj, "last_price_date", None))

_BASE_ATTRS = {
    "placeholder": "۱۴۰۵/۰۴/۰۳",
    "dir": "ltr",
    "inputmode": "numeric",
    "autocomplete": "off",
    "class": "jalali-date-input vTextField",
}


class JalaliDateWidget(forms.TextInput):
    """Text input that displays a Gregorian date as a Jalali string."""

    def __init__(self, attrs=None):
        merged = dict(_BASE_ATTRS)
        if attrs:
            merged.update(attrs)
        super().__init__(merged)

    def format_value(self, value):
        if value in (None, ""):
            return ""
        if isinstance(value, str):
            return value          # re-render after a validation error
        return to_jalali_date(value)


class JalaliDateTimeWidget(forms.TextInput):
    """Text input that displays a Gregorian datetime as 'Jalali HH:MM'."""

    def __init__(self, attrs=None):
        merged = dict(_BASE_ATTRS)
        merged["placeholder"] = "۱۴۰۵/۰۴/۰۳ ۱۲:۳۰"
        if attrs:
            merged.update(attrs)
        super().__init__(merged)

    def format_value(self, value):
        if value in (None, ""):
            return ""
        if isinstance(value, str):
            return value
        return to_jalali_datetime(value)


class JalaliFormDateField(forms.DateField):
    """Form field for a model ``DateField`` — lossless Jalali ⇄ Gregorian."""

    widget = JalaliDateWidget

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            return parse_jalali_date(value)
        except ValueError as exc:
            raise forms.ValidationError(str(exc), code="invalid")


class JalaliFormDateTimeField(forms.Field):
    """Form field for a model ``DateTimeField``.

    Accepts 'YYYY/MM/DD' or 'YYYY/MM/DD HH:MM' (Persian/Arabic/ASCII digits).
    The time part is preserved when present, so editing only the date keeps
    the original time; a date-only entry defaults to 00:00.
    """

    widget = JalaliDateTimeWidget

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, datetime.datetime):
            return value

        s = normalize_digits(value).strip()
        if not s:
            return None
        bits = s.split()
        try:
            d = parse_jalali_date(bits[0])
            hh, mm = 0, 0
            if len(bits) > 1 and ":" in bits[1]:
                hp, mp = bits[1].split(":")[:2]
                hh, mm = int(hp), int(mp)
            dt = datetime.datetime(d.year, d.month, d.day, hh, mm)
        except (ValueError, TypeError):
            raise forms.ValidationError(
                "فرمت تاریخ/زمان نامعتبر است. نمونه: ۱۴۰۵/۰۴/۰۳ ۱۲:۳۰",
                code="invalid",
            )
        if settings.USE_TZ:
            dt = timezone.make_aware(dt)
        return dt


class JalaliFormDateForDateTimeField(forms.Field):
    """Form field for a model ``DateTimeField`` where only the date matters.

    Shows and accepts 'YYYY/MM/DD' Jalali date only — the time component is
    hidden from the UI entirely.  Saves as a timezone-aware datetime at local
    midnight of the selected date, preserving the exact calendar day under any
    timezone conversion.

    Use this instead of ``JalaliFormDateTimeField`` when the business only
    cares about the calendar day but the DB column is a DateTimeField.
    """

    widget = JalaliDateWidget

    def to_python(self, value):
        if value in self.empty_values:
            return None
        # Already a datetime (e.g. from has_changed initial-value check)
        if isinstance(value, datetime.datetime):
            return value
        # date without time — wrap in midnight datetime
        if isinstance(value, datetime.date):
            dt = datetime.datetime(value.year, value.month, value.day, 0, 0, 0)
            return timezone.make_aware(dt) if settings.USE_TZ else dt

        s = normalize_digits(value).strip()
        if not s:
            return None
        try:
            d = parse_jalali_date(s)
        except (ValueError, TypeError) as exc:
            raise forms.ValidationError(
                "تاریخ نامعتبر است. نمونه: ۱۴۰۵/۰۴/۱۳",
                code="invalid",
            ) from exc
        dt = datetime.datetime(d.year, d.month, d.day, 0, 0, 0)
        return timezone.make_aware(dt) if settings.USE_TZ else dt


# Ready-made ModelAdmin.formfield_overrides mapping.  BOTH form_class AND
# widget must be given: Django merges these onto FORMFIELD_FOR_DBFIELD_DEFAULTS,
# so without an explicit widget the admin's default (AdminDateWidget /
# AdminSplitDateTime — Gregorian) would win and the input would stay Gregorian.
JALALI_FORMFIELD_OVERRIDES = {
    _models.DateField:     {"form_class": JalaliFormDateField,     "widget": JalaliDateWidget},
    _models.DateTimeField: {"form_class": JalaliFormDateTimeField, "widget": JalaliDateTimeWidget},
}


# ---------------------------------------------------------------------------
# Shared decimal display helper
# ---------------------------------------------------------------------------

def clean_decimal_display(value):
    """Strip trailing zeros for clean decimal display (display only, no rounding).

    Decimal('15000.00') → '15000'
    Decimal('15000.50') → '15000.5'
    Decimal('12.75')    → '12.75'
    Decimal('0.00')     → '0'
    """
    from decimal import Decimal, InvalidOperation
    if value is None or str(value) in ('', 'None'):
        return ''
    try:
        d = Decimal(str(value))
        if d == d.to_integral_value():
            return str(int(d.to_integral_value()))
        s = f'{d:f}'
        return s.rstrip('0').rstrip('.')
    except (InvalidOperation, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# Shared decimal widget — strips trailing zeros + step="any" for spinners
# ---------------------------------------------------------------------------

class DecimalWidget(forms.NumberInput):
    """NumberInput that strips trailing zeros from the displayed value and sets
    step="any" so that:
      • browser spinner arrows increment/decrement by 1 (browser default for "any")
      • manual decimal typing is accepted without HTML validation blocking it

    Purely cosmetic for the displayed value; the underlying DecimalField validates
    and saves correctly.
    """

    def __init__(self, attrs=None):
        defaults = {'step': 'any'}
        if attrs:
            defaults.update(attrs)
        super().__init__(defaults)

    def format_value(self, value):
        result = clean_decimal_display(value)
        return result if result != '' else ''


# Ready-made formfield_overrides entry for DecimalField — apply to any admin
# that edits decimal amounts so spinner arrows go 0 → 1 → 2 and trailing
# zeros are stripped from the input display.
DECIMAL_FORMFIELD_OVERRIDES = {
    _models.DecimalField: {'widget': DecimalWidget},
}


# ---------------------------------------------------------------------------
# Money input widget — text input with live comma formatting
# ---------------------------------------------------------------------------

class MoneyInput(forms.TextInput):
    """TextInput for monetary decimal values.

    • Displays the stored value with comma thousands separators (1,000,000).
    • Adds data-money-input so static/admin/js/money_input.js initialises
      live comma formatting while the user types.
    • value_from_datadict() strips commas and normalises Persian/Arabic digits
      to ASCII before Django's DecimalField validation runs.
    """

    def __init__(self, attrs=None):
        defaults = {'inputmode': 'decimal', 'data-money-input': '1'}
        if attrs:
            defaults.update(attrs)
        super().__init__(defaults)

    def format_value(self, value):
        raw = clean_decimal_display(value)
        if not raw:
            return ''
        try:
            int_part, sep, dec_part = raw.partition('.')
            formatted_int = '{:,}'.format(int(int_part))
            return '{}.{}'.format(formatted_int, dec_part) if sep else formatted_int
        except (ValueError, TypeError):
            return raw

    def value_from_datadict(self, data, files, name):
        raw = super().value_from_datadict(data, files, name)
        if raw is None:
            return raw
        raw = normalize_digits(raw)
        return raw.replace(',', '')


MONEY_FORMFIELD_OVERRIDES = {
    _models.DecimalField: {'widget': MoneyInput},
}
