import django_filters

from common.filters import JalaliDateFilter
from finance.models import Transaction


class TransactionFilter(django_filters.FilterSet):
    """FilterSet for the transaction list endpoint.

    The admin UI sends Django-lookup-style param names
    (``transaction_date__gte`` / ``transaction_date__lte``); these are kept as
    the public param names for back-compat and routed through JalaliDateFilter
    so a Jalali (or Gregorian) date string filters correctly on the
    ``transaction_date`` DateTimeField (date component only).
    """

    transaction_date__gte = JalaliDateFilter(
        field_name="transaction_date", lookup_expr="date__gte"
    )
    transaction_date__lte = JalaliDateFilter(
        field_name="transaction_date", lookup_expr="date__lte"
    )

    class Meta:
        model  = Transaction
        fields = ["transaction_type", "payment_status", "category"]
