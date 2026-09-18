import django_filters
from django import forms

from common.filters import JalaliDateFilter
from surgeries.models import SurgeryHistory


class SurgeryHistoryFilterForm(forms.Form):
    """Cross-field validation for the surgery date range.

    Each of surgery_date_from/surgery_date_to already validates on its own
    (via JalaliDateFilter), so a reversed range (from > to) passes per-field
    validation but silently produces an impossible ``date__gte=X AND
    date__lte=Y`` queryset that can never match any row. Reject it explicitly
    instead of returning a confusing, unexplained empty result.
    """

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("surgery_date_from")
        date_to   = cleaned.get("surgery_date_to")
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError(
                "تاریخ شروع نمی‌تواند بعد از تاریخ پایان باشد.", code="invalid_range",
            )
        return cleaned


class SurgeryHistoryFilter(django_filters.FilterSet):
    """FilterSet for the surgery history list endpoint.

    Adds date-range and amount-range filtering on top of the simple equality
    filters that previously lived in filterset_fields.

    Note: surgery_date is a DateTimeField.  The ``date__gte`` / ``date__lte``
    lookups extract the date component before comparing, so a user-supplied
    YYYY-MM-DD value works correctly regardless of time-of-day.
    """

    surgery_date_from = JalaliDateFilter(
        field_name="surgery_date", lookup_expr="date__gte"
    )
    surgery_date_to   = JalaliDateFilter(
        field_name="surgery_date", lookup_expr="date__lte"
    )
    min_amount = django_filters.NumberFilter(field_name="amount", lookup_expr="gte")
    max_amount = django_filters.NumberFilter(field_name="amount", lookup_expr="lte")

    class Meta:
        model  = SurgeryHistory
        form   = SurgeryHistoryFilterForm
        fields = [
            "patient",
            "surgery_type",
            "status",
            "payment_status",
            "clinical_doctor",
            "doctor_or_therapist",
        ]
