from django import template
from common.dates import to_jalali_date, to_jalali_datetime

register = template.Library()


@register.filter
def jalali_date(value):
    """Convert a date/datetime to a Jalali string: ۱۴۰۵/۰۲/۱۹"""
    return to_jalali_date(value)


@register.filter
def jalali_datetime(value):
    """Convert a datetime to a Jalali string: ۱۴۰۵/۰۲/۱۹ ۱۴:۳۰"""
    return to_jalali_datetime(value)
