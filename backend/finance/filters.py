import django_filters

from common.filters import JalaliDateFilter
from finance.models import Transaction


class TransactionFilter(django_filters.FilterSet):
    """FilterSet for the transaction list endpoint."""

    transaction_date__gte = JalaliDateFilter(
        field_name="transaction_date", lookup_expr="date__gte"
    )
    transaction_date__lte = JalaliDateFilter(
        field_name="transaction_date", lookup_expr="date__lte"
    )

    class Meta:
        model = Transaction
        fields = ["transaction_type", "payment_status", "category"]