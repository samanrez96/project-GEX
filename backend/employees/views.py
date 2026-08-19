from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsAdminOrEmployeeManager
from common.excel import ExcelColumn, ExcelExportMixin, describe_ordering
from common.pagination import StandardPagination
from employees.filters import EmployeeFilter
from employees.models import Employee, EmployeePurchaseCommission, JobPosition
from employees.serializers import (
    EmployeeListSerializer,
    EmployeePurchaseCommissionSerializer,
    EmployeeSerializer,
    JobPositionListSerializer,
    JobPositionSerializer,
)

_EMPLOYEE_LIST_ACTIONS = frozenset({"list"})


class JobPositionViewSet(viewsets.ModelViewSet):
    """CRUD viewset for job positions.

    GET/POST             /api/v1/employees/positions/
    GET/PUT/PATCH/DELETE /api/v1/employees/positions/{id}/

    Search (?search=): name, description
    Ordering (?ordering=): name, created_at  (default: name)
    Filter (?is_active=true/false)
    """

    permission_classes = [IsAuthenticated]  # base, overridden for write
    filter_backends    = [SearchFilter, OrderingFilter]
    search_fields      = ["name", "description"]
    ordering_fields    = ["name", "created_at"]
    ordering           = ["name"]

    def get_serializer_class(self):
        if self.action == "list":
            return JobPositionListSerializer
        return JobPositionSerializer

    def get_queryset(self):
        qs = JobPosition.objects.all()
        is_active = self.request.query_params.get("is_active")
        if is_active == "true":
            return qs.filter(is_active=True)
        if is_active == "false":
            return qs.filter(is_active=False)
        return qs

    def get_permissions(self):
        """
        Read-only (list, retrieve) allowed for any authenticated user.
        Write operations require admin or employee manager role.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminOrEmployeeManager()]
        return [IsAuthenticated()]

    def destroy(self, request, *args, **kwargs):
        position = self.get_object()
        if position.get_active_employee_count() > 0:
            return Response(
                {"detail": "این پوزیشن دارای کارمندان فعال است و قابل حذف نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class EmployeeViewSet(ExcelExportMixin, viewsets.ModelViewSet):
    """CRUD viewset for clinic employees.

    GET/POST             /api/v1/employees/
    GET/PUT/PATCH/DELETE /api/v1/employees/{id}/

    Search (?search=):
      full_name, email, personal_phone, national_id, job_position__name

    Filters (?is_active=true/false&gender=male/female/other&job_position={id}):
      is_active, gender, job_position

    Ordering (?ordering=):
      full_name, start_date, created_at  (default: full_name)
    """

    permission_classes = [IsAuthenticated]  # base, overridden for write
    pagination_class   = StandardPagination
    filterset_class    = EmployeeFilter
    filter_backends    = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields      = [
        "full_name", "email", "personal_phone",
        "national_id", "job_position__name",
    ]
    ordering_fields    = [
        "full_name", "job_position__name", "is_active", "start_date", "created_at",
    ]
    ordering           = ["full_name"]

    def get_serializer_class(self):
        if self.action in _EMPLOYEE_LIST_ACTIONS:
            return EmployeeListSerializer
        return EmployeeSerializer

    def get_queryset(self):
        return Employee.objects.select_related("job_position")

    def get_permissions(self):
        """
        Read-only (list, retrieve) allowed for any authenticated user.
        Write operations require admin or employee manager role.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminOrEmployeeManager()]
        return [IsAuthenticated()]

    # ── Excel export ──────────────────────────────────────────────────────────
    excel_filename_prefix = 'employee-list'
    excel_sheet_title      = 'کارمندان'
    excel_report_title     = 'گزارش فهرست کارمندان'

    _ORDERING_LABELS = {
        'full_name':          'نام کامل',
        'job_position__name': 'پوزیشن شغلی',
        'is_active':          'وضعیت همکاری',
        'start_date':         'تاریخ استخدام',
        'created_at':          'تاریخ ثبت',
    }

    def get_excel_meta_rows(self, request):
        from employees.models import JobPosition

        params = request.query_params
        meta = []

        is_active_val = params.get('is_active')
        if is_active_val:
            meta.append(('وضعیت همکاری', {'true': 'فعال', 'false': 'غیرفعال'}.get(is_active_val, is_active_val)))

        gender_val = params.get('gender')
        if gender_val:
            from employees.models import GenderChoice
            meta.append(('جنسیت', dict(GenderChoice.choices).get(gender_val, gender_val)))

        position_id = params.get('job_position')
        if position_id:
            pos = JobPosition.objects.filter(pk=position_id).first()
            meta.append(('پوزیشن شغلی', pos.name if pos else position_id))

        date_from = params.get('start_date_from')
        date_to   = params.get('start_date_to')
        if date_from or date_to:
            meta.append(('بازه تاریخ استخدام', f"{date_from or '—'} تا {date_to or '—'}"))

        search_val = params.get('search')
        if search_val:
            meta.append(('جستجو', search_val))

        ordering_desc = describe_ordering(params.get('ordering'), self._ORDERING_LABELS)
        if ordering_desc:
            meta.append(('مرتب‌سازی', ordering_desc))

        return meta

    def get_excel_columns(self, request):
        return [
            ExcelColumn(key='row_number',    label='ردیف',            data_type='integer', width=6),
            ExcelColumn(key='full_name',     label='نام کامل',         data_type='text', width=22),
            ExcelColumn(key='job_position_name', label='پوزیشن شغلی',  data_type='text', width=18),
            ExcelColumn(key='email',         label='ایمیل',            data_type='text', width=22),
            ExcelColumn(key='personal_phone', label='تلفن',            data_type='text', width=14),
            ExcelColumn(key='national_id',   label='شماره ملی',        data_type='text', width=14),
            ExcelColumn(key='start_date',    label='تاریخ استخدام',    data_type='date', width=13),
            ExcelColumn(key='is_active_display', label='وضعیت',        data_type='text', width=12),
        ]

    def get_excel_summary(self, request, queryset):
        employees = list(queryset)
        total  = len(employees)
        active = sum(1 for e in employees if e.is_active)
        return [
            ('تعداد کل کارمندان', total),
            ('تعداد فعال',        active),
            ('تعداد غیرفعال',     total - active),
        ]

    def queryset_to_excel_rows(self, queryset):
        for idx, emp in enumerate(queryset, start=1):
            yield {
                'row_number':              idx,
                'full_name':               emp.full_name,
                'job_position_name':       emp.job_position.name if emp.job_position else None,
                'email':                   emp.email,
                'personal_phone':          emp.personal_phone,
                'national_id':             emp.national_id,
                'start_date':              emp.start_date,
                'is_active_display':       'فعال' if emp.is_active else 'غیرفعال',
            }


class EmployeePurchaseCommissionViewSet(viewsets.ModelViewSet):
    """CRUD for employee purchase commissions.

    GET/POST             /api/v1/employees/purchase-commissions/
    GET/PUT/PATCH/DELETE /api/v1/employees/purchase-commissions/{id}/

    Filter: ?employee={id}
    Ordering: commission_date (default: -commission_date)
    """

    permission_classes = [IsAuthenticated]  # base, overridden for write
    serializer_class   = EmployeePurchaseCommissionSerializer
    filter_backends    = [DjangoFilterBackend, OrderingFilter]
    filterset_fields   = ['employee']
    ordering_fields    = ['commission_date', 'amount', 'created_at']
    ordering           = ['-commission_date']

    def get_queryset(self):
        return EmployeePurchaseCommission.objects.select_related(
            'employee', 'purchase', 'purchase__vendor',
        ).prefetch_related('purchase__items__product')

    def get_permissions(self):
        """
        Read-only (list, retrieve) allowed for any authenticated user.
        Write operations require admin or employee manager role.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminOrEmployeeManager()]
        return [IsAuthenticated()]