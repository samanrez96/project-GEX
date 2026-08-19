import django_filters

from common.filters import JalaliDateFilter
from employees.models import Employee


class EmployeeFilter(django_filters.FilterSet):
    """FilterSet for the employee list endpoint.

    Adds date-range filtering on start_date while preserving the simple
    equality filters that previously lived in filterset_fields.
    """

    start_date_from = JalaliDateFilter(field_name="start_date", lookup_expr="gte")
    start_date_to   = JalaliDateFilter(field_name="start_date", lookup_expr="lte")

    class Meta:
        model  = Employee
        fields = ["is_active", "gender", "job_position"]
