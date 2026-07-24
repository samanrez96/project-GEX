"""Reusable Jalali-aware filter primitives for django-filter FilterSets.

``JalaliDateFilter`` is a drop-in replacement for ``django_filters.DateFilter``
that accepts a Jalali date string ('۱۴۰۵/۰۴/۰۳' or '1405/04/03') and converts
it to a Gregorian ``date`` before the ORM lookup runs.  Existing Gregorian ISO
query params ('2026-06-24') still work unchanged, so no API contract breaks.
"""

import django_filters
from django import forms

from common.dates import parse_jalali_date


class JalaliDateFormField(forms.DateField):
    """forms.DateField whose ``to_python`` understands Jalali input."""

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            return parse_jalali_date(value)
        except ValueError as exc:
            raise forms.ValidationError(str(exc), code="invalid")


class JalaliDateFilter(django_filters.DateFilter):
    """DateFilter that parses Jalali (or Gregorian) input to a Gregorian date."""

    field_class = JalaliDateFormField
